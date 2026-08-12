# -*- coding: utf-8 -*-
"""
更新检查：版本比较、最新版本缓存、安装包地址、安装形态与提示文案。

    python -m unittest discover tests
"""
import shutil
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from kuraya import settings, updater
from updater_support import patch_config


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
        self.tmp = patch_config()
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

    def test_failure_cache_expires_after_an_hour(self):
        """失败缓存只顶 1 小时：离线不反复等超时，网络恢复后很快重新检查"""
        yesterday = str(int(time.time()) - 2 * 24 * 3600)
        settings.save_update_state(yesterday, '')
        mock.patch.object(updater.requests, 'get',
                          self.fake_get(exc=updater.requests.
                                        RequestException('boom'))).start()
        self.addCleanup(mock.patch.stopall)
        self.assertIsNone(updater.latest())
        state = settings.update_state()
        # checked 被倒拨：实际只剩余 1 小时有效期，而不是一整天
        self.assertLessEqual(float(state['checked']),
                             int(time.time()) - updater.CHECK_INTERVAL
                             + updater.FAIL_INTERVAL + 5)
        self.assertEqual(state['latest'], '')


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


class InstallerDetection(unittest.TestCase):
    """安装形态检测：install.ps1 装的目录给安装命令提示，解压版给下载页"""

    def installed(self, target, local_appdata):
        with mock.patch.object(updater.os, 'name', 'nt'), \
             mock.patch.dict(updater.os.environ,
                             {'LOCALAPPDATA': local_appdata}):
            return updater._installer_installed(target)

    def test_programs_kuraya_is_installer(self):
        """install.ps1 安装形态：%LOCALAPPDATA%\\Programs\\Kuraya"""
        base = '/Users/me/AppData/Local'
        self.assertTrue(
            self.installed(f'{base}/Programs/Kuraya', base))

    def test_arbitrary_folder_is_extracted(self):
        """解压版：任意目录不是安装形态"""
        self.assertFalse(
            self.installed('/Users/me/Downloads/Kuraya',
                           '/Users/me/AppData/Local'))

    def test_non_windows_false(self):
        """非 Windows 恒为 False（brew 走自己的分支）"""
        with mock.patch.object(updater.os, 'name', 'posix'):
            self.assertFalse(
                updater._installer_installed(Path('/opt/Kuraya')))


class NoticeText(unittest.TestCase):
    def setUp(self):
        self.tmp = patch_config()
        self.addCleanup(self.tmp.cleanup)

    def test_empty_when_no_update(self):
        settings.save_update_state(str(int(time.time())), '0.2.3')
        self.assertEqual(updater.text(), '')

    def test_empty_when_nothing_cached(self):
        self.assertEqual(updater.text(), '')

    def test_mentions_new_and_current_version(self):
        """当前版本以旧缓存版本为基准，模拟用户还没升级"""
        with mock.patch('kuraya.updater.__version__', '0.1.0'):
            settings.save_update_state(str(int(time.time())), '9.9.9')
            notice = updater.text()
        self.assertIn('发现新版本 v9.9.9', notice)
        self.assertIn('v0.1.0', notice)
        self.assertIn('kuraya update', notice)
        self.assertIn('releases/latest', notice)

    def test_respects_current_version(self):
        """GitHub 版本等于当前版本时无提示（模拟已是最新）"""
        with mock.patch('kuraya.updater.__version__', '9.9.9'):
            settings.save_update_state(str(int(time.time())), '9.9.9')
            self.assertEqual(updater.text(), '')


class Show(unittest.TestCase):
    def setUp(self):
        self.tmp = patch_config()
        self.addCleanup(self.tmp.cleanup)
        updater._shown = False
        self.addCleanup(setattr, updater, '_shown', False)
        # 测试进程自身不是交互终端，show() 会整个跳过。基线上假定屏幕前
        # 有人，各用例才测得到自己那个条件而不是一律沉默
        tty = mock.patch('kuraya.console.interactive', return_value=True)
        tty.start()
        self.addCleanup(tty.stop)

    def test_prints_once_when_update(self):
        settings.save_update_state(str(int(time.time())), '9.9.9')
        with mock.patch('kuraya.console.say') as say, \
                mock.patch('kuraya.updater.__version__', '0.1.0'):
            updater.show()
            updater.show()
        self.assertEqual(say.call_count, 1)
        self.assertIn('发现新版本 v9.9.9', say.call_args[0][0])

    def test_silent_when_not_interactive(self):
        """管道与定时任务里不提示：没人看，还白等一次联网查版本"""
        settings.save_update_state(str(int(time.time())), '9.9.9')
        with mock.patch('kuraya.console.interactive', return_value=False), \
                mock.patch('kuraya.console.say') as say, \
                mock.patch('kuraya.updater.__version__', '0.1.0'):
            updater.show()
        say.assert_not_called()

    def test_silent_in_quiet_mode(self):
        settings.save_update_state(str(int(time.time())), '9.9.9')
        with mock.patch('kuraya.console.QUIET', True), \
                mock.patch('kuraya.console.say') as say:
            updater.show()
        say.assert_not_called()

    def test_silent_without_update(self):
        settings.save_update_state(str(int(time.time())), '0.2.3')
        with mock.patch('kuraya.console.say') as say:
            updater.show()
        say.assert_not_called()

    def test_reports_failed_deferred_update(self):
        """延迟替换失败后用户重开程序，正是他纳闷「怎么还是旧版本」的时刻，
        这一刻必须把盘上那条原因说出来"""
        settings.save_update_state(str(int(time.time())), '0.2.3')
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / 'kuraya-update-xyz').mkdir()
        (tmp / 'kuraya-update-xyz' / 'update.log').write_text(
            'FAIL: Access to the path is denied', encoding='utf-8')
        with mock.patch.object(updater.sys, 'platform', 'win32'), \
                mock.patch.object(updater.tempfile, 'gettempdir',
                                  return_value=str(tmp)), \
                mock.patch.object(updater, 'FROZEN', True), \
                mock.patch('kuraya.console.say') as say:
            updater.show()
        self.assertIn('Access to the path is denied', say.call_args[0][0])


