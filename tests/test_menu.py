# -*- coding: utf-8 -*-
"""
菜单选择：方向键 / 数字键 / 鼠标点击选项行。

    python -m unittest discover tests
"""
import unittest
from unittest import mock

from kuraya import i18n as _i18n
_i18n._lang = _i18n.ZH_CN  # 测试断言简体中文文案，先固定语言再导入被测模块

from kuraya import menu

OPTIONS = [('1', '甲', ''), ('2', '乙', ''), ('3', '丙', '')]


def run_loop(keys_seq, cursor=(17, 1)):
    """渲染用空函数（行数不影响行号公式，只依赖光标行），喂入按键序列"""
    with mock.patch.object(menu, 'clear_screen'), \
         mock.patch.object(menu, 'brand'), \
         mock.patch.object(menu, 'rule'), \
         mock.patch.object(menu, 'say'), \
         mock.patch('kuraya.keys.query_cursor', return_value=cursor), \
         mock.patch('kuraya.keys.read_key', side_effect=list(keys_seq)), \
         mock.patch('kuraya.keys.enable_mouse'), \
         mock.patch('kuraya.keys.disable_mouse'):
        return menu.menu_loop(lambda: None, OPTIONS)


class ClickSelection(unittest.TestCase):
    """点击先高亮、再点一次已高亮项才执行；方向键/数字键不受影响"""

    def click_row(self, row):
        """n=3、光标行 17 时选项 0/1/2 所在行 = 12/13/14"""
        return ('click', 5, row)

    def test_click_highlights_first(self):
        """第一次点击未高亮项只移动高亮不执行；回车确认的是新高亮项"""
        self.assertEqual(run_loop([self.click_row(13), 'enter']), '2')

    def test_second_click_executes(self):
        """再点一次已高亮项才执行"""
        self.assertEqual(run_loop([self.click_row(13), self.click_row(13)]), '2')

    def test_click_other_option_switches(self):
        """先点 B 高亮，再点 C 则高亮切到 C"""
        self.assertEqual(
            run_loop([self.click_row(13), self.click_row(14), 'enter']), '3')

    def test_click_highlighted_option_executes(self):
        """选项 0 初始已高亮，第一次点击即确认（点已高亮项 = 再点一次）"""
        self.assertEqual(run_loop([self.click_row(12)]), '1')

    def test_click_blank_row_ignored(self):
        """点击选项区之外（如顶部行）忽略，继续等待按键"""
        self.assertEqual(run_loop([('click', 5, 5), '2']), '2')

    def test_click_without_cursor_ignored(self):
        """终端不支持光标查询时点击无法定位，忽略"""
        self.assertEqual(run_loop([('click', 5, 13), '2'], cursor=None), '2')

    def test_arrows_still_work(self):
        self.assertEqual(run_loop(['down', 'enter']), '2')

    def test_digits_still_work(self):
        self.assertEqual(run_loop(['3']), '3')

    def test_mouse_disabled_on_exit(self):
        """退出菜单时关闭鼠标报告（引用计数成对）"""
        with mock.patch.object(menu, 'clear_screen'), \
             mock.patch.object(menu, 'brand'), \
             mock.patch.object(menu, 'rule'), \
             mock.patch.object(menu, 'say'), \
             mock.patch('kuraya.keys.query_cursor', return_value=(17, 1)), \
             mock.patch('kuraya.keys.read_key', return_value='enter'), \
             mock.patch('kuraya.keys.enable_mouse') as enable, \
             mock.patch('kuraya.keys.disable_mouse') as disable:
            menu.menu_loop(lambda: None, OPTIONS)
        enable.assert_called_once()
        disable.assert_called_once()

    def test_cursor_hidden_during_redraw(self):
        """整屏重绘期间隐藏光标，渲染完恢复（消除 Windows 重绘闪烁）"""
        import io
        from contextlib import redirect_stdout
        buffer = io.StringIO()
        with mock.patch.object(menu, 'clear_screen'), \
             mock.patch.object(menu, 'brand'), \
             mock.patch.object(menu, 'rule'), \
             mock.patch.object(menu, 'say'), \
             mock.patch('kuraya.keys.query_cursor', return_value=(17, 1)), \
             mock.patch('kuraya.keys.read_key', return_value='enter'), \
             mock.patch('kuraya.keys.enable_mouse'), \
             mock.patch('kuraya.keys.disable_mouse'), \
             redirect_stdout(buffer):
            menu.menu_loop(lambda: None, OPTIONS)
        out = buffer.getvalue()
        self.assertLess(out.index('\x1b[?25l'), out.index('\x1b[?25h'))

    def test_warp_hint_shown_once(self):
        """Warp 下提示开启 Mouse Reporting，且每会话只提示一次"""
        import io
        from contextlib import redirect_stdout
        menu._mouse_hint_shown = False
        buffer = io.StringIO()
        with mock.patch.object(menu, 'clear_screen'), \
             mock.patch.object(menu, 'brand'), \
             mock.patch.object(menu, 'rule'), \
             mock.patch.object(menu, 'say'), \
             mock.patch('kuraya.keys.query_cursor', return_value=(17, 1)), \
             mock.patch('kuraya.keys.read_key', return_value='enter'), \
             mock.patch('kuraya.keys.enable_mouse'), \
             mock.patch('kuraya.keys.disable_mouse'), \
             mock.patch('kuraya.keys.terminal_mouse_status',
                        return_value='warp-needs-toggle'), \
             redirect_stdout(buffer):
            menu.menu_loop(lambda: None, OPTIONS)
        self.assertIn('Mouse Reporting', buffer.getvalue())
        menu._mouse_hint_shown = False


if __name__ == '__main__':
    unittest.main()
