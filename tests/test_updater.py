# -*- coding: utf-8 -*-
"""
更新检查。

    python -m unittest discover tests
"""
import shutil
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from kuraya import i18n as _i18n
_i18n._lang = _i18n.ZH_CN  # 测试断言简体中文文案，固定语言

from kuraya import settings, updater


def _patch_config():
    """把配置指向临时文件，让缓存读写走真实路径"""
    tmp = tempfile.TemporaryDirectory()
    target = Path(tmp.name) / '设置.ini'
    patcher = mock.patch.object(settings, 'SETTINGS_FILE', target)
    patcher.start()
    return tmp


class VersionCompare(unittest.TestCase):
    def test_newer(self):
        self.assertTrue(updater.is_newer('0.3.0', '0.2.3'))

    def test_v_prefix_tolerated(self):
        self.assertTrue(updater.is_newer('v0.3.0', '0.2.3'))

    def test_same_version(self):
        self.assertFalse(updater.is_newer('0.2.3', '0.2.3'))

    def test_older(self):
        self.assertFalse(updater.is_newer('0.2.2', '0.2.3'))

    def test_numeric_not_lexicographic(self):
        """0.10.0 大于 0.9.9，不能按字符串比"""
        self.assertTrue(updater.is_newer('0.10.0', '0.9.9'))

    def test_more_segments_wins(self):
        self.assertTrue(updater.is_newer('1.0', '0.9.9'))


class Latest(unittest.TestCase):
    def setUp(self):
        self.tmp = _patch_config()
        self.addCleanup(self.tmp.cleanup)

    def fake_get(self, tag=None, status=200, exc=None):
        resp = mock.Mock(status_code=status)
        resp.json.return_value = {'tag_name': tag}
        if exc is not None:
            return mock.Mock(side_effect=exc)
        return mock.Mock(return_value=resp)

    def test_fresh_cache_skips_request(self):
        """24 小时内直接复用上次结果，不发请求"""
        settings.save_update_state(str(int(time.time())), '9.9.9')
        with mock.patch.object(updater.requests, 'get') as get:
            self.assertEqual(updater.latest(), '9.9.9')
        get.assert_not_called()

    def test_first_run_fetches(self):
        get = mock.patch.object(updater.requests, 'get',
                                self.fake_get(tag='v9.9.9')).start()
        self.addCleanup(mock.patch.stopall)
        self.assertEqual(updater.latest(), '9.9.9')
        get.assert_called_once()

    def test_stale_cache_refetches_and_saves(self):
        yesterday = str(int(time.time()) - 2 * 24 * 3600)
        settings.save_update_state(yesterday, '0.2.3')
        mock.patch.object(updater.requests, 'get',
                          self.fake_get(tag='v9.9.9')).start()
        self.addCleanup(mock.patch.stopall)
        self.assertEqual(updater.latest(), '9.9.9')
        state = settings.update_state()
        self.assertEqual(state['latest'], '9.9.9')
        self.assertGreaterEqual(float(state['checked']), float(yesterday))

    def test_network_failure_returns_none(self):
        """连不上时静默返回 None，且写入失败缓存避免每次启动都等超时"""
        yesterday = str(int(time.time()) - 2 * 24 * 3600)
        settings.save_update_state(yesterday, '')
        exc = updater.requests.RequestException('boom')
        mock.patch.object(updater.requests, 'get', self.fake_get(exc=exc)).start()
        self.addCleanup(mock.patch.stopall)
        self.assertIsNone(updater.latest())
        # 失败已缓存，第二次不再请求
        with mock.patch.object(updater.requests, 'get') as get:
            self.assertIsNone(updater.latest())
        get.assert_not_called()

    def test_non_200_returns_none(self):
        yesterday = str(int(time.time()) - 2 * 24 * 3600)
        settings.save_update_state(yesterday, '')
        mock.patch.object(updater.requests, 'get',
                          self.fake_get(status=403)).start()
        self.addCleanup(mock.patch.stopall)
        self.assertIsNone(updater.latest())

    def test_missing_tag_returns_none(self):
        yesterday = str(int(time.time()) - 2 * 24 * 3600)
        settings.save_update_state(yesterday, '')
        mock.patch.object(updater.requests, 'get',
                          self.fake_get(tag=None)).start()
        self.addCleanup(mock.patch.stopall)
        self.assertIsNone(updater.latest())

    def test_garbage_timestamp_treated_as_stale(self):
        settings.save_update_state('不是时间', '0.2.3')
        mock.patch.object(updater.requests, 'get',
                          self.fake_get(tag='v9.9.9')).start()
        self.addCleanup(mock.patch.stopall)
        self.assertEqual(updater.latest(), '9.9.9')

    def test_force_bypasses_fresh_cache(self):
        """主动更新时总是重新请求，不信任缓存"""
        settings.save_update_state(str(int(time.time())), '0.2.3')
        mock.patch.object(updater.requests, 'get',
                          self.fake_get(tag='v9.9.9')).start()
        self.addCleanup(mock.patch.stopall)
        self.assertEqual(updater.latest(force=True), '9.9.9')


