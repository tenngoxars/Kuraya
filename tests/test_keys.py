# -*- coding: utf-8 -*-
"""
跨平台单键读取：Esc / Enter / 功能键序列的识别。

    python -m unittest discover tests
"""
import unittest
from unittest import mock

from kuraya import keys


def _posix_env(first, rest=b''):
    """构造 POSIX 分支的依赖：termios/tty/select 用假模块注入"""
    termios = mock.MagicMock()
    termios.tcgetattr.return_value = 'old'
    select = mock.MagicMock()
    # 有转义序列后续字节时：第一轮可读、读完即退出
    select.select.side_effect = [[True], [False]] if rest else [[False]]
    reads = [first] + ([rest] if rest else [])
    return {
        'os.read': mock.patch.object(keys.os, 'read', side_effect=reads),
        'isatty': mock.patch.object(keys.os, 'isatty', return_value=True),
        'modules': mock.patch.dict('sys.modules', {
            'termios': termios, 'tty': mock.MagicMock(), 'select': select,
        }),
        'termios': termios,
    }


class ReadKeyPosix(unittest.TestCase):
    """POSIX 走 termios raw 模式，一次读一个字节"""

    def setUp(self):
        self.posix = mock.patch.object(keys.os, 'name', 'posix').start()
        self.addCleanup(mock.patch.stopall)

    def key(self, first, rest=b''):
        env = _posix_env(first, rest)
        with env['os.read'], env['isatty'], env['modules']:
            return keys._read_key_posix()

    def test_plain_char(self):
        self.assertEqual(self.key(b'5'), '5')

    def test_enter(self):
        self.assertEqual(self.key(b'\r'), 'enter')

    def test_esc_alone(self):
        self.assertEqual(self.key(b'\x1b'), 'esc')

    def test_arrow_sequence_not_esc(self):
        """方向键是 \x1b[A 等转义序列，识别为 up/down 而非 Esc"""
        self.assertEqual(self.key(b'\x1b', b'[A'), 'up')
        self.assertEqual(self.key(b'\x1b', b'[B'), 'down')
        self.assertEqual(self.key(b'\x1b', b'[C'), 'right')
        self.assertEqual(self.key(b'\x1b', b'[D'), 'left')

    def test_unknown_sequence(self):
        """F1 等未识别的转义序列返回 '?'，不影响后续按键"""
        self.assertEqual(self.key(b'\x1b', b'OP'), '?')

    def test_eof(self):
        self.assertEqual(self.key(b''), 'eof')

    def test_ctrl_c_raises(self):
        with self.assertRaises(KeyboardInterrupt):
            self.key(b'\x03')

    def test_utf8_char(self):
        """多字节 UTF-8 字符按一个键处理"""
        self.assertEqual(self.key('中'.encode('utf-8')), '中')

    def test_raw_mode_restored(self):
        """无论结果如何都要恢复终端模式"""
        env = _posix_env(b'1')
        with env['os.read'], env['isatty'], env['modules']:
            keys._read_key_posix()
        env['termios'].tcsetattr.assert_called_once_with(
            keys.sys.stdin.fileno(), env['termios'].TCSADRAIN, 'old')


class ReadKeyWindows(unittest.TestCase):
    """Windows 走 msvcrt"""

    def setUp(self):
        self.nt = mock.patch.object(keys.os, 'name', 'nt').start()
        self.addCleanup(mock.patch.stopall)

    def key(self, *bytes_seq):
        msvcrt = mock.MagicMock()
        msvcrt.getch.side_effect = bytes_seq
        with mock.patch.dict('sys.modules', {'msvcrt': msvcrt}):
            return keys._read_key_win()

    def test_plain_char(self):
        self.assertEqual(self.key(b'1'), '1')

    def test_esc(self):
        self.assertEqual(self.key(b'\x1b'), 'esc')

    def test_enter(self):
        self.assertEqual(self.key(b'\r'), 'enter')

    def test_function_key_prefix_skipped(self):
        """功能键第二字节决定键名：方向键 / 未识别的返回 '?'"""
        self.assertEqual(self.key(b'\xe0', b'H'), 'up')
        self.assertEqual(self.key(b'\xe0', b'P'), 'down')
        self.assertEqual(self.key(b'\xe0', b'X'), '?')

    def test_ctrl_c_raises(self):
        with self.assertRaises(KeyboardInterrupt):
            self.key(b'\x03')


if __name__ == '__main__':
    unittest.main()
