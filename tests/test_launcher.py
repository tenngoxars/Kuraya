# -*- coding: utf-8 -*-
"""
界面对事件的渲染。

喂一串合成事件，把输出的 ANSI 转义去掉后逐行核对 ——
事件类型漏接会表现为少一行，而不是抛异常，靠肉眼看不出来。

    python -m unittest discover tests
"""
import io
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from kuraya import i18n as _i18n
_i18n._lang = _i18n.ZH_CN  # 测试断言简体中文文案，先固定语言再导入被测模块

from kuraya import launcher, setup
from kuraya.media.model import (CoverReady, FailReason, Failed, Fetched, Found,
                                Movie, PosterReady, Probing, Settings, Stage,
                                Started, Stored)

MOVIE = Movie(number='XXX-000', title='标题', cover_url='',
              actors=('演员甲',), release='2026-08-07', studio='示例制作商')

ANSI = re.compile(r'\033\[[0-9;]*[A-Za-z]')

SUCCESS = [
    Found(count=1),
    Started(number='XXX-000', index=1),
    Probing(stage=Stage.METADATA),
    Fetched(movie=MOVIE),
    Probing(stage=Stage.COVER),
    CoverReady(size_kb=512),
    Probing(stage=Stage.CROP),
    PosterReady(),
    Probing(stage=Stage.ARCHIVE),
    Stored(path=Path('D:/films/Private/演员甲/XXX-000'), elapsed=4.2),
]


def render(events, **opts):
    """跑一遍 do_scrape，返回 (输出行, 统计)"""
    buffer = io.StringIO()
    with mock.patch.object(launcher, 'media') as fake, \
         mock.patch.object(launcher.settings, 'load', return_value={'sleep': 0}), \
         mock.patch.object(launcher.spin, 'set'), \
         mock.patch.object(launcher.spin, 'hide'):
        fake.Settings = Settings
        fake.process.return_value = iter(events)
        with redirect_stdout(buffer):
            stats = launcher.do_scrape(Path('lib'), Path('src'), opts)

    lines = [ANSI.sub('', line).lstrip('\r').rstrip()
             for line in buffer.getvalue().split('\n')]
    return [line for line in lines if line.strip()], stats


class Success(unittest.TestCase):

    def setUp(self):
        self.lines, self.stats = render(SUCCESS)

    def test_lines(self):
        self.assertEqual(self.lines, [
            '   ▸ XXX-000                                             [1/1]',
            '     ├ 封面   已下载',
            '     ├ 裁剪   已生成竖版海报',
            '     ├ 元数据 演员甲 · 示例制作商 · 2026-08-07',
            '     └ 入库   演员甲\\XXX-000                              4.2s',
        ])

    def test_metadata_line_comes_before_stored(self):
        """Fetched 在抓取那一刻就发出，界面把它排在入库之前"""
        labels = [line.split()[1] for line in self.lines[1:]]
        self.assertEqual(labels, ['封面', '裁剪', '元数据', '入库'])

    def test_stats(self):
        self.assertEqual(self.stats, {'found': 1, 'done': 1, 'failed': 0})


class Failures(unittest.TestCase):

    def one(self, reason, number='XXX-000'):
        lines, stats = render([
            Found(count=1),
            Started(number=number, index=1),
            Failed(number=number, reason=reason),
        ])
        return lines[-1], stats

    def test_every_reason_renders(self):
        """漏掉一种原因会在这里 KeyError，而不是在用户跑到那一部时"""
        for reason in FailReason:
            line, stats = self.one(reason)
            self.assertTrue(line.startswith('     └ '), reason)
            self.assertEqual(stats['failed'], 1, reason)

    def test_not_found_wording(self):
        line, _ = self.one(FailReason.NOT_FOUND)
        self.assertIn('未找到元数据', line)

    def test_network_is_distinct_from_not_found(self):
        network, _ = self.one(FailReason.NETWORK)
        missing, _ = self.one(FailReason.NOT_FOUND)
        self.assertNotEqual(network, missing)

    def test_no_number_shows_filename(self):
        lines, _ = render([
            Found(count=1),
            Started(number='新建文件夹.mp4', index=1),
            Failed(number='新建文件夹.mp4', reason=FailReason.NO_NUMBER),
        ])
        self.assertIn('新建文件夹.mp4', lines[0])


class Batch(unittest.TestCase):

    def test_mixed_results(self):
        _, stats = render([
            Found(count=2),
            Started(number='XXX-000', index=1),
            Fetched(movie=MOVIE),
            Stored(path=Path('lib/演员甲/XXX-000'), elapsed=1.0),
            Started(number='SSSS-4567', index=2),
            Failed(number='SSSS-4567', reason=FailReason.NOT_FOUND),
        ])
        self.assertEqual(stats, {'found': 2, 'done': 1, 'failed': 1})

    def test_unterminated_movie_counts_as_failure(self):
        """引擎不该这样，但真断在中间时不能算成功"""
        _, stats = render([
            Found(count=1),
            Started(number='XXX-000', index=1),
            Probing(stage=Stage.METADATA),
        ])
        self.assertEqual(stats['failed'], 1)


