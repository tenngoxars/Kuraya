# -*- coding: utf-8 -*-
"""
片库页面生成产物契约：分批渲染所需的结构必须存在于生成的 index.html。
直接调用 gallery 函数（与生产路径一致），不走裸脚本子进程。

    python -m unittest discover tests
"""
import io
import os
import shutil
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from xml.sax.saxutils import escape as xml_escape

from kuraya import gallery

NFO = """<?xml version="1.0" encoding="UTF-8" ?>
<movie>
  <title>TEST-001-测试作品</title>
  <num>TEST-001</num>
  <studio>STUDIO-X</studio>
  <label>LABEL-X</label>
  <premiered>2025-01-01</premiered>
  <runtime>120</runtime>
  <poster>TEST-001-poster.jpg</poster>
  <actor><name>测试演员</name></actor>
</movie>
"""


def build_page(age_days=0, label='LABEL-X'):
    """在临时目录造最小影片库并生成页面，返回 index.html 文本。
    age_days 回拨视频文件 mtime——「新入库」按 mtime 判定；
    label 用于注入含特殊字符的发行商元数据（nfo 是 XML，写入前按 XML 转义）"""
    with tempfile.TemporaryDirectory() as tmp:
        cdir = Path(tmp) / '测试演员' / 'TEST-001'
        cdir.mkdir(parents=True)
        (cdir / 'TEST-001.nfo').write_text(
            NFO.replace('LABEL-X', xml_escape(label)), encoding='utf-8')
        (cdir / 'TEST-001-poster.jpg').write_bytes(b'')
        video = cdir / 'TEST-001.mp4'
        video.write_bytes(b'')
        if age_days:
            past = time.time() - age_days * 86400
            os.utime(video, (past, past))
        with redirect_stdout(io.StringIO()):
            code = gallery.main([tmp])
        assert code == 0
        return (Path(tmp) / 'index.html').read_text(encoding='utf-8')


class GalleryContract(unittest.TestCase):
    """分批渲染依赖的产物结构：sentinel 哨兵与首屏批量常量"""

    def test_page_contains_sentinel_and_page_size(self):
        """页面必须含 #sentinel（滚动追加的观察目标）与 PAGE=60 首屏常量，
        缺失会让大库分批渲染静默失效"""
        html = build_page()
        self.assertIn('id="sentinel"', html)
        self.assertIn('const PAGE = 60', html)

    def test_search_normalizes_separators(self):
        """搜索归一化的分隔符表与预处理必须都在产物里，少了任一段
        abc001 就搜不到 ABC-001，而页面本身不会报错。
        断言只取各自唯一的那一行——匹配到别处也有的片段等于没测"""
        html = build_page()
        self.assertIn('const SEPARATORS', html)
        self.assertIn('it._squashed = it._fields.map(squash)', html)

    def test_page_uses_distributor_not_studio(self):
        """片库页面显示发行商，制作商仍只留在 NFO 中"""
        html = build_page()
        self.assertIn('LABEL-X', html)
        self.assertNotIn('STUDIO-X', html)

    def test_page_contains_recoverable_delete_action(self):
        """页面通过 kuraya 协议请求移入废纸篓，不直接执行任意文件操作"""
        html = build_page()
        for fragment in (
                'delete_path:', 'kuraya:delete:', 'requestDelete',
                'className = "delete-btn"', 'id="confirmModal"',
                'role="dialog"', 'confirmDelete', '.card:hover .delete-btn',
                '.delete-btn:focus-visible', '@media (hover: none)',
                'function deletePollState', 'scheduleDeleteReload',
                'role", "status"', 'aria-live', 'confirmTarget',
                'location.replace(url.href)', 'deleteStatus("error"',
                'restoreDeleteItems', 'DATA.splice(0, DATA.length',
                'item: it', 'scrollY: window.scrollY',
                'lastDeleteSnapshot', 'latestFilters',
                'restoreDeleteView', 'applyDeleteFilters'):
                with self.subTest(fragment=fragment):
                    self.assertIn(fragment, html)
        self.assertNotIn('.card:focus-within .delete-btn', html)
        self.assertNotIn('window.confirm(', html)
        self.assertNotIn('window.location.reload()', html)

    def test_page_scripts_keep_dependency_order(self):
        """单文件脚本的顶层依赖顺序不能因拆分而踩 TDZ。"""
        html = build_page()
        for earlier, later in (
                ('const UI_LANG', 'function deletePollState'),
                ('function deletePollState', 'const confirmModal'),
                ('const confirmModal', 'const DATA'),
                ('const DATA', 'function buildChips')):
            with self.subTest(earlier=earlier, later=later):
                self.assertLess(html.index(earlier), html.index(later))

    def test_copy_mode_keeps_delete_action_disabled(self):
        """协议不可用时，生成页面必须明确处于 copy 模式并走删除能力守卫"""
        with mock.patch.object(gallery, 'play_mode', 'copy'):
            html = build_page()
        self.assertIn('const PLAY_MODE = "copy"', html)
        self.assertIn('deleteEnabled(PLAY_MODE)', html)

    def test_atomic_page_write_preserves_old_page_on_replace_failure(self):
        """新页面替换失败时，旧页面不能被截断或覆盖"""
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'index.html'
            output.write_text('old page', encoding='utf-8')
            with mock.patch.object(gallery.os, 'replace', side_effect=OSError('busy')):
                with self.assertRaises(OSError):
                    gallery.write_page_atomic(output, 'new page')
            self.assertEqual(output.read_text(encoding='utf-8'), 'old page')
            self.assertEqual(list(Path(tmp).glob('.index.html.*.tmp')), [])