class AssetUrl(unittest.TestCase):
    """安装包地址按平台与架构选择，发行版没有的组合直接报错"""

    def url(self, platform, os_name, machine):
        with mock.patch.object(updater.sys, 'platform', platform), \
                mock.patch.object(updater.os, 'name', os_name), \
                mock.patch.object(updater.platform, 'machine',
                                  lambda: machine):
            return updater._asset_url('0.3.0')

    def test_macos_arm64(self):
        self.assertTrue(self.url('darwin', 'posix', 'arm64')
                        .endswith('Kuraya-0.3.0-mac-arm64.zip'))

    def test_windows(self):
        self.assertTrue(self.url('win32', 'nt', 'AMD64')
                        .endswith('Kuraya-0.3.0-win-x64.zip'))

    def test_linux_x86_64(self):
        self.assertTrue(self.url('linux', 'posix', 'x86_64')
                        .endswith('Kuraya-0.3.0-linux-x86_64.zip'))

    def test_intel_mac_rejected(self):
        with self.assertRaises(updater.UpdateError):
            self.url('darwin', 'posix', 'x86_64')

    def test_linux_arm64_rejected(self):
        with self.assertRaises(updater.UpdateError):
            self.url('linux', 'posix', 'aarch64')


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
        with tempfile.TemporaryDirectory() as tmp:
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


class UpdateCommand(unittest.TestCase):
    """`kuraya update` 命令的完整流程"""

    def setUp(self):
        self.tmp = _patch_config()
        self.addCleanup(self.tmp.cleanup)

    def frozen(self, exe=None):
        return mock.patch.object(
            updater, 'FROZEN', True), mock.patch.object(
            updater.sys, 'executable', exe or '/opt/kuraya/Kuraya/Kuraya')

    def test_already_latest(self):
        """没有新版本时直接告知，不下载"""
        with mock.patch.object(updater, 'latest',
                               return_value='0.2.3'), \
                self.frozen()[0], self.frozen()[1], \
                mock.patch.object(updater, '_download') as dl:
            code = updater.update(yes=True)
        self.assertEqual(code, 0)
        dl.assert_not_called()

    def test_check_failure(self):
        with mock.patch.object(updater, 'latest', return_value=None), \
                self.frozen()[0], self.frozen()[1]:
            self.assertEqual(updater.update(yes=True), 1)

    def test_cancel_keeps_install(self):
        """按 n 或 Esc 取消，不下载"""
        for key in ('n', 'esc'):
            with self.subTest(key=key):
                with mock.patch.object(updater, 'latest',
                                       return_value='9.9.9'), \
                        self.frozen()[0], self.frozen()[1], \
                        mock.patch('kuraya.keys.read_key',
                                   return_value=key), \
                        mock.patch.object(updater, '_download') as dl:
                    self.assertEqual(updater.update(), 0)
                dl.assert_not_called()

    def test_confirm_proceeds(self):
        new_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, new_dir, ignore_errors=True)
        (new_dir / 'Kuraya').mkdir()
        with mock.patch.object(updater, 'latest',
                               return_value='9.9.9'), \
                self.frozen()[0], self.frozen()[1], \
                mock.patch('kuraya.keys.read_key', return_value='y'), \
                mock.patch.object(updater, '_download',
                                  return_value=(new_dir, new_dir.parent)), \
                mock.patch.object(updater, '_replace') as rep:
            code = updater.update()
        self.assertEqual(code, 0)
        rep.assert_called_once()

    def test_source_install_rejected(self):
        """源码/pip 安装不自更新，提示用安装时的方式"""
        with mock.patch.object(updater, 'FROZEN', False), \
                mock.patch.object(updater.sys, 'executable',
                                  '/usr/bin/python3'):
            self.assertEqual(updater.update(yes=True), 1)

    def test_brew_delegates_to_brew_upgrade(self):
        """brew 安装时委托 brew upgrade（保持 brew 状态一致），不自行替换"""
        exe = '/opt/homebrew/Cellar/kuraya/0.3.0/libexec/Kuraya/Kuraya'
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch.object(updater, '_run_brew_upgrade',
                                  return_value=(True, '0.4.0', False)) as run:
            self.assertEqual(updater.update(yes=True), 0)
        run.assert_called_once()

    def test_brew_quiet_reports_version(self):
        exe = '/opt/homebrew/Cellar/kuraya/0.3.0/libexec/Kuraya/Kuraya'
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch.object(updater, '_run_brew_upgrade',
                                  return_value=(True, '0.4.0', False)):
            self.assertEqual(updater.update(yes=True, quiet=True), 0)

    def test_brew_failure_reported(self):
        exe = '/opt/homebrew/Cellar/kuraya/0.3.0/libexec/Kuraya/Kuraya'
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch.object(updater, '_run_brew_upgrade',
                                  return_value=(False, '', False)):
            self.assertEqual(updater.update(yes=True), 1)

    def test_brew_confirm_cancels(self):
        """委托前确认，Esc/n 取消"""
        exe = '/opt/homebrew/Cellar/kuraya/0.3.0/libexec/Kuraya/Kuraya'
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch('kuraya.keys.read_key', return_value='esc'), \
                mock.patch.object(updater, '_run_brew_upgrade') as run:
            self.assertEqual(updater.update(), 0)
        run.assert_not_called()

    def test_run_brew_upgrade_success(self):
        """升级成功：退出码 0 且输出无 up-to-date → 从 brew list 取新版本"""
        with mock.patch.object(updater.subprocess, 'run') as run:
            run.side_effect = [
                mock.Mock(returncode=0, stdout='==> Upgrading kuraya\n',
                          stderr=''),
                mock.Mock(returncode=0, stdout='kuraya 0.4.0\n', stderr=''),
            ]
            self.assertEqual(updater._run_brew_upgrade(),
                             (True, '0.4.0', False))

    def test_run_brew_upgrade_already_latest(self):
        with mock.patch.object(updater.subprocess, 'run') as run:
            run.return_value = mock.Mock(
                returncode=0, stdout='kuraya 0.4.0 already up-to-date\n',
                stderr='')
            self.assertEqual(updater._run_brew_upgrade(),
                             (True, '', True))

    def test_run_brew_upgrade_missing_brew(self):
        with mock.patch.object(updater.subprocess, 'run',
                               side_effect=FileNotFoundError):
            self.assertEqual(updater._run_brew_upgrade(),
                             (False, '', False))

    def test_quiet_output(self):
        new_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, new_dir, ignore_errors=True)
        (new_dir / 'Kuraya').mkdir()
        with mock.patch.object(updater, 'latest',
                               return_value='9.9.9'), \
                self.frozen()[0], self.frozen()[1], \
                mock.patch.object(updater, '_download',
                                  return_value=(new_dir, new_dir.parent)), \
                mock.patch.object(updater, '_replace'):
            code = updater.update(yes=True, quiet=True)
        self.assertEqual(code, 0)

    def test_quiet_none_output(self):
        with mock.patch.object(updater, 'latest',
                               return_value='0.2.3'), \
                self.frozen()[0], self.frozen()[1]:
            self.assertEqual(updater.update(yes=True, quiet=True), 0)


