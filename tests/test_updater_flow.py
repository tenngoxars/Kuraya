# -*- coding: utf-8 -*-
"""
更新流程：下载解压、就地逐文件替换（Windows）、整目录替换（其余平台）。

    python -m unittest discover tests
"""
import os
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
                                   return_value=resp) as get:
                with self.assertRaises(updater.UpdateError):
                    updater._download('0.3.0')
            # 资产不存在，重试多少次都一样，只该请求一次
            self.assertEqual(get.call_count, 1)

    def test_network_failure_retried(self):
        """几十 MB 单流下载中途断一次很常见，一次卡顿不该判死整个更新"""
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = self.make_zip(tmp)
            timeout = updater.requests.exceptions.ReadTimeout('stalled')
            with mock.patch.object(
                    updater.requests, 'get',
                    side_effect=[timeout, timeout,
                                 self.FakeResp(zip_path.read_bytes())]) as get, \
                    mock.patch.object(updater.time, 'sleep'):
                new, tmp_root = updater._download('0.3.0')
            self.assertEqual(get.call_count, updater.DOWNLOAD_TRIES)
            self.assertTrue((new / 'Kuraya').is_file())
            self.addCleanup(shutil.rmtree, tmp_root, ignore_errors=True)

    def test_network_failure_gives_up_with_next_step(self):
        """重试用尽后的报错要能让人往下走：异常类名之外还得给出手动下载地址"""
        timeout = updater.requests.exceptions.ConnectTimeout('no route')
        with mock.patch.object(updater.requests, 'get',
                               side_effect=timeout) as get, \
                mock.patch.object(updater.time, 'sleep') as sleep:
            with self.assertRaises(updater.UpdateError) as caught:
                updater._download('0.3.0')
        self.assertEqual(get.call_count, updater.DOWNLOAD_TRIES)
        self.assertEqual(sleep.call_count, updater.DOWNLOAD_TRIES - 1)
        message = str(caught.exception)
        self.assertIn('ConnectTimeout', message)
        self.assertIn('HTTPS_PROXY', message)
        self.assertIn(updater.RELEASES_URL, message)

    def test_extract_failure_named_separately(self):
        """下载成功但包坏了要说「解压失败」，跟下载失败混成一句用户没法判断"""
        with mock.patch.object(updater.requests, 'get',
                               return_value=self.FakeResp(b'not a zip')):
            with self.assertRaises(updater.UpdateError) as caught:
                updater._download('0.3.0')
        self.assertIn('BadZipFile', str(caught.exception))
        self.assertNotIn('HTTPS_PROXY', str(caught.exception))

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

    def test_rename_failure_keeps_install(self):
        """改名失败就整个放弃，现有安装原样保留"""
        with mock.patch.object(Path, 'rename',
                               side_effect=OSError('Access is denied')):
            with self.assertRaises(updater.UpdateError):
                updater._replace(self.new, self.target)
        self.assertTrue((self.root / 'Kuraya').is_dir())
        self.assertEqual((self.target / 'old.txt').read_text(), 'old')