class ScriptInjection(unittest.TestCase):
    """元数据来自第三方数据源，原样进 <script> 会截断脚本块"""

    EVIL = '</script><h1 id="broke">X</h1><script>'

    def test_closing_tag_in_metadata_does_not_break_out(self):
        """发行商名含 </script> 时页面里不能出现第二个 </script>——
        出现即脚本块被提前闭合，app.js 截断，整页零张卡片且不报错"""
        html = build_page(label=self.EVIL)
        self.assertEqual(html.count('</script>'), 1)

    def test_escaped_value_is_still_present(self):
        """转义只改字节表示不丢值：\\u003c 在 JS 字符串里还原成 <。
        断言取转义后的实际形态，直接断言 </script> 会被模板自带的那个命中"""
        html = build_page(label=self.EVIL)
        self.assertIn(r'\u003c/script>', html)

    def test_card_escapes_every_interpolated_field(self):
        """卡片靠 innerHTML 拼装，字段不转义则名字里的 <img onerror> 当场执行。
        逐个插值点断言——漏一个就是一条注入路径，而页面看不出异常"""
        html = build_page()
        self.assertIn('function esc(s)', html)
        for point in ('${esc(it.poster_url)}', '${esc(it.code)}',
                      '${esc(it.label)}', 'data-val="${esc(v)}"'):
            with self.subTest(point=point):
                self.assertIn(point, html)


class NewBadge(unittest.TestCase):
    """新入库角标：judgement 交给页面按 added_ts 现算，生成端只提供时间戳"""

    def test_added_ts_reflects_video_mtime(self):
        """页面要现算就得拿到入库时间，且必须是视频文件的 mtime。
        列式打包后时间戳是行里的最后一列，取整存（浮点小数位没有意义）"""
        import re
        html = build_page(age_days=30)
        row = re.search(r'const DATA = \[(\[.*?\])\]', html, re.S).group(1)
        ts = int(re.search(r'(\d{9,})\]$', row).group(1))
        self.assertAlmostEqual(ts, time.time() - 30 * 86400, delta=120)

    def test_judgement_is_not_baked_into_data(self):
        """判别性：生成时定死的话，页面放几天再打开角标就是过期的"""
        html = build_page()
        self.assertNotIn('"is_new"', html)

    def test_page_carries_badge_markup_and_style(self):
        """三处缺任一处，角标都不会出现：判定函数、卡片模板插值、样式规则"""
        html = build_page()
        self.assertIn('const badge = isNew(it)', html)
        self.assertIn('${badge}', html)
        self.assertIn('.badge-new::before', html)


