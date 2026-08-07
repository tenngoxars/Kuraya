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
from xml.sax.saxutils import escape as xml_escape

from kuraya import gallery

NFO = """<?xml version="1.0" encoding="UTF-8" ?>
<movie>
  <title>TEST-001-测试作品</title>
  <num>TEST-001</num>
  <studio>STUDIO-X</studio>
  <premiered>2025-01-01</premiered>
  <runtime>120</runtime>
  <poster>TEST-001-poster.jpg</poster>
  <actor><name>测试演员</name></actor>
</movie>
"""


def build_page(age_days=0, studio='STUDIO-X'):
    """在临时目录造最小影片库并生成页面，返回 index.html 文本。
    age_days 回拨视频文件 mtime——「新入库」按 mtime 判定；
    studio 用于注入含特殊字符的元数据（nfo 是 XML，写入前按 XML 转义）"""
    with tempfile.TemporaryDirectory() as tmp:
        cdir = Path(tmp) / '测试演员' / 'TEST-001'
        cdir.mkdir(parents=True)
        (cdir / 'TEST-001.nfo').write_text(
            NFO.replace('STUDIO-X', xml_escape(studio)), encoding='utf-8')
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


class ScriptInjection(unittest.TestCase):
    """元数据来自第三方数据源，原样进 <script> 会截断脚本块"""

    EVIL = '</script><h1 id="broke">X</h1><script>'

    def test_closing_tag_in_metadata_does_not_break_out(self):
        """厂商名含 </script> 时页面里不能出现第二个 </script>——
        出现即脚本块被提前闭合，app.js 截断，整页零张卡片且不报错"""
        html = build_page(studio=self.EVIL)
        self.assertEqual(html.count('</script>'), 1)

    def test_escaped_value_is_still_present(self):
        """转义只改字节表示不丢值：\\u003c 在 JS 字符串里还原成 <。
        断言取转义后的实际形态，直接断言 </script> 会被模板自带的那个命中"""
        html = build_page(studio=self.EVIL)
        self.assertIn(r'\u003c/script>', html)

    def test_card_escapes_every_interpolated_field(self):
        """卡片靠 innerHTML 拼装，字段不转义则名字里的 <img onerror> 当场执行。
        逐个插值点断言——漏一个就是一条注入路径，而页面看不出异常"""
        html = build_page()
        self.assertIn('function esc(s)', html)
        for point in ('${esc(it.poster_url)}', '${esc(it.code)}',
                      '${esc(it.studio)}', 'data-val="${esc(v)}"'):
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
        for key in ('"actor"', '"studio"', '"director"'):
            with self.subTest(key=key):
                self.assertIn(f'key: {key}', html)

    def test_empty_dimensions_hidden_not_zeroed(self):
        """判别性：整库无导演时若还渲染「导演 0」按钮，点开只有「全部」，
        纯噪音——必须按实际计数过滤掉空维度"""
        html = build_page()
        self.assertIn('ALL_DIMS.filter(d => d.values.length > 0)', html)

    def test_empty_library_does_not_break_chips(self):
        """判别性：全部维度都为空（空库）时 DIMS 为空数组，
        buildChips 会找不到 activeDim 而崩——必须按 DIMS 是否为空
        提前返回，而不是依赖 activeDim 存在"""
        html = build_page()
        self.assertIn('if (!DIMS.length) { chipsEl.innerHTML = ""; return; }', html)

    def test_director_collected(self):
        """导演要能筛，打包字段里就得有它——顺序还必须与页面还原时一致"""
        html = build_page()
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
            f'<studio>S</studio><premiered>2025-01-01</premiered>'
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
