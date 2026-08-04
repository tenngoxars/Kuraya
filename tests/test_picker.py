# -*- coding: utf-8 -*-
"""
目录/文件选择框三平台分支的测试：Windows PowerShell、macOS osascript、
Linux tkinter，以及各分支的失败与取消语义。

    python -m unittest discover tests
"""
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from kuraya import picker


class PickMac(unittest.TestCase):
    """macOS 走 osascript 原生面板"""

    def setUp(self):
        self.nt = mock.patch.object(picker.os, 'name', 'posix').start()
        self.darwin = mock.patch.object(picker.sys, 'platform', 'darwin').start()
        self.run = mock.patch('kuraya.picker.subprocess.run').start()
        self.addCleanup(mock.patch.stopall)

    def test_folder_selected(self):
        self.run.return_value = SimpleNamespace(
            returncode=0, stdout='/Users/x/Movies\n', stderr='')
        path, err = picker.pick('folder', '选择影片库')
        self.assertEqual(path, '/Users/x/Movies')
        self.assertEqual(err, '')
        argv = self.run.call_args[0][0]
        self.assertEqual(argv[0], 'osascript')
        self.assertIn('choose folder', argv[2])
        self.assertIn('选择影片库', argv[2])

    def test_cancel(self):
        """用户取消：osascript 提示 User canceled，视为取消而非错误"""
        self.run.return_value = SimpleNamespace(
            returncode=1, stdout='',
            stderr='execution error: User canceled. (-128)')
        path, err = picker.pick('folder')
        self.assertEqual((path, err), ('', ''))

    def test_failure_returns_error(self):
        """真实失败（如 Apple 事件被拒）应返回错误说明，供界面降级手动输入"""
        self.run.return_value = SimpleNamespace(
            returncode=1, stdout='', stderr='execution error: 未授权 (-1743)')
        path, err = picker.pick('folder')
        self.assertEqual(path, '')
        self.assertIn('未授权', err)

    def test_timeout_reports_consistently(self):
        self.run.side_effect = subprocess.TimeoutExpired('osascript', 300)
        path, err = picker.pick('folder')
        self.assertEqual((path, err), ('', '选择框超时未关闭'))

    def test_title_quote_escaped(self):
        self.run.return_value = SimpleNamespace(
            returncode=0, stdout='/Users/x/Movies\n', stderr='')
        picker.pick('folder', '选择"影片库"')
        argv = self.run.call_args[0][0]
        self.assertNotIn('"影片库"', argv[2])
        self.assertIn("选择'影片库'", argv[2])

    def test_osascript_missing(self):
        self.run.side_effect = FileNotFoundError
        path, err = picker.pick('folder')
        self.assertEqual((path, err), ('', 'FileNotFoundError: '))

    def test_file_kind_uses_choose_file(self):
        self.run.return_value = SimpleNamespace(
            returncode=0, stdout='/Applications/IINA.app\n', stderr='')
        path, _ = picker.pick('file', '选择播放器')
        argv = self.run.call_args[0][0]
        self.assertIn('choose file', argv[2])
        self.assertEqual(path, '/Applications/IINA.app')


class PickWindows(unittest.TestCase):
    """Windows 走 PowerShell 对话框"""

    def setUp(self):
        self.nt = mock.patch.object(picker.os, 'name', 'nt').start()
        self.addCleanup(mock.patch.stopall)

    def test_uses_powershell(self):
        with mock.patch('kuraya.picker._powershell',
                        return_value=(r'D:\Media\Library', '')) as ps:
            path, err = picker.pick('folder', '选择影片库')
        self.assertEqual(path, r'D:\Media\Library')
        self.assertEqual(err, '')
        self.assertIn('FolderBrowserDialog', ps.call_args[0][0])


class PickLinux(unittest.TestCase):
    """Linux 走 tkinter"""

    def setUp(self):
        self.nt = mock.patch.object(picker.os, 'name', 'posix').start()
        self.plat = mock.patch.object(picker.sys, 'platform', 'linux').start()
        self.addCleanup(mock.patch.stopall)

    def test_uses_tkinter(self):
        with mock.patch('kuraya.picker._tk',
                        return_value=('/media/lib', '')) as tk:
            path, err = picker.pick('folder')
        self.assertEqual(path, '/media/lib')
        self.assertEqual(err, '')
        tk.assert_called_once_with('folder', '请选择')


if __name__ == '__main__':
    unittest.main()