class TopBar(unittest.TestCase):
    """顶栏：三维度切换、宽度自适应的筛选行、已激活筛选、总清空"""

    def test_three_dimensions_present(self):
        html = build_page()
        for key in ('"actor"', '"label"', '"director"'):
            with self.subTest(key=key):
                self.assertIn(f'key: {key}', html)

    def test_empty_dimensions_hidden_not_zeroed(self):
        """判别性：整库无导演时若还渲染「导演 0」按钮，点开只有「全部」，
        纯噪音——必须按实际计数过滤掉空维度"""
        html = build_page()
        self.assertIn('ALL_DIMS.filter(d => d.values.length > 0)', html)

    def test_chip_counts_follow_active_filters(self):
        """判别性：选演员后发行商/导演的计数必须基于当前筛选子集，
        不能还是全库静态值——维度自身筛选排除，其余维度与搜索生效"""
        html = build_page()
        for fragment in (
                'function filteredList(excludeKey)',
                'if (dim.key === excludeKey) continue',
                'function allDimCounts(excludeKey)',
                'const counts = allDimCounts(activeDim)',
                'counts[d.key].length',
                'const entries = counts[dim.key]'):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)

    def test_empty_subset_dimensions_hidden(self):
        """判别性：子集下无值的维度要隐藏（选演员后该演员没有导演片时
        不该出现「导演 0」），当前维度变空要自动切到有值的维度"""
        html = build_page()
        for fragment in (
                "if (!counts[d.key].length) continue;",
                'const fallback = DIMS.find(d => counts[d.key].length)',
                'if (!dims.children.length) { chipsEl.innerHTML = ""; return; }'):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)

    def test_empty_library_does_not_break_chips(self):
        """判别性：全部维度都为空（空库）时 DIMS 为空数组，
        buildChips 会找不到 activeDim 而崩——必须按 DIMS 是否为空
        提前返回，而不是依赖 activeDim 存在"""
        html = build_page()
        self.assertIn('if (!DIMS.length) { chipsEl.innerHTML = ""; return; }', html)

    def test_director_collected(self):
        """导演要能筛，打包字段里就得有它——顺序还必须与页面还原时一致"""
        html = build_page()
        self.assertIn('"label"', html)
        self.assertIn('"director"', html)
        self.assertEqual(gallery.PACK_FIELDS.index('director'), 4)

    def test_chip_count_is_measured_not_hardcoded(self):
        """判别性：写死 Top N 会在窄屏溢出、宽屏浪费。
        必须是实测右边界，且不能用 scrollWidth（不溢出时判据恒为真）"""
        html = build_page()
        self.assertIn('getBoundingClientRect().right', html)
        self.assertNotIn('chipsEl.scrollWidth', html)

    def test_sticky_block_wraps_toolbar_and_chips(self):
        """筛选行必须跟着吸顶，否则滚下去就改不了筛选"""
        html = build_page()
        self.assertIn('class="sticky-block"', html)
        self.assertIn('.sticky-block {', html)

    def test_reset_appears_only_when_dirty(self):
        html = build_page()
        self.assertIn('if (dirty()) {', html)
        self.assertIn('r.onclick = resetAll', html)

    def test_more_panel_search_uses_squash(self):
        """判别性：面板若还用裸 includes，ABC-001 在面板里就搜不到，
        与主搜索两套规则——必须走同一个 squash 归一化，且空 sq
        （纯分隔符查询）要跳过归一化分支，否则 includes("") 恒真"""
        html = build_page()
        self.assertIn('(sq && squash(n.toLowerCase()).includes(sq))', html)

    def test_more_panel_overflow_is_hinted_not_silent(self):
        """超过渲染上限的条目要提示可搜索，否则用户以为列表就这些"""
        html = build_page()
        self.assertIn('hits.length > 300', html)
        self.assertIn('t("moreHint"', html)

    def test_resize_observer_guarded_for_old_browsers(self):
        """判别性：FULL_RENDER 回退的老浏览器通常没有 ResizeObserver，
        裸调用会在脚本末尾抛 ReferenceError——必须带 in window 守卫"""
        html = build_page()
        self.assertIn('"ResizeObserver" in window', html)

    def test_clear_restores_browse_position(self):
        """筛选前的滚动位置要保存，清空后恢复，不能每次都回到顶部"""
        html = build_page()
        for fragment in (
                'let browseSnapshot = null',
                'function rememberBrowsePosition',
                'browseSnapshot = {scrollY: window.scrollY, rendered}',
                'browseRestoreSnapshot(browseSnapshot, dirty())',
                'browseRenderCount(restore, result.length, PAGE, FULL_RENDER)',
                'window.scrollTo({top, behavior: "auto"})'):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)

        set_filter = html[html.index('function setFilter'):html.index('function resetAll')]
        reset_all = html[html.index('function resetAll'):html.index('</script>')]
        self.assertIn('rememberBrowsePosition();', set_filter)
        self.assertIn('scrollAfterFilterChange();', set_filter)
        self.assertIn('render();', reset_all)

    def test_i18n_module_is_injected_before_app(self):
        """判别性：app.js 顶层就调用 t()/UI_LANG，若 i18n.js 拼在它后面
        会在定义前引用直接抛错，整页空白——顺序错了产物里 UI_LANG
        会出现在 esc 之后"""
        html = build_page()
        self.assertLess(html.index('const UI_LANG'), html.index('function esc'))


