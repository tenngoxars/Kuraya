# -*- coding: utf-8 -*-
"""
`kuraya update` 命令流程与 brew 升级分支。

    python -m unittest discover tests
"""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kuraya import updater
from updater_support import patch_config


class UpdateCommand(unittest.TestCase):
    """`kuraya update` 命令的完整流程"""

    def setUp(self):
        self.tmp = patch_config()
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
                        mock.patch('builtins.input',
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
                mock.patch('builtins.input', return_value='y'), \
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
                                  return_value=(True, '0.4.0', False, '')) as run:
            self.assertEqual(updater.update(yes=True), 0)
        run.assert_called_once()

    def test_brew_quiet_reports_version(self):
        exe = '/opt/homebrew/Cellar/kuraya/0.3.0/libexec/Kuraya/Kuraya'
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch.object(updater, '_run_brew_upgrade',
                                  return_value=(True, '0.4.0', False, '')):
            self.assertEqual(updater.update(yes=True, quiet=True), 0)

    def test_brew_failure_reported(self):
        exe = '/opt/homebrew/Cellar/kuraya/0.3.0/libexec/Kuraya/Kuraya'
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch.object(updater, '_run_brew_upgrade',
                                  return_value=(False, '', False, '')):
            self.assertEqual(updater.update(yes=True), 1)

    def test_brew_confirm_cancels(self):
        """委托前确认，Esc/n 取消"""
        exe = '/opt/homebrew/Cellar/kuraya/0.3.0/libexec/Kuraya/Kuraya'
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch('builtins.input', return_value='n'), \
                mock.patch.object(updater, '_run_brew_upgrade') as run:
            self.assertEqual(updater.update(), 0)
        run.assert_not_called()

    def test_run_brew_upgrade_success(self):
        """升级成功：先刷新 tap，退出码 0 且无 up-to-date → 取新版本"""
        with mock.patch.object(updater.subprocess, 'run') as run:
            run.side_effect = [
                mock.Mock(returncode=0, stdout='/tmp/tap', stderr=''),
                mock.Mock(returncode=0, stdout='Already up to date.', stderr=''),
                mock.Mock(returncode=0, stdout='==> Upgrading kuraya\n',
                          stderr=''),
                mock.Mock(returncode=0, stdout='kuraya 0.4.0\n', stderr=''),
            ]
            self.assertEqual(updater._run_brew_upgrade(),
                             (True, '0.4.0', False, ''))

    def test_run_brew_upgrade_already_latest(self):
        with mock.patch.object(updater.subprocess, 'run') as run:
            run.side_effect = [
                mock.Mock(returncode=0, stdout='/tmp/tap', stderr=''),
                mock.Mock(returncode=0, stdout='Already up to date.', stderr=''),
                mock.Mock(returncode=0,
                          stdout='kuraya 0.4.0 already up-to-date\n',
                          stderr=''),
            ]
            self.assertEqual(updater._run_brew_upgrade(),
                             (True, '', True, ''))

    def test_run_brew_upgrade_missing_brew(self):
        with mock.patch.object(updater.subprocess, 'run',
                               side_effect=FileNotFoundError):
            self.assertEqual(updater._run_brew_upgrade(),
                             (False, '', False, ''))

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

    def test_quiet_routes_pending_failure_to_stderr(self):
        """quiet 的 stdout 只留 updated= 一行给脚本判断，但上次更新失败的原因
        不能因此丢掉——日志在 _pending_failure 里已被删除，这是它最后一次露面"""
        import io
        from contextlib import redirect_stdout, redirect_stderr
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(updater, 'latest', return_value='0.2.3'), \
                self.frozen()[0], self.frozen()[1], \
                mock.patch.object(
                    updater, '_pending_failure',
                    return_value='上次更新未完成：Access is denied'), \
                redirect_stdout(out), redirect_stderr(err):
            code = updater.update(yes=True, quiet=True)
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), 'updated=none')
        self.assertIn('Access is denied', err.getvalue())

    def test_quiet_none_output(self):
        with mock.patch.object(updater, 'latest',
                               return_value='0.2.3'), \
                self.frozen()[0], self.frozen()[1]:
            self.assertEqual(updater.update(yes=True, quiet=True), 0)


