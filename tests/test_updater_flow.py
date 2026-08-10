# -*- coding: utf-8 -*-
"""
更新流程：下载解压、延迟替换（安全软件拦截降级）、目录替换。

    python -m unittest discover tests
"""
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from kuraya import updater


class Download(unittest.TestCase):
    """下载与解压，结构不符必须失败且不触碰现有安装"""

    def make_zip(self, tmp, with_exe=True, with_app=False):
        root = Path(tmp) / 'x' / 'Kuraya'
        root.mkdir(parents=True)
        if with_exe:
            (root / 'Kuraya').write_bytes(b'#!/bin/sh\n')
        if with_app:
            (Path(tmp) / 'x' / 'Kuraya.app').mkdir()
        zip_path = Path(tmp) / 'pkg.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for f in (Path(tmp) / 'x').rglob('*'):
                if f.is_file():
                    zf.write(f, f.relative_to(Path(tmp) / 'x'))
        return zip_path

    class FakeResp:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_content(self, size):
            yield self._body

    def fake_get(self, zip_path):
        return mock.patch.object(
            updater.requests, 'get',
            return_value=self.FakeResp(zip_path.read_bytes()))

    def test_download_and_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = self.make_zip(tmp)
            with self.fake_get(zip_path):
                new, tmp_root = updater._download('0.3.0')
            self.assertTrue(new.is_dir())
            self.assertTrue((new / 'Kuraya').is_file())
            self.addCleanup(shutil.rmtree, tmp_root, ignore_errors=True)

    def test_non_200_raises(self):
        with tempfile.TemporaryDirectory():
            resp = self.FakeResp(b'')
            resp.status_code = 404
            with mock.patch.object(updater.requests, 'get',
                                   return_value=resp):
                with self.assertRaises(updater.UpdateError):
                    updater._download('0.3.0')

    def test_missing_exe_raises(self):
        """zip 里没有可执行文件说明包结构不对，必须拒绝"""
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = self.make_zip(tmp, with_exe=False)
            with self.fake_get(zip_path):
                with self.assertRaises(updater.UpdateError):
                    updater._download('0.3.0')

    def test_unix_exec_permission_restored(self):
        """zipfile 不保留 Unix 权限位，须从 external_attr 恢复，
        否则可执行文件失去 +x，自更新后无法运行"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'x' / 'Kuraya'
            root.mkdir(parents=True)
            info = zipfile.ZipInfo('Kuraya/Kuraya')
            info.external_attr = 0o755 << 16      # 模拟 unzip/zip 存的权限
            with zipfile.ZipFile(Path(tmp) / 'pkg.zip', 'w') as zf:
                zf.writestr(info, b'#!/bin/sh\n')
            with self.fake_get(Path(tmp) / 'pkg.zip'):
                new, tmp_root = updater._download('0.3.0')
            mode = (new / 'Kuraya').stat().st_mode
            self.assertTrue(mode & 0o111, f'可执行位丢失: {oct(mode)}')
            self.addCleanup(shutil.rmtree, tmp_root, ignore_errors=True)

    def test_missing_exe_permission_forced(self):
        """zip 完全没带权限位时，主可执行文件也要强制补 +x"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'x' / 'Kuraya'
            root.mkdir(parents=True)
            info = zipfile.ZipInfo('Kuraya/Kuraya')
            info.external_attr = 0                     # 无权限信息
            with zipfile.ZipFile(Path(tmp) / 'pkg.zip', 'w') as zf:
                zf.writestr(info, b'#!/bin/sh\n')
            with self.fake_get(Path(tmp) / 'pkg.zip'):
                new, tmp_root = updater._download('0.3.0')
            mode = (new / 'Kuraya').stat().st_mode
            self.assertTrue(mode & 0o111, f'可执行位缺失: {oct(mode)}')
            self.addCleanup(shutil.rmtree, tmp_root, ignore_errors=True)