class LibraryPathInput(unittest.TestCase):
    """
    选择框用不了时的输入退路。macOS 的 Homebrew Python 不带 tkinter，
    这在命令行安装场景下是常态而非意外
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.existing = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def ask(self, typed):
        buffer = io.StringIO()
        with mock.patch('builtins.input', return_value=typed), \
             redirect_stdout(buffer):
            return setup.ask_library_path()

    def test_accepts_existing_directory(self):
        self.assertEqual(self.ask(str(self.existing)), str(self.existing))

    def test_strips_quotes(self):
        """从访达或资源管理器拖进终端的路径会带引号"""
        self.assertEqual(self.ask(f'"{self.existing}"'), str(self.existing))

    def test_rejects_missing_directory(self):
        self.assertEqual(self.ask(str(self.existing / '没有这个')), '')

    def test_empty_input_cancels(self):
        self.assertEqual(self.ask(''), '')

    def test_interrupt_cancels(self):
        buffer = io.StringIO()
        with mock.patch('builtins.input', side_effect=EOFError), \
             redirect_stdout(buffer):
            self.assertEqual(setup.ask_library_path(), '')


class Empty(unittest.TestCase):

    def test_nothing_to_do(self):
        lines, stats = render([Found(count=0)])
        self.assertEqual(lines, ['    没有待处理的影片'])
        self.assertEqual(stats, {'found': 0, 'done': 0, 'failed': 0})


class DryRun(unittest.TestCase):

    def test_listed_files_are_not_failures(self):
        _, stats = render([
            Found(count=2),
            Started(number='XXX-000', index=1),
            Started(number='YYYY-111', index=2),
        ], dry_run=True)
        self.assertEqual(stats, {'found': 2, 'done': 0, 'failed': 0})


class ChildProtocol(unittest.TestCase):
    """
    子进程输出经 ASCII 标记解析（cleanup/gallery），
    界面文案随语言变化，解析标记必须稳定
    """

    def clean(self, lines):
        buffer = io.StringIO()
        with mock.patch.object(launcher, 'run', return_value=iter(lines)), \
             mock.patch.object(launcher.spin, 'set'), \
             mock.patch.object(launcher.spin, 'hide'), \
             redirect_stdout(buffer):
            removed = launcher.do_clean(Path('src'), Path('lib'))
        return removed, ANSI.sub('', buffer.getvalue())

    def test_cleanup_markers_parsed(self):
        removed, out = self.clean([
            '[cleanup:rm] 空文件夹A',
            '[cleanup:linked] 演员X/AAA-001',
            '[cleanup:kept] 没刮到的',
        ])
        self.assertEqual(removed, 1)
        self.assertIn('移除 空文件夹A', out)
        self.assertIn('此前已入库', out)
        self.assertIn('未能刮削', out)

    def test_child_failure_reported(self):
        removed, out = self.clean([f'{launcher.CHILD_FAILED} 1'])
        self.assertIn('清理源目录失败', out)

    def refresh(self, lines):
        with mock.patch.object(launcher, 'run', return_value=iter(lines)), \
             mock.patch.object(launcher.spin, 'set'), \
             mock.patch.object(launcher.spin, 'hide'), \
             redirect_stdout(io.StringIO()):
            return launcher.do_refresh(Path('lib'))

    def test_gallery_collected_marker(self):
        self.assertEqual(self.refresh(['gallery-collected=7']), 7)

    def test_gallery_missing_marker_counts_as_failure(self):
        """拿不到收录数说明子进程没正常跑完，不能当成 0 部"""
        self.assertEqual(self.refresh(['一些无关输出']), 0)


class OfferOpenLibrary(unittest.TestCase):
    """完整流程完成后用方向键选择是否直接打开片库"""

    def run_all(self, keys=('enter',), quiet=False, yes=False):
        read = mock.Mock(side_effect=list(keys))
        opened = mock.Mock()
        buffer = io.StringIO()
        with mock.patch.object(launcher, 'do_scrape',
                               return_value={'found': 1, 'done': 1,
                                             'failed': 0}), \
             mock.patch.object(launcher, 'do_clean'), \
             mock.patch.object(launcher, 'do_refresh', return_value=5), \
             mock.patch.object(launcher, 'QUIET', quiet), \
             mock.patch('kuraya.keys.read_key', read), \
             mock.patch.object(launcher, 'open_library', opened), \
             redirect_stdout(buffer):
            stats, offered = launcher.cmd_all(Path('lib'), Path('src'),
                                              {'yes': yes})
        return read, opened, offered

    def test_enter_opens_library(self):
        """默认高亮「打开片库」，回车即打开；交互过就不必再等回车"""
        read, opened, offered = self.run_all(keys=('enter',))
        read.assert_called_once()
        opened.assert_called_once()
        self.assertTrue(offered)

    def test_down_enter_skips(self):
        """↓ 切到「稍后再说」再回车，不打开"""
        read, opened, offered = self.run_all(keys=('down', 'enter'))
        opened.assert_not_called()
        self.assertTrue(offered)

    def test_esc_skips(self):
        read, opened, offered = self.run_all(keys=('esc',))
        opened.assert_not_called()
        self.assertTrue(offered)

    def test_down_redraws_selection(self):
        """方向键后上移重绘选择区，两行选项 + 提示行"""
        buffer = io.StringIO()
        opened = mock.Mock()
        with mock.patch('kuraya.keys.read_key',
                        side_effect=['down', 'enter']), \
             mock.patch.object(launcher, 'open_library', opened), \
             redirect_stdout(buffer):
            launcher.offer_open_library(Path('lib'))
        out = buffer.getvalue()
        self.assertIn('\x1b[3A', out)          # 上移三行重绘（两选项 + 提示）
        self.assertIn('稍后再说', out)          # 第二项存在
        opened.assert_not_called()

    def test_quiet_skips_prompt(self):
        read, opened, offered = self.run_all(quiet=True)
        read.assert_not_called()
        opened.assert_not_called()
        self.assertFalse(offered)

    def test_yes_skips_prompt(self):
        read, opened, offered = self.run_all(yes=True)
        read.assert_not_called()
        opened.assert_not_called()
        self.assertFalse(offered)


if __name__ == '__main__':
    unittest.main()
