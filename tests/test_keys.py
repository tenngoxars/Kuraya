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

    def test_mouse_click_sequence(self):
        """SGR 鼠标序列 \x1b[<b;x;yM 解析为点击坐标（列, 行）"""
        self.assertEqual(self.key(b'\x1b', b'[<0;10;5M'),
                         ('click', 10, 5))

    def test_mouse_release_event(self):
        """释放事件（m 结尾）同样携带坐标，按点击处理"""
        self.assertEqual(self.key(b'\x1b', b'[<3;20;8m'),
                         ('click', 20, 8))

    def test_malformed_mouse_sequence(self):
        self.assertEqual(self.key(b'\x1b', b'[<xx'), '?')


class ReadKeyWindows(unittest.TestCase):
    """Windows 走 msvcrt"""

    def setUp(self):
        self.nt = mock.patch.object(keys.os, 'name', 'nt').start()
        self.addCleanup(mock.patch.stopall)

    def key(self, *bytes_seq):
        msvcrt = mock.MagicMock()
        msvcrt.getch.side_effect = bytes_seq
        msvcrt.kbhit.side_effect = [False]  # 默认无后续转义字节
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

    def test_mouse_click_sequence(self):
        """Windows 终端（WT）的鼠标序列走 msvcrt 逐字节收集"""
        msvcrt = mock.MagicMock()
        seq = [b'\x1b', b'[', b'<', b'0', b';', b'1', b'2', b';', b'5', b'M']
        msvcrt.getch.side_effect = seq
        msvcrt.kbhit.side_effect = [True] * (len(seq) - 1) + [False]
        with mock.patch.dict('sys.modules', {'msvcrt': msvcrt}):
            self.assertEqual(keys._read_key_win(), ('click', 12, 5))

    def test_esc_with_trailing_bytes(self):
        """Esc 后跟方向键序列（WT 风格 \x1b[A）识别为方向键"""
        msvcrt = mock.MagicMock()
        msvcrt.getch.side_effect = [b'\x1b', b'[', b'B']
        msvcrt.kbhit.side_effect = [True, True, False]
        with mock.patch.dict('sys.modules', {'msvcrt': msvcrt}):
            self.assertEqual(keys._read_key_win(), 'down')


class MouseMode(unittest.TestCase):
    """鼠标报告启用/禁用（嵌套引用计数）+ 光标位置解析"""

    def setUp(self):
        self.isatty = mock.patch.object(keys.os, 'isatty',
                                        return_value=True).start()
        self.addCleanup(mock.patch.stopall)

    def test_balanced_enable_disable(self):
        """最外层退出才真正关闭鼠标报告"""
        with mock.patch.object(keys.sys.stdout, 'write') as write, \
             mock.patch.object(keys.sys.stdout, 'flush'):
            keys.enable_mouse()
            keys.enable_mouse()
            keys.disable_mouse()          # 内层退出：不关闭
            write.assert_called_once_with(keys.MOUSE_ENABLE)
            keys.disable_mouse()          # 外层退出：关闭
            write.assert_called_with(keys.MOUSE_DISABLE)
            self.assertEqual(write.call_count, 2)

    def test_parse_cpr(self):
        self.assertEqual(keys._parse_cpr(b'\x1b[12;5R'), (12, 5))

    def test_parse_cpr_garbage(self):
        self.assertIsNone(keys._parse_cpr(b'not-a-cpr'))


if __name__ == '__main__':
    unittest.main()
