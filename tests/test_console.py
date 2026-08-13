# -*- coding: utf-8 -*-
"""
console.interactive()：屏幕前有没有人。

这一个判据决定所有等人输入的分支走不走。判宽了，定时任务会卡在
选择框或按键上；判窄了，人在终端前却拿不到菜单。

    python -m unittest discover tests
"""
import unittest
from unittest import mock

from kuraya import console


class _Stream:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


class _Closed:
    def isatty(self):
        raise ValueError('I/O operation on closed file')


class Interactive(unittest.TestCase):
    def check(self, stdin, stdout):
        with mock.patch.object(console.sys, 'stdin', stdin), \
                mock.patch.object(console.sys, 'stdout', stdout):
            return console.interactive()

    def test_true_when_both_tty(self):
        self.assertTrue(self.check(_Stream(True), _Stream(True)))

    def test_false_without_keyboard(self):
        """管道喂输入：菜单读不到按键，会立刻 EOF 退出"""
        self.assertFalse(self.check(_Stream(False), _Stream(True)))

    def test_false_when_output_redirected(self):
        """输出进了文件：ANSI 面板只会留下一堆控制字符"""
        self.assertFalse(self.check(_Stream(True), _Stream(False)))

    def test_false_when_stdin_is_none(self):
        """打包成窗口程序时 sys.stdin 可能是 None"""
        self.assertFalse(self.check(None, _Stream(True)))

    def test_false_when_stream_closed(self):
        """流已关闭：isatty() 抛 ValueError，不能让它冒到调用方"""
        self.assertFalse(self.check(_Closed(), _Stream(True)))


class EnsureUtf8(unittest.TestCase):
    """统一 UTF-8 输出并强制行缓冲：打包后的 exe 可能被当非交互
    进程走块缓冲，刮削进度会积压到结束才一口气输出"""

    def test_reconfigure_with_line_buffering(self):
        with mock.patch.object(console.sys, 'stdout') as out, \
                mock.patch.object(console.sys, 'stderr') as err:
            console.ensure_utf8()
        out.reconfigure.assert_called_once_with(
            encoding='utf-8', errors='replace', line_buffering=True)
        err.reconfigure.assert_called_once_with(
            encoding='utf-8', errors='replace', line_buffering=True)

    def test_tolerates_closed_streams(self):
        """流不可 reconfigure（关闭/无属性）时静默跳过，不打断启动"""
        class Broken:
            def reconfigure(self, **kw):
                raise ValueError('closed')

        with mock.patch.object(console.sys, 'stdout', Broken()), \
                mock.patch.object(console.sys, 'stderr', Broken()):
            console.ensure_utf8()   # 不应抛异常


if __name__ == '__main__':
    unittest.main()
