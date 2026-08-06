# -*- coding: utf-8 -*-
"""
跨平台单键读取：Esc / Enter / 功能键序列的识别。

    python -m unittest discover tests
"""
import unittest
from unittest import mock

from kuraya import keys


def _posix_env(first, rest=b''):
    """构造 POSIX 分支的依赖：termios/tty/select 替换 keys 模块属性"""
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
        'attrs': [mock.patch.object(keys, 'termios', termios),
                  mock.patch.object(keys, 'select', select),
                  mock.patch.object(keys, 'tty', mock.MagicMock())],
        'termios': termios,
    }


class ReadKeyPosix(unittest.TestCase):
    """POSIX 走 termios raw 模式，一次读一个字节"""

    def setUp(self):
        self.posix = mock.patch.object(keys.os, 'name', 'posix').start()
        self.addCleanup(mock.patch.stopall)

    def key(self, first, rest=b''):
        env = _posix_env(first, rest)
        with env['os.read'], env['isatty'], env['modules'], \
             env['attrs'][0], env['attrs'][1], env['attrs'][2]:
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
        with env['os.read'], env['isatty'], env['modules'], \
             env['attrs'][0], env['attrs'][1], env['attrs'][2]:
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

    def test_esc_with_trailing_bytes(self):
        """Esc 后跟方向键序列（WT 风格 \x1b[A）识别为方向键"""
        msvcrt = mock.MagicMock()
        msvcrt.getch.side_effect = [b'\x1b', b'[', b'B']
        msvcrt.kbhit.side_effect = [True, True, False]
        with mock.patch.dict('sys.modules', {'msvcrt': msvcrt}):
            self.assertEqual(keys._read_key_win(), 'down')


class CprParse(unittest.TestCase):
    """CPR（光标位置应答）解析，供菜单局部重绘定位"""

    def test_parse_cpr(self):
        self.assertEqual(keys._parse_cpr(b'\x1b[12;5R'), (12, 5))

    def test_parse_cpr_garbage(self):
        self.assertIsNone(keys._parse_cpr(b'not-a-cpr'))

    def test_stdin_vt_toggle_restores_mode(self):
        """Windows stdin VT 输入模式：开启切到 PROCESSED|VT_INPUT，
        关闭恢复保存的原模式（CPR 应答读取的前置，用完必须还原）"""
        windll = mock.MagicMock()
        with mock.patch('ctypes.windll', windll, create=True):
            keys._console_stdin_vt(True)         # mode.value 为 0，saved=0
            keys._console_stdin_vt(False, 0x0A)  # 恢复原模式 0x0A
        calls = windll.kernel32.SetConsoleMode.call_args_list
        self.assertEqual(calls[0].args[1], 0x201)  # PROCESSED|VT_INPUT
        self.assertEqual(calls[1].args[1], 0x0A)   # 恢复原模式

    def test_time_imported_at_module_top(self):
        """import time 必须在模块顶层：Windows 分支 _query_cursor_win
        用 time.monotonic() 兜底，放进 POSIX 守卫会 NameError"""
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(keys))
        top_imports = [a for a in tree.body if isinstance(a, ast.Import)]
        self.assertTrue(any('time' in (n.name for n in a.names)
                            for a in top_imports))


if __name__ == '__main__':
    unittest.main()
