# -*- coding: utf-8 -*-
"""
`kuraya uninstall`：确认后移除命令入口与程序文件；
brew / 源码安装走对应提示，Windows 因运行中 exe 无法自删而提示手动。

    python -m unittest discover tests
"""
import unittest
from unittest import mock

from kuraya import __main__ as main
from kuraya import i18n as _i18n

_i18n._lang = _i18n.ZH_CN


class Uninstall(unittest.TestCase):
    """卸载流程：确认 → PATH → shim → 程序目录"""

    def run_uninstall(self, answer='y', cfg_answer='n', frozen=True,
                      win32=False, darwin=False,
                      executable='/opt/Kuraya/Kuraya'):
        with mock.patch.object(main, 'FROZEN', frozen), \
                mock.patch.object(main.sys, 'platform',
                                  'win32' if win32
                                  else ('darwin' if darwin else 'linux')), \
                mock.patch.object(main.sys, 'executable', executable), \
                mock.patch('builtins.input',
                           side_effect=[answer, cfg_answer]), \
                mock.patch('kuraya.pathenv.uninstall',
                           return_value=(True, '')), \
                mock.patch('shutil.rmtree') as rmtree:
            code = main.do_uninstall()
        return code, rmtree

    def test_confirms_and_removes(self):
        code, rmtree = self.run_uninstall()
        self.assertEqual(code, 0)
        rmtree.assert_called()          # 删除程序目录
        rmtree.assert_any_call(mock.ANY, ignore_errors=True)  # 壳 app

    def test_confirms_and_removes_config(self):
        """确认卸载并确认删除配置：配置目录一并移除"""
        code, rmtree = self.run_uninstall(cfg_answer='y')
        self.assertEqual(code, 0)
        rmtree.assert_any_call(main.settings.APP_DIR)  # 配置目录

    def test_config_kept_by_default(self):
        """配置询问默认保留：不回 y 就不删配置目录"""
        code, rmtree = self.run_uninstall()
        self.assertEqual(code, 0)
        for call in rmtree.call_args_list:
            self.assertNotEqual(call.args[0], main.settings.APP_DIR)

    def test_config_missing_not_an_error(self):
        """从未运行过（配置目录不存在）：确认删除也不误报失败"""
        with mock.patch.object(main, 'FROZEN', True), \
                mock.patch.object(main.sys, 'platform', 'linux'), \
                mock.patch.object(main.sys, 'executable', '/opt/Kuraya/Kuraya'), \
                mock.patch('builtins.input', side_effect=['y', 'y']), \
                mock.patch('kuraya.pathenv.uninstall',
                           return_value=(True, '')), \
                mock.patch.object(main.settings, 'APP_DIR',
                                  main.Path('/nonexistent/kuraya-config')), \
                mock.patch('shutil.rmtree') as rmtree:
            code = main.do_uninstall()
        self.assertEqual(code, 0)
        # 配置目录不存在：不应触发对它的删除调用
        for call in rmtree.call_args_list:
            self.assertNotEqual(call.args[0],
                                main.Path('/nonexistent/kuraya-config'))

    def test_cancel_keeps_everything(self):
        code, rmtree = self.run_uninstall(answer='n')
        self.assertEqual(code, 0)
        rmtree.assert_not_called()

    def test_brew_rejected(self):
        """Homebrew 安装由 brew 管理，不自行删除"""
        code, _ = self.run_uninstall(
            darwin=True,
            executable='/opt/homebrew/Cellar/kuraya/0.5.7/libexec/Kuraya/Kuraya')
        self.assertEqual(code, 1)

    def test_source_install_rejected(self):
        code, _ = self.run_uninstall(frozen=False)
        self.assertEqual(code, 1)

    def test_windows_manual_removal(self):
        """Windows 上运行中的 exe 无法自删，提示手动删除"""
        code, rmtree = self.run_uninstall(win32=True)
        self.assertEqual(code, 0)
        # Windows 分支不删程序目录，只可能删配置（cfg_answer 默认 n）
        rmtree.assert_not_called()


class FallbackError(unittest.TestCase):
    """未预料异常的兜底处理器能正常工作（曾因 setup 未导入而自身 NameError）"""

    def test_fallback_shows_error(self):
        with mock.patch.object(main.sys, 'argv', ['kuraya', 'rebuild']), \
             mock.patch.object(main, 'FROZEN', False), \
             mock.patch.object(main, 'resolve_paths',
                               side_effect=RuntimeError('boom')), \
             mock.patch('kuraya.protocol.ensure_shell_app'), \
             mock.patch('kuraya.protocol.ensure_registered'), \
             mock.patch('kuraya.console.enable_ansi'), \
             mock.patch('kuraya.launcher.say'), \
             mock.patch('kuraya.launcher.spin'), \
             mock.patch('kuraya.updater.show'), \
             mock.patch('kuraya.setup.show_error') as show:
            code = main.main()
        self.assertEqual(code, main.CONFIG_ERROR)
        show.assert_called_once()
        self.assertIn('boom', show.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
