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

    def run_uninstall(self, answer='y', frozen=True, win32=False, darwin=False,
                      executable='/opt/Kuraya/Kuraya'):
        with mock.patch.object(main, 'FROZEN', frozen), \
                mock.patch.object(main.sys, 'platform',
                                  'win32' if win32
                                  else ('darwin' if darwin else 'linux')), \
                mock.patch.object(main.sys, 'executable', executable), \
                mock.patch('builtins.input', return_value=answer), \
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
        rmtree.assert_not_called()


if __name__ == '__main__':
    unittest.main()