class ReplaceLater(unittest.TestCase):
    """安全软件拦截时降级为延迟替换（独立进程在程序退出后完成）"""

    def test_update_falls_back_to_later_replace(self):
        """WinError 5（拒绝访问）时安排延迟替换，不再报失败"""
        new_dir = Path(tempfile.mkdtemp())
        (new_dir / 'Kuraya').mkdir(parents=True)
        self.addCleanup(shutil.rmtree, new_dir, ignore_errors=True)
        exe = '/opt/Kuraya/Kuraya.exe'
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'win32'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch.object(updater, 'latest', return_value='9.9.9'), \
                mock.patch('builtins.input', return_value='y'), \
                mock.patch.object(updater, '_download',
                                  return_value=(new_dir, new_dir.parent)), \
                mock.patch.object(updater, '_replace',
                                  side_effect=updater.UpdateError(
                                      'blocked', winerror=5)), \
                mock.patch.object(updater, '_replace_later',
                                  return_value=True) as later:
            code = updater.update(yes=True)
        self.assertEqual(code, 0)
        later.assert_called_once()

    def test_later_replace_writes_script_and_launches(self):
        """延迟脚本包含目标与新目录路径，用脱离控制台的 PowerShell 启动"""
        tmp = Path(tempfile.mkdtemp())
        new_dir = tmp / 'x' / 'Kuraya'
        target = Path('/opt/Kuraya')
        with mock.patch.object(updater.subprocess, 'Popen') as popen:
            ok = updater._replace_later(new_dir, target)
        self.assertTrue(ok)
        script = tmp / 'replace.ps1'
        self.assertTrue(script.is_file())
        content = script.read_text(encoding='utf-8-sig')
        self.assertIn('/opt/Kuraya', content)
        self.assertIn('Rename-Item', content)
        args = popen.call_args[0][0]
        self.assertEqual(args[0], 'powershell')
        self.assertEqual(args[args.index('-File') + 1], str(script))
        # 判别性：脱离父进程控制台（用户点 × 关窗时 CTRL_CLOSE_EVENT
        # 不会带走脚本；旧版无 creationflags 且带 -WindowStyle Hidden）
        kwargs = popen.call_args[1]
        self.assertIn('creationflags', kwargs)
        self.assertNotIn('-WindowStyle', args)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

    def test_update_falls_back_on_winerror32(self):
        """WinError 32（共享冲突，如资源管理器占用目录）同样走延迟替换"""
        new_dir = Path(tempfile.mkdtemp())
        (new_dir / 'Kuraya').mkdir(parents=True)
        self.addCleanup(shutil.rmtree, new_dir, ignore_errors=True)
        exe = '/opt/Kuraya/Kuraya.exe'
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'win32'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch.object(updater, 'latest', return_value='9.9.9'), \
                mock.patch('builtins.input', return_value='y'), \
                mock.patch.object(updater, '_download',
                                  return_value=(new_dir, new_dir.parent)), \
                mock.patch.object(updater, '_replace',
                                  side_effect=updater.UpdateError(
                                      'sharing', winerror=32)), \
                mock.patch.object(updater, '_replace_later',
                                  return_value=True) as later:
            code = updater.update(yes=True)
        self.assertEqual(code, 0)
        later.assert_called_once()

    def test_later_replace_waits_exit_then_retries_rename(self):
        """脚本两阶段：先等进程退出（Get-Process），再重试重命名（while）。
        判别性：旧版固定 Start-Sleep 3 秒/纯进程等待都会失败"""
        tmp = Path(tempfile.mkdtemp())
        new_dir = tmp / 'x' / 'Kuraya'
        target = Path('/opt/Kuraya')
        with mock.patch.object(updater.sys, 'platform', 'win32'), \
             mock.patch.object(updater.subprocess, 'Popen'):
            ok = updater._replace_later(new_dir, target)
        self.assertTrue(ok)
        content = (tmp / 'replace.ps1').read_text(encoding='utf-8-sig')
        # 阶段 1：等进程退出（运行中的 exe 锁目录，重命名必被拒）
        self.assertIn('Get-Process', content)
        self.assertIn('Kuraya.exe', content)
        # 阶段 2：进程退出后重试重命名（防用户快速重开）
        self.assertIn('while ($true)', content)
        self.assertIn('Rename-Item -LiteralPath $target', content)
        self.assertIn('$deadline', content)
        self.assertNotIn('Start-Sleep -Seconds 3', content)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

    def test_update_fails_without_winerror5(self):
        """非拒绝访问错误不降级，正常报失败"""
        new_dir = Path(tempfile.mkdtemp())
        (new_dir / 'Kuraya').mkdir(parents=True)
        self.addCleanup(shutil.rmtree, new_dir, ignore_errors=True)
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'win32'), \
                mock.patch.object(updater.sys, 'executable',
                                  '/opt/Kuraya/Kuraya.exe'), \
                mock.patch.object(updater, 'latest', return_value='9.9.9'), \
                mock.patch.object(updater, '_download',
                                  return_value=(new_dir, new_dir.parent)), \
                mock.patch.object(updater, '_replace',
                                  side_effect=updater.UpdateError('x')):
            self.assertEqual(updater.update(yes=True), 1)


class Replace(unittest.TestCase):
    """替换顺序：旧目录改名 .old → 新目录就位 → 删旧；失败恢复"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.target = self.root / 'Kuraya'
        self.target.mkdir()
        (self.target / 'old.txt').write_text('old')
        self.new = self.root / 'new'
        self.new.mkdir()
        (self.new / 'new.txt').write_text('new')

    def test_swaps_directories(self):
        updater._replace(self.new, self.target)
        self.assertEqual((self.target / 'new.txt').read_text(), 'new')
        self.assertFalse((self.target / 'old.txt').exists())
        self.assertFalse((self.root / 'Kuraya.old').exists())

    def test_restores_on_failure(self):
        with mock.patch.object(updater.shutil, 'move',
                               side_effect=OSError('locked')):
            with self.assertRaises(updater.UpdateError):
                updater._replace(self.new, self.target)
        self.assertEqual((self.target / 'old.txt').read_text(), 'old')
        self.assertFalse((self.root / 'Kuraya.old').exists())

    def test_retries_transient_rename_failure(self):
        """Windows 上目录可能被杀软短暂占用，rename 失败要重试"""
        real_rename = Path.rename
        calls = {'n': 0}

        def flaky(self_, dst):
            calls['n'] += 1
            if calls['n'] <= 2:
                raise OSError('Access is denied')
            return real_rename(self_, dst)

        with mock.patch.object(Path, 'rename', flaky):
            updater._replace(self.new, self.target)
        self.assertEqual((self.target / 'new.txt').read_text(), 'new')
        self.assertEqual(calls['n'], 3)

    def test_gives_up_after_retries(self):
        with mock.patch.object(Path, 'rename',
                               side_effect=OSError('Access is denied')):
            with self.assertRaises(updater.UpdateError):
                updater._replace(self.new, self.target)
        # 旧目录未被破坏（rename 始终失败，原样保留）
        self.assertTrue((self.root / 'Kuraya').is_dir())


if __name__ == '__main__':
    unittest.main()