class BrewUpgrade(unittest.TestCase):
    """brew 分支：每次升级前无条件刷新 tap（防 formula 停旧版装旧版），
    已是最新用新旧 brew 措辞判定"""

    def run_upgrade(self, outcomes, quiet=True):
        with mock.patch.object(updater.subprocess, 'run',
                               side_effect=outcomes) as run:
            result = updater._run_brew_upgrade(quiet=quiet)
        return result, run

    def test_tap_refreshed_before_upgrade(self):
        """每次升级先 git pull 刷新 tap（formula 停在旧版时直接 upgrade
        会「成功」升到旧版，永远追不上最新），刷新失败也继续尝试"""
        outcomes = [
            mock.Mock(returncode=0, stdout='/opt/homebrew/Library/Taps/'
                                           'tenngoxars/homebrew-tap', stderr=''),
            mock.Mock(returncode=0, stdout='Already up to date.', stderr=''),
            mock.Mock(returncode=0, stdout='', stderr=''),
            mock.Mock(returncode=0, stdout='kuraya 0.5.12', stderr=''),
        ]
        (ok, version, already, _err), run = self.run_upgrade(outcomes)
        self.assertTrue(ok)
        self.assertEqual(version, '0.5.12')
        self.assertFalse(already)
        calls = [c.args[0] for c in run.call_args_list]
        self.assertEqual(calls[0][:2], ['brew', '--repository'])
        self.assertEqual(calls[0][2], updater.TAP)
        self.assertEqual(calls[1][:2], ['git', '-C'])
        self.assertEqual(calls[2][:2], ['brew', 'upgrade'])
        self.assertEqual(calls[3][:2], ['brew', 'list'])

    def test_tap_refresh_failure_still_upgrades(self):
        """tap 刷新失败（网络等）不阻断升级尝试"""
        outcomes = [
            mock.Mock(returncode=0, stdout='', stderr=''),   # --repository 空
            mock.Mock(returncode=0, stdout='', stderr=''),   # upgrade
            mock.Mock(returncode=0, stdout='kuraya 0.5.12', stderr=''),
        ]
        (ok, version, already, _err), _ = self.run_upgrade(outcomes)
        self.assertTrue(ok)
        self.assertEqual(version, '0.5.12')
        self.assertFalse(already)

    def test_upgrade_disables_auto_update(self):
        """upgrade 禁用 brew 自动更新（避免卡在 Updating Homebrew）"""
        outcomes = [
            mock.Mock(returncode=0, stdout='/tmp/tap', stderr=''),
            mock.Mock(returncode=0, stdout='Already up to date.', stderr=''),
            mock.Mock(returncode=0,
                      stdout='kuraya 0.5.12 already up-to-date.', stderr=''),
        ]
        (_, _, _, _), run = self.run_upgrade(outcomes)
        env = run.call_args_list[2].kwargs['env']  # 第三次调用是 upgrade
        self.assertEqual(env['HOMEBREW_NO_AUTO_UPDATE'], '1')

    def test_still_up_to_date_after_refresh(self):
        """刷新后仍 up-to-date 才是真的最新"""
        outcomes = [
            mock.Mock(returncode=0, stdout='/tmp/tap', stderr=''),
            mock.Mock(returncode=0, stdout='Already up to date.', stderr=''),
            mock.Mock(returncode=0,
                      stdout='kuraya 0.5.12 already up-to-date.', stderr=''),
        ]
        ok, version, already, _err = self.run_upgrade(outcomes)[0]
        self.assertTrue(ok)
        self.assertEqual(version, '')
        self.assertTrue(already)

    def test_brew_missing_returns_failure(self):
        """brew 不存在时 tap 刷新与 upgrade 都失败，返回失败"""
        outcomes = [OSError('no brew'), OSError('no brew'), OSError('no brew')]
        (ok, version, already, _err), _ = self.run_upgrade(outcomes)
        self.assertFalse(ok)
        self.assertEqual(version, '')
        self.assertFalse(already)

    def test_already_installed_wording(self):
        """现代 brew 对已最新的输出是 Warning: ... already installed
        （不含 up-to-date），同样按「已是最新」处理，不误报已更新"""
        outcomes = [
            mock.Mock(returncode=0, stdout='/tmp/tap', stderr=''),
            mock.Mock(returncode=0, stdout='Already up to date.', stderr=''),
            mock.Mock(returncode=0, stdout='Warning: '
                       'tenngoxars/tap/kuraya 0.5.18 already installed',
                       stderr=''),
        ]
        ok, version, already, _err = self.run_upgrade(outcomes)[0]
        self.assertTrue(ok)
        self.assertEqual(version, '')
        self.assertTrue(already)

    def test_failure_carries_brew_error(self):
        """brew 失败时带回它自己的报错（如未信任 tap 会给出 brew trust
        命令）：吞掉再让用户手动重跑等于没给诊断。只取末尾几行"""
        noise = '\n'.join(f'==> line {i}' for i in range(20))
        outcomes = [
            mock.Mock(returncode=0, stdout='/tmp/tap', stderr=''),
            mock.Mock(returncode=0, stdout='Already up to date.', stderr=''),
            mock.Mock(returncode=1, stdout=noise + '\n\n',
                      stderr='Error: Refusing to load formula '
                             'tenngoxars/tap/kuraya from untrusted tap.\n'
                             'Run `brew trust tenngoxars/tap` to trust it.\n'),
        ]
        ok, version, already, err = self.run_upgrade(outcomes)[0]
        self.assertFalse(ok)
        self.assertEqual(version, '')
        self.assertFalse(already)
        self.assertIn('brew trust tenngoxars/tap', err)
        self.assertEqual(len(err.splitlines()), updater.ERROR_LINES)
        self.assertNotIn('\n\n', err)          # 空行剔掉不刷屏

    def test_failure_error_surfaced_to_user(self):
        """报错要真的打到用户眼前，不是只存在返回值里"""
        import io
        from contextlib import redirect_stdout
        exe = '/opt/homebrew/Cellar/kuraya/0.3.0/libexec/Kuraya/Kuraya'
        err = 'Run `brew trust tenngoxars/tap` to trust it.'
        buffer = io.StringIO()
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch.object(updater, '_run_brew_upgrade',
                                  return_value=(False, '', False, err)), \
                redirect_stdout(buffer):
            code = updater.update(yes=True)
        self.assertEqual(code, 1)
        self.assertIn('brew trust tenngoxars/tap', buffer.getvalue())

    def test_quiet_keeps_stdout_parseable(self):
        """quiet 的一行契约给脚本用，报错走 stderr 不掺进去"""
        import io
        from contextlib import redirect_stdout, redirect_stderr
        exe = '/opt/homebrew/Cellar/kuraya/0.3.0/libexec/Kuraya/Kuraya'
        err = 'Error: Refusing to load formula'
        out, errbuf = io.StringIO(), io.StringIO()
        with mock.patch.object(updater, 'FROZEN', True), \
                mock.patch.object(updater.sys, 'platform', 'darwin'), \
                mock.patch.object(updater.sys, 'executable', exe), \
                mock.patch.object(updater, '_run_brew_upgrade',
                                  return_value=(False, '', False, err)), \
                redirect_stdout(out), redirect_stderr(errbuf):
            code = updater.update(yes=True, quiet=True)
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue().strip(), 'updated=error')
        self.assertIn(err, errbuf.getvalue())

    def test_tap_refresh_failure_warns(self):
        """tap 刷新失败时提示可能非最新（formula 停旧版会装旧版），
        quiet 模式不输出"""
        import io
        from contextlib import redirect_stdout
        outcomes = [
            mock.Mock(returncode=0, stdout='', stderr=''),   # --repository 空
            mock.Mock(returncode=0, stdout='', stderr=''),   # upgrade
            mock.Mock(returncode=0, stdout='kuraya 0.5.12', stderr=''),
        ]
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            (ok, version, _, _), _ = self.run_upgrade(outcomes, quiet=False)
        self.assertTrue(ok)
        self.assertIn('tap 刷新失败', buffer.getvalue())
        # quiet 模式静默
        buffer2 = io.StringIO()
        with redirect_stdout(buffer2):
            self.run_upgrade(outcomes)
        self.assertEqual(buffer2.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
