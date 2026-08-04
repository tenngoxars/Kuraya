# -*- coding: utf-8 -*-
"""
kuraya: 协议 URL 解析与平台探测的测试。

页面生成的链接形如 kuraya:<百分号编码的绝对路径>，play 命令也会收到同样
的字符串，两种形态都必须还原出原始路径；play_mode 决定页面用协议还是复制。

    python -m unittest discover tests
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from kuraya import protocol
from kuraya.protocol import parse_url


class ParseUrl(unittest.TestCase):

    def test_plain_absolute_path(self):
        """macOS/Linux 上 play 命令直接传绝对路径"""
        self.assertEqual(parse_url('/tmp/影片.mp4'), '/tmp/影片.mp4')

    def test_scheme_absolute_path(self):
        """页面生成的链接形态，根斜杠不能被吃掉"""
        self.assertEqual(parse_url('kuraya:%2Ftmp%2F%E5%BD%B1%E7%89%87.mp4'),
                         '/tmp/影片.mp4')

    def test_scheme_windows_style(self):
        """Windows 链接是盘符开头，不应受影响（本平台路径规则不同，仅验证解析）"""
        self.assertEqual(parse_url('kuraya:C%3A%5CMedia%5C%E5%BD%B1%E7%89%87.mp4'),
                         'C:\\Media\\影片.mp4')

    def test_relative_path(self):
        self.assertEqual(parse_url('kuraya:影片.mp4'), '影片.mp4')

    def test_quoted_path(self):
        self.assertEqual(parse_url('"/tmp/影片.mp4"'), '/tmp/影片.mp4')

    def test_plain_scheme_prefix_without_value(self):
        self.assertEqual(parse_url('kuraya:'), '.')


class PlayMode(unittest.TestCase):
    """平台探测：Windows 看注册表、mac 看壳 app、Linux 看 xdg"""

    @mock.patch.object(protocol.os, 'name', 'nt')
    @mock.patch('kuraya.protocol.is_registered', return_value=True)
    def test_windows_registered(self, *_):
        self.assertEqual(protocol.play_mode(), 'protocol')

    @mock.patch.object(protocol.os, 'name', 'nt')
    @mock.patch('kuraya.protocol.is_registered', return_value=False)
    def test_windows_not_registered(self, *_):
        self.assertEqual(protocol.play_mode(), 'copy')

    @mock.patch.object(protocol.sys, 'platform', 'darwin')
    @mock.patch.object(protocol.os, 'name', 'posix')
    @mock.patch('pathlib.Path.home')
    @mock.patch('kuraya.protocol._shell_app_ready', side_effect=[False, True])
    def test_mac_with_shell_app(self, ready, home):
        """home 下没有、系统级 /Applications 有壳 app 时同样走协议"""
        home.return_value = Path('/Users/x')
        self.assertEqual(protocol.play_mode(), 'protocol')
        self.assertEqual(ready.call_count, 2)

    @mock.patch.object(protocol.sys, 'platform', 'darwin')
    @mock.patch.object(protocol.os, 'name', 'posix')
    @mock.patch('pathlib.Path.home')
    @mock.patch('kuraya.protocol._shell_app_ready', side_effect=[False, False])
    def test_mac_without_shell_app(self, ready, home):
        home.return_value = Path('/Users/x')
        self.assertEqual(protocol.play_mode(), 'copy')

    @mock.patch.object(protocol.sys, 'platform', 'linux')
    @mock.patch.object(protocol.os, 'name', 'posix')
    @mock.patch('kuraya.protocol.subprocess.run')
    def test_linux_registered(self, run):
        run.return_value = SimpleNamespace(stdout='kuraya-handler.desktop')
        self.assertEqual(protocol.play_mode(), 'protocol')

    @mock.patch.object(protocol.sys, 'platform', 'linux')
    @mock.patch.object(protocol.os, 'name', 'posix')
    @mock.patch('kuraya.protocol.subprocess.run')
    def test_linux_not_registered(self, run):
        run.return_value = SimpleNamespace(stdout='')
        self.assertEqual(protocol.play_mode(), 'copy')

    @mock.patch.object(protocol.sys, 'platform', 'linux')
    @mock.patch.object(protocol.os, 'name', 'posix')
    @mock.patch('kuraya.protocol.subprocess.run')
    def test_linux_xdg_error(self, run):
        run.side_effect = subprocess.SubprocessError
        self.assertEqual(protocol.play_mode(), 'copy')


class EnsureShellApp(unittest.TestCase):
    """mac 打包版首次运行自装壳 app 并注册 lsregister"""

    def test_not_macos(self):
        with mock.patch.object(protocol.sys, 'platform', 'linux'):
            self.assertFalse(protocol.ensure_shell_app())

    def test_not_frozen(self):
        with mock.patch.object(protocol.sys, 'platform', 'darwin'), \
                mock.patch.object(protocol.sys, 'frozen', False, create=True):
            self.assertFalse(protocol.ensure_shell_app())

    def test_already_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'home'
            macos = home / 'Applications' / 'Kuraya.app' / 'Contents' / 'MacOS'
            macos.mkdir(parents=True)
            (macos / 'Kuraya').write_text('')
            with mock.patch.object(protocol.sys, 'platform', 'darwin'), \
                    mock.patch.object(protocol.sys, 'frozen', True, create=True), \
                    mock.patch('pathlib.Path.home', return_value=home), \
                    mock.patch('kuraya.protocol.subprocess.run') as run:
                self.assertTrue(protocol.ensure_shell_app())
            run.assert_not_called()

    def test_half_installed_is_reinstalled(self):
        """后台安装被中断（Contents/MacOS 已建但为空）时，应重装而不是跳过"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / 'opt' / 'kuraya' / 'Kuraya'
            exe.parent.mkdir(parents=True)
            exe.write_text('')
            src = root / 'opt' / 'Kuraya.app'
            (src / 'Contents' / 'MacOS').mkdir(parents=True)
            (src / 'Contents' / 'MacOS' / 'Kuraya').write_text('')
            home = root / 'home'
            half = home / 'Applications' / 'Kuraya.app' / 'Contents' / 'MacOS'
            half.mkdir(parents=True)  # 只有空 MacOS 目录，没有可执行文件
            with mock.patch.object(protocol.sys, 'platform', 'darwin'), \
                    mock.patch.object(protocol.sys, 'frozen', True, create=True), \
                    mock.patch.object(protocol.sys, 'executable', str(exe)), \
                    mock.patch('pathlib.Path.home', return_value=home), \
                    mock.patch('kuraya.protocol.subprocess.run') as run:
                self.assertTrue(protocol.ensure_shell_app())
            # 重装后 MacOS 下有可执行文件，且重新注册过 lsregister
            self.assertTrue((half / 'Kuraya').is_file())
            run.assert_called_once()

    def test_no_source_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / 'kuraya' / 'Kuraya'
            exe.parent.mkdir(parents=True)
            exe.write_text('')
            home = root / 'home'
            with mock.patch.object(protocol.sys, 'platform', 'darwin'), \
                    mock.patch.object(protocol.sys, 'frozen', True, create=True), \
                    mock.patch.object(protocol.sys, 'executable', str(exe)), \
                    mock.patch('pathlib.Path.home', return_value=home):
                self.assertFalse(protocol.ensure_shell_app())
            self.assertFalse((home / 'Applications').exists())

    def test_installs_and_registers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / 'opt' / 'kuraya' / 'Kuraya'
            exe.parent.mkdir(parents=True)
            exe.write_text('')
            src = root / 'opt' / 'Kuraya.app'
            (src / 'Contents').mkdir(parents=True)
            home = root / 'home'
            home.mkdir()
            with mock.patch.object(protocol.sys, 'platform', 'darwin'), \
                    mock.patch.object(protocol.sys, 'frozen', True, create=True), \
                    mock.patch.object(protocol.sys, 'executable', str(exe)), \
                    mock.patch('pathlib.Path.home', return_value=home), \
                    mock.patch('kuraya.protocol.subprocess.run') as run:
                self.assertTrue(protocol.ensure_shell_app())
            target = home / 'Applications' / 'Kuraya.app'
            self.assertTrue((target / 'Contents').is_dir())
            run.assert_called_once()
            args = run.call_args[0][0]
            self.assertEqual(args[0], protocol._LSREGISTER)
            self.assertEqual(Path(args[2]), target)


if __name__ == '__main__':
    unittest.main()