class NoticeText(unittest.TestCase):
    def setUp(self):
        self.tmp = _patch_config()
        self.addCleanup(self.tmp.cleanup)

    def test_empty_when_no_update(self):
        settings.save_update_state(str(int(time.time())), '0.2.3')
        self.assertEqual(updater.text(), '')

    def test_empty_when_nothing_cached(self):
        self.assertEqual(updater.text(), '')

    def test_mentions_new_and_current_version(self):
        """当前版本以旧缓存版本为基准，模拟用户还没升级"""
        with mock.patch('kuraya.__version__', '0.1.0'):
            settings.save_update_state(str(int(time.time())), '9.9.9')
            notice = updater.text()
        self.assertIn('发现新版本 v9.9.9', notice)
        self.assertIn('v0.1.0', notice)
        self.assertIn('kuraya update', notice)
        self.assertIn('releases/latest', notice)

    def test_respects_current_version(self):
        """GitHub 版本等于当前版本时无提示（模拟已是最新）"""
        with mock.patch('kuraya.__version__', '9.9.9'):
            settings.save_update_state(str(int(time.time())), '9.9.9')
            self.assertEqual(updater.text(), '')


class Show(unittest.TestCase):
    def setUp(self):
        self.tmp = _patch_config()
        self.addCleanup(self.tmp.cleanup)
        updater._shown = False
        self.addCleanup(setattr, updater, '_shown', False)

    def test_prints_once_when_update(self):
        settings.save_update_state(str(int(time.time())), '9.9.9')
        with mock.patch('kuraya.launcher.say') as say, \
                mock.patch('kuraya.__version__', '0.1.0'):
            updater.show()
            updater.show()
        self.assertEqual(say.call_count, 1)
        self.assertIn('发现新版本 v9.9.9', say.call_args[0][0])

    def test_silent_in_quiet_mode(self):
        settings.save_update_state(str(int(time.time())), '9.9.9')
        with mock.patch('kuraya.launcher.QUIET', True), \
                mock.patch('kuraya.launcher.say') as say:
            updater.show()
        say.assert_not_called()

    def test_silent_without_update(self):
        settings.save_update_state(str(int(time.time())), '0.2.3')
        with mock.patch('kuraya.launcher.say') as say:
            updater.show()
        say.assert_not_called()


if __name__ == '__main__':
    unittest.main()