class PendingNotice(unittest.TestCase):
    """启动恢复：延迟替换失败后重开程序，不能只提示——还要重新安排"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def patch(self):
        """进入 win32 + FROZEN + 临时目录的 mock 栈；_replace_later 的
        mock 挂在 self.replace_mock 上供断言"""
        stack = ExitStack()
        stack.enter_context(mock.patch.object(updater.sys, 'platform', 'win32'))
        stack.enter_context(mock.patch.object(updater.tempfile, 'gettempdir',
                                              return_value=str(self.tmp)))
        stack.enter_context(mock.patch.object(updater, 'FROZEN', True))
        self.replace_mock = stack.enter_context(
            mock.patch.object(updater, '_replace_later', return_value=True))
        return stack

    def _log(self, name, content):
        d = self.tmp / name
        d.mkdir()
        (d / 'update.log').write_text(content, encoding='utf-8')
        return d

    def test_fail_with_intact_new_dir_reschedules(self):
        """FAIL 且新版本完整：脚本已超时退出，必须重新安排替换，
        否则用户退出重开还是旧版本"""
        d = self._log('kuraya-update-a', 'FAIL: Access denied')
        (d / 'x' / 'Kuraya').mkdir(parents=True)
        (d / 'x' / 'Kuraya' / 'Kuraya.exe').write_bytes(b'')
        with self.patch():
            notice = updater.pending_notice()
        self.replace_mock.assert_called_once()
        self.assertIn('已重新安排', notice)
        self.assertIn('Access denied', notice)

    def test_fail_without_new_dir_only_hints(self):
        """FAIL 但新版本已不在（下载目录被清）：没法重排，给下载页引导"""
        self._log('kuraya-update-b', 'FAIL: boom')
        with self.patch():
            notice = updater.pending_notice()
        self.replace_mock.assert_not_called()
        self.assertIn('boom', notice)

    def test_pending_only_asks_to_exit(self):
        """PENDING：脚本可能还在等程序退出（用户重开又锁上了目录），
        提示退出等待即可，重复安排会两个脚本抢替换"""
        self._log('kuraya-update-c', 'PENDING')
        with self.patch():
            notice = updater.pending_notice()
        self.replace_mock.assert_not_called()
        self.assertIn('尚未完成', notice)

    def test_ok_leftover_cleaned(self):
        """OK 残留（脚本自清失败）不提示，顺手清掉"""
        d = self._log('kuraya-update-d', 'OK')
        with self.patch():
            notice = updater.pending_notice()
        self.assertEqual(notice, '')
        self.replace_mock.assert_not_called()
        self.assertFalse(d.exists())

    def test_old_fail_entries_cleaned_newest_rescheduled(self):
        """多份残留只处理最新一份：对每份都重排会让多个脚本抢同一处替换，
        旧目录的新版本要么已被接管要么不完整，直接清掉"""
        old = self._log('kuraya-update-old', 'FAIL: old failure')
        (old / 'x' / 'Kuraya').mkdir(parents=True)
        (old / 'x' / 'Kuraya' / 'Kuraya.exe').write_bytes(b'')
        newest = self._log('kuraya-update-new', 'FAIL: new failure')
        (newest / 'x' / 'Kuraya').mkdir(parents=True)
        (newest / 'x' / 'Kuraya' / 'Kuraya.exe').write_bytes(b'')
        # 让 newest 的 mtime 确定性地晚于 old
        future = old.stat().st_mtime + 60
        import os as _os
        _os.utime(newest / 'update.log', (future, future))
        with self.patch():
            notice = updater.pending_notice()
        self.replace_mock.assert_called_once()
        self.assertIn('new failure', notice)
        self.assertNotIn('old failure', notice)
        self.assertFalse(old.exists())

    def test_non_windows_noop(self):
        """非 Windows 平台没有延迟替换这回事"""
        self._log('kuraya-update-e', 'FAIL: boom')
        with mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater, 'FROZEN', True):
            self.assertEqual(updater.pending_notice(), '')


if __name__ == '__main__':
    unittest.main()
