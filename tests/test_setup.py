# -*- coding: utf-8 -*-
"""
首次运行引导：PATH 安装征询。

    python -m unittest discover tests
"""
import unittest
from unittest import mock

from kuraya import setup


class OfferPathInstall(unittest.TestCase):
    """Windows 打包版首次运行的 PATH 征询（曾因 key 未定义而崩溃）"""

    def run_offer(self, answer='y', installed=False, path_asked=False):
        with mock.patch.object(setup.os, 'name', 'nt'), \
             mock.patch.object(setup.sys, 'frozen', True, create=True), \
             mock.patch('kuraya.pathenv.is_installed',
                        return_value=installed), \
             mock.patch('kuraya.settings.load',
                        return_value={'path_asked': path_asked}), \
             mock.patch('builtins.input', return_value=answer), \
             mock.patch('kuraya.settings.save'), \
             mock.patch('kuraya.pathenv.install',
                        return_value=(True, '')) as install:
            setup.offer_path_install()
        return install

    def test_confirm_installs(self):
        """输入 y 确认后登记 PATH"""
        install = self.run_offer('y')
        install.assert_called_once()

    def test_enter_skips(self):
        """直接回车跳过：不再追问、不安装"""
        install = self.run_offer('')
        install.assert_not_called()

    def test_non_windows_skipped(self):
        """非 Windows 不征询"""
        with mock.patch.object(setup.os, 'name', 'posix'), \
             mock.patch('kuraya.pathenv.install') as install:
            setup.offer_path_install()
        install.assert_not_called()


if __name__ == '__main__':
    unittest.main()