class ReplaceInPlace(unittest.TestCase):
    """
    Windows 上目录改不了名（里面的 exe 与 dll 正被本进程加载），只能逐个文件换：
    旧文件改名让位，新文件就位，当场换完。
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.target = self.root / 'Kuraya'
        (self.target / '_internal').mkdir(parents=True)
        (self.target / 'Kuraya.exe').write_text('v1')
        (self.target / '_internal' / 'python313.dll').write_text('dll v1')
        (self.target / '_internal' / 'gone.pyd').write_text('上一版才有的')
        self.new = self.root / 'new'
        (self.new / '_internal').mkdir(parents=True)
        (self.new / 'Kuraya.exe').write_text('v2')
        (self.new / '_internal' / 'python313.dll').write_text('dll v2')
        (self.new / '_internal' / 'added.pyd').write_text('新版才有的')

    def aside(self, *parts):
        return self.target.joinpath(*parts).with_name(
            parts[-1] + updater.OLD_SUFFIX)

    def test_files_replaced_without_touching_the_directory(self):
        """目录本身自始至终没动过——它改不了名，这正是整套办法的前提"""
        stat_before = self.target.stat()
        updater._replace_in_place(self.new, self.target)
        self.assertEqual(self.target.stat().st_ino, stat_before.st_ino)
        self.assertEqual((self.target / 'Kuraya.exe').read_text(), 'v2')
        self.assertEqual(
            (self.target / '_internal' / 'python313.dll').read_text(), 'dll v2')

    def test_old_files_are_renamed_not_deleted(self):
        """本进程加载着旧文件，删不掉，只能改名留到下次启动"""
        updater._replace_in_place(self.new, self.target)
        self.assertEqual(self.aside('Kuraya.exe').read_text(), 'v1')
        self.assertEqual(
            self.aside('_internal', 'python313.dll').read_text(), 'dll v1')

    def test_new_file_added(self):
        updater._replace_in_place(self.new, self.target)
        self.assertEqual(
            (self.target / '_internal' / 'added.pyd').read_text(), '新版才有的')

    def test_obsolete_file_moved_aside(self):
        """新版没有的旧文件也要让位，否则上一版的残留会一直留着"""
        updater._replace_in_place(self.new, self.target)
        self.assertFalse((self.target / '_internal' / 'gone.pyd').exists())
        self.assertEqual(
            self.aside('_internal', 'gone.pyd').read_text(), '上一版才有的')

    def test_rollback_leaves_install_untouched(self):
        """半新半旧的程序目录是启动不起来的：中途失败必须整体退回去"""
        real_move = updater.shutil.move
        calls = {'n': 0}

        def flaky(src, dst):
            calls['n'] += 1
            if calls['n'] == 2:
                raise OSError('locked')
            return real_move(src, dst)

        with mock.patch.object(updater.shutil, 'move', flaky):
            with self.assertRaises(updater.UpdateError):
                updater._replace_in_place(self.new, self.target)

        self.assertEqual((self.target / 'Kuraya.exe').read_text(), 'v1')
        self.assertEqual(
            (self.target / '_internal' / 'python313.dll').read_text(), 'dll v1')
        self.assertEqual(
            (self.target / '_internal' / 'gone.pyd').read_text(), '上一版才有的')
        self.assertFalse((self.target / '_internal' / 'added.pyd').exists())
        left = list(self.target.rglob(f'*{updater.OLD_SUFFIX}'))
        self.assertEqual(left, [])

    def test_undeletable_leftover_gets_another_name(self):
        """同一次运行里连更两版：上一版的让位文件还被加载着删不掉，
        这一次得往后排一个，不能卡在上次的残留上"""
        stuck = self.target / f'Kuraya.exe{updater.OLD_SUFFIX}'
        stuck.write_text('v0')
        with mock.patch.object(updater.Path, 'unlink',
                               side_effect=OSError('still loaded')):
            updater._replace_in_place(self.new, self.target)
        self.assertEqual((self.target / 'Kuraya.exe').read_text(), 'v2')
        self.assertEqual(stuck.read_text(), 'v0')
        self.assertEqual(
            (self.target / f'Kuraya.exe.1{updater.OLD_SUFFIX}').read_text(), 'v1')

    def test_failure_carries_winerror(self):
        """占用类失败要带上 Windows 的原话，用户才知道是杀软还是权限"""
        exc = OSError('Access is denied')
        exc.winerror = 5
        with mock.patch.object(updater.shutil, 'move', side_effect=exc):
            with self.assertRaises(updater.UpdateError) as caught:
                updater._replace_in_place(self.new, self.target)
        self.assertEqual(caught.exception.winerror, 5)


class SweepOld(unittest.TestCase):
    """让位的旧文件本进程删不掉（还加载着），下次启动没人加载了才删得掉"""

    def setUp(self):
        self.target = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.target, ignore_errors=True)
        (self.target / '_internal').mkdir()
        (self.target / f'Kuraya.exe{updater.OLD_SUFFIX}').write_text('v1')
        (self.target / '_internal' / f'a.dll{updater.OLD_SUFFIX}').write_text('x')
        (self.target / 'Kuraya.exe').write_text('v2')

    def sweep(self):
        with mock.patch.object(updater, 'FROZEN', True):
            updater.sweep_old(self.target)

    def test_old_files_removed(self):
        self.sweep()
        self.assertEqual(list(self.target.rglob(f'*{updater.OLD_SUFFIX}')), [])

    def test_current_files_kept(self):
        self.sweep()
        self.assertEqual((self.target / 'Kuraya.exe').read_text(), 'v2')

    def test_undeletable_leftover_is_ignored(self):
        """删不掉只是占盘，不值得打断启动"""
        with mock.patch.object(updater.Path, 'unlink',
                               side_effect=OSError('still locked')):
            self.sweep()
        self.assertTrue((self.target / f'Kuraya.exe{updater.OLD_SUFFIX}').exists())

    def test_source_install_skipped(self):
        """没打包就没有更新这回事，别去翻源码目录"""
        with mock.patch.object(updater, 'FROZEN', False):
            updater.sweep_old(self.target)
        self.assertTrue((self.target / f'Kuraya.exe{updater.OLD_SUFFIX}').exists())


if __name__ == '__main__':
    unittest.main()
