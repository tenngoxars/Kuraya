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
    """悬停高亮、点击执行；方向键/数字键不受影响"""

    def row(self, r):
        """n=3、光标行 17 时选项 0/1/2 所在行 = 12/13/14"""
        return r

    def hover(self, r):
        return ('hover', 5, r)

    def click(self, r):
        return ('click', 5, r)

    def test_hover_highlights_then_enter_confirms(self):
        """悬停到选项 B 高亮（不执行），回车确认的是 B"""
        self.assertEqual(run_loop([self.hover(13), 'enter']), '2')

    def test_hover_switches_between_options(self):
        """悬停 B 再悬停 C，高亮跟随；回车确认 C"""
        self.assertEqual(
            run_loop([self.hover(13), self.hover(14), 'enter']), '3')

    def test_click_executes_target_row(self):
        """点击选项行直接执行该行（悬停已提供高亮反馈）"""
        self.assertEqual(run_loop([self.click(13)]), '2')

    def test_hover_same_row_no_effect(self):
        """悬停当前已高亮行不改变状态，回车仍确认原选项"""
        self.assertEqual(run_loop([self.hover(12), 'enter']), '1')

    def test_hover_same_row_does_not_redraw(self):
        """同行使内移动不触发重绘（1003 事件流很密，全屏重绘会闪）"""
        read = mock.Mock(side_effect=[self.hover(12), self.hover(12), 'enter'])
        with mock.patch.object(menu, 'clear_screen') as clear, \
             mock.patch.object(menu, 'brand'), \
             mock.patch.object(menu, 'rule'), \
             mock.patch.object(menu, 'say'), \
             mock.patch('kuraya.keys.query_cursor', return_value=(17, 1)), \
             mock.patch('kuraya.keys.read_key', read), \
             mock.patch('kuraya.keys.enable_mouse'), \
             mock.patch('kuraya.keys.disable_mouse'):
            result = menu.menu_loop(lambda: None, OPTIONS)
        self.assertEqual(result, '1')
        # 三次 read_key 均在第一次渲染后：同行使内 hover 未触发重绘
        self.assertEqual(clear.call_count, 1)

    def test_alt_screen_entered_and_restored(self):
        """菜单进入备用屏幕（鼠标转发），退出恢复主屏"""
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
        self.assertIn('\x1b[?1049h', out)
        self.assertIn('\x1b[?1049l', out)
        self.assertLess(out.index('\x1b[?1049h'),
                        out.index('\x1b[?1049l'))

    def test_click_blank_row_ignored(self):
        """点击选项区之外（如顶部行）忽略，继续等待按键"""
        self.assertEqual(run_loop([self.click(5), '2']), '2')

    def test_hover_without_cursor_ignored(self):
        """终端不支持光标查询时悬停/点击无法定位，忽略"""
        self.assertEqual(run_loop([self.hover(13), '2'], cursor=None), '2')

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
