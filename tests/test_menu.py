# -*- coding: utf-8 -*-
"""
菜单选择：方向键 / 数字键 / 回车确认。

    python -m unittest discover tests
"""
import contextlib
import unittest
from pathlib import Path
from unittest import mock

from kuraya import i18n as _i18n
_i18n._lang = _i18n.ZH_CN  # 测试断言简体中文文案，先固定语言再导入被测模块

from kuraya import menu

OPTIONS = [('1', '甲', ''), ('2', '乙', ''), ('3', '丙', '')]


def run_loop(keys_seq, cursor=(17, 1)):
    """渲染用空函数（行数不影响行号公式，只依赖光标行），喂入按键序列。
    基于 loop_io 复用 mock 样板，并重定向局部重绘输出"""
    with loop_io(keys_seq, cursor) as (result, _out, _clear, _qc):
        return result


@contextlib.contextmanager
def loop_io(keys_seq, cursor=(17, 1)):
    """运行 menu_loop 并暴露输出与内部 mock，供断言重绘序列/次数的测试复用"""
    import io
    from contextlib import redirect_stdout
    buffer = io.StringIO()
    with mock.patch.object(menu, 'clear_screen') as clear, \
         mock.patch.object(menu, 'brand'), \
         mock.patch.object(menu, 'rule'), \
         mock.patch.object(menu, 'say'), \
         mock.patch('kuraya.keys.query_cursor', return_value=cursor) as qc, \
         mock.patch('kuraya.keys.read_key', side_effect=list(keys_seq)), \
         redirect_stdout(buffer):
        result = menu.menu_loop(lambda: None, OPTIONS)
    yield result, buffer.getvalue(), clear, qc


class KeyboardSelection(unittest.TestCase):
    """方向键/数字键导航 + 回车确认；选中行金色粗体高亮"""

    def test_arrows_move_selection(self):
        self.assertEqual(run_loop(['down', 'enter']), '2')

    def test_arrows_wrap_around(self):
        """方向键到末尾循环回开头"""
        self.assertEqual(run_loop(['down', 'down', 'down', 'enter']), '1')

    def test_arrows_repaint_rows_only(self):
        """方向键选择只局部重绘两行：整屏不重绘、光标不重复查询"""
        with loop_io(['down', 'down', 'enter']) as (result, out, clear, qc):
            self.assertEqual(result, '3')
            self.assertEqual(clear.call_count, 1)   # 整屏只绘一次
            self.assertEqual(qc.call_count, 1)      # CPR 只查一次
            # 局部重绘定位序列：选项 0/1/2 行 = 12/13/14
            for r in (12, 13, 14):
                self.assertIn(f'\x1b[{r};1H\x1b[2K', out)

    def test_selected_row_highlighted_bold(self):
        """方向键移到新行后，新选中行金色粗体高亮，且不再铺底色"""
        with loop_io(['down', 'enter']) as (result, out, clear, qc):
            self.assertEqual(result, '2')
            # 重绘序列中选中行带粗体序列
            self.assertIn('\x1b[1m', out)
            # 判别性：底色高亮已撤回，不得再出现背景色序列
            self.assertNotIn('48;5;', out)

    def test_arrows_without_cursor_fallback(self):
        """CPR 不可用（终端不应答）时方向键回退整屏重绘，不崩溃"""
        with loop_io(['down', 'enter'], cursor=None) as (result, out, clear, qc):
            self.assertEqual(result, '2')
            self.assertGreater(clear.call_count, 1)  # 初次 + 方向键回退重绘

    def test_digits_still_work(self):
        self.assertEqual(run_loop(['3']), '3')

    def test_esc_returns_none(self):
        self.assertIsNone(run_loop(['esc']))

    def test_alt_screen_entered_and_restored(self):
        """菜单进入备用屏幕，退出恢复主屏"""
        with loop_io(['enter']) as (result, out, clear, qc):
            self.assertIn('\x1b[?1049h', out)
            self.assertIn('\x1b[?1049l', out)
            self.assertLess(out.index('\x1b[?1049h'),
                            out.index('\x1b[?1049l'))

    def test_cursor_hidden_during_redraw(self):
        """整屏重绘期间隐藏光标，渲染完恢复（消除 Windows 重绘闪烁）"""
        with loop_io(['enter']) as (result, out, clear, qc):
            self.assertLess(out.index('\x1b[?25l'), out.index('\x1b[?25h'))


class RunExecBranches(unittest.TestCase):
    """主循环执行分支：退出备用屏幕后先清屏再执行，输出不从旧内容继续"""

    def setUp(self):
        import tempfile
        from kuraya import settings as s
        self.dir = tempfile.mkdtemp()
        self.patchers = [
            mock.patch.object(s, 'SETTINGS_FILE',
                              Path(self.dir) / '设置.ini'),
            mock.patch.object(s, 'APP_DIR', Path(self.dir)),
        ]
        import configparser
        cfg = configparser.ConfigParser()
        cfg['路径'] = {'影片库目录': self.dir,
                       '待整理目录': f'{self.dir}/待整理', '播放器': ''}
        with open(f'{self.dir}/设置.ini', 'w') as fp:
            cfg.write(fp)
        for p in self.patchers:
            p.start()
        self.addCleanup(mock.patch.stopall)

    def test_rebuild_clears_before_exec(self):
        """选 2 重建页面：分支清屏在 cmd_rebuild 之前。
        判别性：进入菜单的 draw_all 已清 1 次，分支再清才是 2 次——
        旧代码（无分支清屏）rebuild 前只有 1 次 clear，此断言必失败"""
        order = []
        with mock.patch('kuraya.keys.read_key', side_effect=['2', 'esc']), \
             mock.patch.object(menu, 'clear_screen',
                               side_effect=lambda: order.append('clear')), \
             mock.patch.object(menu.launcher, 'cmd_rebuild',
                               side_effect=lambda lib: order.append('rebuild')), \
             mock.patch.object(menu.launcher, 'spin'), \
             mock.patch('kuraya.updater.text', return_value=''), \
             mock.patch.object(menu, 'pause'):
            menu.run()
        # rebuild 之前：draw_all 清 1 次 + 分支清 1 次 = 2
        self.assertGreaterEqual(order.index('rebuild'), 2)

    def test_scrape_clears_before_exec(self):
        """选 1 刮削入库：分支清屏在 cmd_all 之前（判别性同上）"""
        order = []
        with mock.patch('kuraya.keys.read_key', side_effect=['1', 'esc']), \
             mock.patch.object(menu, 'clear_screen',
                               side_effect=lambda: order.append('clear')), \
             mock.patch.object(menu.launcher, 'cmd_all',
                               side_effect=lambda lib, src, opts=None:
                                   order.append('cmd_all') or
                                   ({'done': 0, 'failed': 0}, False)), \
             mock.patch.object(menu.launcher, 'spin'), \
             mock.patch('kuraya.updater.text', return_value=''), \
             mock.patch.object(menu, 'pause'):
            menu.run()
        self.assertGreaterEqual(order.index('cmd_all'), 2)

    def test_settings_branch_no_extra_clear(self):
        """选 4 设置：走备用屏幕，执行分支不额外清屏。
        清屏只来自两次菜单重绘（draw_all），共 2 次"""
        with mock.patch('kuraya.keys.read_key',
                        side_effect=['4', 'esc', 'esc']), \
             mock.patch.object(menu, 'clear_screen') as clear, \
             mock.patch('kuraya.updater.text', return_value=''), \
             mock.patch.object(menu, 'settings_menu'):
            menu.run()
        self.assertEqual(clear.call_count, 2)


if __name__ == '__main__':
    unittest.main()