class Packing(unittest.TestCase):
    """列式打包：字段名与影片库基址各只写一次，页面按同序还原"""

    def lib(self, dirname, num, actors, poster='p.jpg'):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        d = tmp / actors[0] / dirname
        d.mkdir(parents=True)
        acts = ''.join(f'<actor><name>{a}</name></actor>' for a in actors)
        (d / f'{dirname}.nfo').write_text(
            f'<?xml version="1.0" encoding="UTF-8" ?><movie><num>{num}</num>'
            f'<studio>S</studio><label>L</label><premiered>2025-01-01</premiered>'
            f'<poster>{poster}</poster>{acts}</movie>', encoding='utf-8')
        (d / poster).write_bytes(b'')
        (d / f'{dirname}.mp4').write_bytes(b'')
        return gallery.pack(gallery.collect(str(tmp)))[0]

    def col(self, name):
        return gallery.PACK_FIELDS.index(name)

    def test_dir_omitted_when_same_as_code(self):
        """目录名与番号同名是常态，重复存一遍纯属浪费"""
        row = self.lib('ABC-001', 'ABC-001', ['演员甲'])
        self.assertEqual(row[self.col('dir')], '')

    def test_dir_kept_when_different_from_code(self):
        """判别性：nfo 的 num 可能与文件夹不同名，省掉就拼不出路径了"""
        row = self.lib('DIR-XYZ', 'NUM-999', ['演员甲'])
        self.assertEqual(row[self.col('dir')], 'DIR-XYZ')

    def test_dir_with_suffix_finds_plain_nfo(self):
        """下载目录常带后缀（4K/中文字幕等），nfo 文件名是纯番号时
        要能配对，否则整部片被跳过"""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        d = tmp / '演员甲' / 'ROE-490 4K 特別版'
        d.mkdir(parents=True)
        (d / 'ROE-490.nfo').write_text(
            '<?xml version="1.0" encoding="UTF-8" ?><movie><num>ROE-490</num>'
            '<label>L</label><premiered>2025-01-01</premiered>'
            '<poster>p.jpg</poster></movie>', encoding='utf-8')
        (d / 'p.jpg').write_bytes(b'')
        (d / 'ROE-490.mp4').write_bytes(b'')
        row = gallery.pack(gallery.collect(str(tmp)))[0]
        self.assertEqual(row[self.col('code')], 'ROE-490')
        self.assertEqual(row[self.col('dir')], 'ROE-490 4K 特別版')

    def _lib_nfo(self, body):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        d = tmp / '演员甲' / 'ROE-490'
        d.mkdir(parents=True)
        (d / 'ROE-490.nfo').write_text(
            '<?xml version="1.0" encoding="UTF-8" ?><movie>'
            f'{body}</movie>', encoding='utf-8')
        (d / 'p.jpg').write_bytes(b'')
        (d / 'ROE-490.mp4').write_bytes(b'')
        return gallery.pack(gallery.collect(str(tmp)))[0]

    def test_label_crossed_with_set_falls_back_to_studio(self):
        """旧引擎曾把系列名写进发行商（label==set），读取时应回退製作商"""
        series = '出張で泊まりに来た叔母と同居生活'
        row = self._lib_nfo(
            f'<num>ROE-490</num><label>{series}</label>'
            f'<set>{series}</set><studio>マドンナ</studio>'
            f'<premiered>2025-01-01</premiered><poster>p.jpg</poster>')
        # 回退拿到的片假名统一为罗马字，与正常数据的写法一致
        self.assertEqual(row[self.col('label')], 'Madonna')

    def test_label_kept_when_set_differs(self):
        """发行商与系列不同值是正常数据（如 JUQ-162），不能被回退误伤"""
        row = self._lib_nfo(
            '<num>ROE-490</num><label>MONROE</label>'
            '<set>出張で泊まりに来た叔母と同居生活</set>'
            '<studio>マドンナ</studio><premiered>2025-01-01</premiered>'
            '<poster>p.jpg</poster>')
        self.assertEqual(row[self.col('label')], 'MONROE')

    def test_katakana_label_romanized(self):
        """同一家厂牌两种写法（マドンナ/Madonna）统一为罗马字，
        否则筛选维度出现两个值"""
        row = self._lib_nfo(
            '<num>JUQ-162</num><label>マドンナ</label>'
            '<set>人妻秘書</set><studio>マドンナ</studio>'
            '<premiered>2025-01-01</premiered><poster>p.jpg</poster>')
        self.assertEqual(row[self.col('label')], 'Madonna')

    def test_unmapped_katakana_kept(self):
        """映射表外的片假名厂商保持原样，宁缺毋滥"""
        row = self._lib_nfo(
            '<num>ABC-001</num><label>ひかりTV</label>'
            '<set>シリーズX</set><studio>ひかりTV</studio>'
            '<premiered>2025-01-01</premiered><poster>p.jpg</poster>')
        self.assertEqual(row[self.col('label')], 'ひかりTV')

    def test_extended_katakana_mappings(self):
        """长尾片商映射：用户库实际遇到的厂牌逐家覆盖"""
        cases = {
            'エレガンス': 'ELEGANCE',
            'ティッシュ': 'TISSUE',
            'みんなのキカタン': 'MINNA NO KIKATAN',
            'HHHグループ': 'HHH GROUP',
            'アリスJAPAN': 'ALICE JAPAN',
            'アキノリ': 'AKINORI',
            'エムズビデオグループ': "M's VIDEO GROUP",
            'グローリークエスト': 'GLORY QUEST',
            'プラネットプラス': 'PLANET PLUS',
            'ロイヤル': 'ROYAL',
        }
        for katakana, expected in cases.items():
            with self.subTest(studio=katakana):
                row = self._lib_nfo(
                    f'<num>X-001</num><label>シリーズX</label>'
                    f'<set>シリーズX</set><studio>{katakana}</studio>'
                    f'<premiered>2025-01-01</premiered><poster>p.jpg</poster>')
                self.assertEqual(row[self.col('label')], expected)

    def test_roman_space_variants_unified(self):
        """罗马字写法带不带空格（IDEA POCKET / IDEAPOCKET）统一为表内标准"""
        for variant in ('IDEAPOCKET', 'IDEA POCKET', 'idea pocket'):
            with self.subTest(label=variant):
                row = self._lib_nfo(
                    f'<num>X-002</num><label>{variant}</label>'
                    f'<set>シリーズX</set><studio>アイデアポケット</studio>'
                    f'<premiered>2025-01-01</premiered><poster>p.jpg</poster>')
                self.assertEqual(row[self.col('label')], 'IDEA POCKET')

    def test_library_roman_variants_unified(self):
        """库内两种写法都出现时（MOODYZ DIVA / MOODYZDIVA），
        统一为出现多（平局取带空格）的标准写法——不依赖内置表"""
        rows = self._lib_multi([
            ('E-001', '<num>E-001</num><studio>ムーディーズ</studio>'
                      '<label>MOODYZ DIVA</label>'
                      '<premiered>2025-01-01</premiered>'),
            ('E-002', '<num>E-002</num><studio>ムーディーズ</studio>'
                      '<label>MOODYZ DIVA</label>'
                      '<premiered>2025-01-01</premiered>'),
            ('E-003', '<num>E-003</num><studio>ムーディーズ</studio>'
                      '<label>MOODYZDIVA</label>'
                      '<premiered>2025-01-01</premiered>'),
        ])
        labels = {r[self.col('label')] for r in rows}
        self.assertEqual(labels, {'MOODYZ DIVA'})

    def test_single_roman_variant_kept(self):
        """库里只有一种写法时不猜测，保持原样"""
        rows = self._lib_multi([
            ('F-001', '<num>F-001</num><studio>プレステージ</studio>'
                      '<label>PRESTIGE DIVA</label>'
                      '<premiered>2025-01-01</premiered>'),
        ])
        self.assertEqual(rows[0][self.col('label')], 'PRESTIGE DIVA')

    def test_fullwidth_space_variant_unified(self):
        """全角空格（IDEA　POCKET）与半角（IDEA POCKET）同样统一"""
        rows = self._lib_multi([
            ('G-001', '<num>G-001</num><studio>アイデアポケット</studio>'
                      '<label>IDEA POCKET</label>'
                      '<premiered>2025-01-01</premiered>'),
            ('G-002', '<num>G-002</num><studio>アイデアポケット</studio>'
                      '<label>IDEA\u3000POCKET</label>'
                      '<premiered>2025-01-01</premiered>'),
        ])
        labels = {r[self.col('label')] for r in rows}
        self.assertEqual(labels, {'IDEA POCKET'})

    def test_lowercase_variant_not_chosen_as_standard(self):
        """小写手写变体不喧宾夺主：同次数时全大写带空格的写法胜出"""
        rows = self._lib_multi([
            ('H-001', '<num>H-001</num><studio>プレステージ</studio>'
                      '<label>PRESTIGE DIVA</label>'
                      '<premiered>2025-01-01</premiered>'),
            ('H-002', '<num>H-002</num><studio>プレステージ</studio>'
                      '<label>prestige diva</label>'
                      '<premiered>2025-01-01</premiered>'),
        ])
        labels = {r[self.col('label')] for r in rows}
        self.assertEqual(labels, {'PRESTIGE DIVA'})

    def test_roman_studio_of_crossed_nfo_still_collected(self):
        """串位 nfo 只让 label 失去可信度，罗马字 studio 仍参与变体收集"""
        rows = self._lib_multi([
            ('I-001', '<num>I-001</num><studio>MOODYZ DIVA</studio>'
                      '<label>シリーズX</label><set>シリーズX</set>'
                      '<premiered>2025-01-01</premiered>'),
            ('I-002', '<num>I-002</num><studio>MOODYZDIVA</studio>'
                      '<label>シリーズX</label><set>シリーズX</set>'
                      '<premiered>2025-01-01</premiered>'),
        ])
        # 两片都串位：label 回退 studio 后，靠变体映射统一
        labels = {r[self.col('label')] for r in rows}
        self.assertEqual(labels, {'MOODYZ DIVA'})

    def _lib_multi(self, entries):
        """多条目库：entries = [(目录名, nfo body)]，返回 pack 后的行"""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for i, (dirname, body) in enumerate(entries):
            d = tmp / f'演员{i}' / dirname
            d.mkdir(parents=True)
            (d / f'{dirname}.nfo').write_text(
                f'<?xml version="1.0" encoding="UTF-8" ?><movie>'
                f'{body}</movie>', encoding='utf-8')
            (d / 'p.jpg').write_bytes(b'')
            (d / f'{dirname}.mp4').write_bytes(b'')
        return gallery.pack(gallery.collect(str(tmp)))

    def test_learned_map_romanizes_fallback(self):
        """库内多数投票：3 部本家片（マドンナ/Madonna）多于 1 部子品牌片
        （マドンナ/MONROE）时学到映射，串位回退的片也统一为 Madonna"""
        rows = self._lib_multi([
            ('A-001', '<num>A-001</num><studio>マドンナ</studio>'
                      '<label>Madonna</label><premiered>2025-01-01</premiered>'),
            ('A-002', '<num>A-002</num><studio>マドンナ</studio>'
                      '<label>Madonna</label><premiered>2025-01-01</premiered>'),
            ('A-003', '<num>A-003</num><studio>マドンナ</studio>'
                      '<label>Madonna</label><premiered>2025-01-01</premiered>'),
            ('A-004', '<num>A-004</num><studio>マドンナ</studio>'
                      '<label>MONROE</label><premiered>2025-01-01</premiered>'),
            ('A-005', '<num>A-005</num><label>シリーズX</label>'
                      '<set>シリーズX</set><studio>マドンナ</studio>'
                      '<premiered>2025-01-01</premiered>'),
        ])
        got = {r[self.col('code')]: r[self.col('label')] for r in rows}
        # 本家片与串位回退片统一为 Madonna；子品牌片 MONROE 是正常罗马字，原样保留
        self.assertEqual(got, {'A-001': 'Madonna', 'A-002': 'Madonna',
                               'A-003': 'Madonna', 'A-004': 'MONROE',
                               'A-005': 'Madonna'})

    def test_single_pair_not_learned(self):
        """只出现一次的 (studio, label) 对可能是子品牌，不采纳；
        串位回退的片保持片假名"""
        rows = self._lib_multi([
            ('B-001', '<num>B-001</num><studio>ABCスタジオ</studio>'
                      '<label>ABC Studio</label><premiered>2025-01-01</premiered>'),
            ('B-002', '<num>B-002</num><label>シリーズX</label>'
                      '<set>シリーズX</set><studio>ABCスタジオ</studio>'
                      '<premiered>2025-01-01</premiered>'),
        ])
        row = next(r for r in rows if r[self.col('code')] == 'B-002')
        self.assertEqual(row[self.col('label')], 'ABCスタジオ')

    def test_crossed_nfo_not_learning_evidence(self):
        """串位 nfo 的 label 是系列名，不可信：同系列多部串位片
        也不能把片假名错学成系列名"""
        rows = self._lib_multi([
            ('C-001', '<num>C-001</num><label>シリーズX</label>'
                      '<set>シリーズX</set><studio>ABCスタジオ</studio>'
                      '<premiered>2025-01-01</premiered>'),
            ('C-002', '<num>C-002</num><label>シリーズX</label>'
                      '<set>シリーズX</set><studio>ABCスタジオ</studio>'
                      '<premiered>2025-01-01</premiered>'),
            ('C-003', '<num>C-003</num><label>シリーズX</label>'
                      '<set>シリーズX</set><studio>ABCスタジオ</studio>'
                      '<premiered>2025-01-01</premiered>'),
        ])
        for r in rows:
            self.assertEqual(r[self.col('label')], 'ABCスタジオ')

    def test_builtin_table_wins_over_learning(self):
        """库里子品牌片多到投票偏向 MONROE 时，内置表的高置信
        映射（マドンナ→Madonna）仍然优先"""
        rows = self._lib_multi([
            ('D-001', '<num>D-001</num><studio>マドンナ</studio>'
                      '<label>MONROE</label><premiered>2025-01-01</premiered>'),
            ('D-002', '<num>D-002</num><studio>マドンナ</studio>'
                      '<label>MONROE</label><premiered>2025-01-01</premiered>'),
            ('D-003', '<num>D-003</num><studio>マドンナ</studio>'
                      '<label>MONROE</label><premiered>2025-01-01</premiered>'),
            ('D-004', '<num>D-004</num><label>シリーズX</label>'
                      '<set>シリーズX</set><studio>マドンナ</studio>'
                      '<premiered>2025-01-01</premiered>'),
        ])
        row = next(r for r in rows if r[self.col('code')] == 'D-004')
        self.assertEqual(row[self.col('label')], 'Madonna')

    def test_actors_omitted_when_same_as_folder(self):
        row = self.lib('ABC-001', 'ABC-001', ['演员甲'])
        self.assertEqual(row[self.col('actors')], '')

    def test_actors_kept_for_multi_actor(self):
        row = self.lib('ABC-001', 'ABC-001', ['演员甲', '演员乙'])
        self.assertEqual(row[self.col('actors')], '演员甲、演员乙')

    def test_added_is_integer(self):
        """浮点秒的小数位没有意义，每条白占八个字节"""
        row = self.lib('ABC-001', 'ABC-001', ['演员甲'])
        self.assertIsInstance(row[self.col('added')], int)

    def test_paths_are_not_percent_encoded(self):
        """预编码会让一个中日文字符膨胀成九个字符，编码交给页面现算"""
        row = self.lib('ABC-001', 'ABC-001', ['桃乃木かな'])
        self.assertEqual(row[self.col('folder')], '桃乃木かな')
        self.assertNotIn('%', row[self.col('folder')])

    def test_library_base_written_once(self):
        """基址若还留在每条记录里，列式就白做了"""
        html = build_page()
        self.assertEqual(html.count('const LIB_BASE = '), 1)


if __name__ == '__main__':
    unittest.main()
