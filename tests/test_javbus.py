# -*- coding: utf-8 -*-
"""
javbus 取值路径的测试。不联网，喂构造的 DOM。

只测一件事：字段边界。站点信息块是一串平铺的 <p>，一旦某个字段的值缺失、
或 </p> 漏掉，相邻字段的 header 就会落进同一个父节点——此时按父节点取链接
会把邻居的值取走，而且取到的是非空值，缺字段自检发现不了。

    python -m unittest discover tests
"""
import contextlib
import io
import unittest
from unittest import mock

from lxml import etree

from kuraya.media import javbus
from kuraya.media.javbus import XPATH, _actors, _jpeg_size, _mgs_package_cover, _one
from kuraya.media.model import Movie

# 各形状只写信息块片段，套壳交给 dom()
NORMAL = ('<p><span class="header">發行商:</span> <a>Madonna</a></p>'
          '<p><span class="header">系列:</span> <a>人妻秘書</a></p>')
NO_LABEL_ROW = '<p><span class="header">系列:</span> <a>人妻秘書</a></p>'
LABEL_NOT_LINKED = ('<p><span class="header">發行商:</span> ----</p>'
                    '<p><span class="header">系列:</span> <a>人妻秘書</a></p>')
HEADERS_SHARE_P = ('<p><span class="header">發行商:</span>'
                   '<span class="header">系列:</span> <a>人妻秘書</a></p>')
UNCLOSED_THEN_P = ('<p><span class="header">發行商:</span>'
                   '<p><span class="header">系列:</span> <a>人妻秘書</a></p>')
UNCLOSED_THEN_SPAN = ('<p><span class="header">發行商:</span>'
                      '<span class="header">系列:</span> <a>人妻秘書</a></p>')
BOTH_IN_ONE_P = ('<p><span class="header">發行商:</span> <a>Madonna</a>'
                 '<span class="header">系列:</span> <a>人妻秘書</a></p>')

# 头像墙。站点把 <span> 里的显示名按 15 字节截断，title 才是全名
WALL = ('<div id="avatar-waterfall">'
        '<a class="avatar-box"><div class="photo-frame">'
        '<img src="/pics/actress/1ny_a.jpg" title="明日花キララ"></div>'
        '<span>明日花キラ</span></a>'
        '<a class="avatar-box"><div class="photo-frame">'
        '<img src="/pics/actress/ef2_a.jpg" title="森沢かな（飯岡かなこ）"></div>'
        '<span>森沢かな（</span></a>'
        '<a class="avatar-box"><div class="photo-frame">'
        '<img src="/pics/actress/wcd_a.jpg" title="森日向子"></div>'
        '<span>森日向子</span></a></div>')

# 无头像的两种写法：占位图与 src 为空，两种都照常带 title
NO_PHOTO = ('<div id="avatar-waterfall">'
            '<a class="avatar-box"><div class="photo-frame">'
            '<img src="https://pics.dmm.co.jp/mono/actjpgs/nowprinting.gif"'
            ' title="橘内ひなた"></div><span>橘内ひなた</span></a>'
            '<a class="avatar-box"><div class="photo-frame">'
            '<img src="" title="有馬みずき"></div>'
            '<span>有馬みず</span></a></div>')

# title 缺失或为空。半截名也得取到人，少一位会让归档目录顺位落到下一位演员身上
NO_TITLE = ('<div id="avatar-waterfall">'
            '<a class="avatar-box"><div class="photo-frame">'
            '<img src="" title=""></div><span>喜多川みら</span></a>'
            '<a class="avatar-box"><div class="photo-frame">'
            '<img src=""></div><span>谷村凪咲</span></a></div>')

# 框里多一张带 title 的图（角标、徽章），不能被算成一位演员
EXTRA_IMG = ('<div id="avatar-waterfall">'
             '<a class="avatar-box"><div class="photo-frame">'
             '<img src="/pics/actress/wcd_a.jpg" title="森日向子">'
             '<img src="/pics/badge.png" title="獨佔"></div>'
             '<span>森日向子</span></a></div>')

EMPTY_WALL = '<div id="avatar-waterfall"></div>'


def dom(fragment):
    return etree.HTML(f'<html><body><div class="info">{fragment}</div></body></html>')


def fields(fragment):
    tree = dom(fragment)
    return _one(tree, 'label'), _one(tree, 'series')


def movie(label, series):
    """字段齐全的一部影片，只有发行商与系列按需要变化"""
    return Movie(number='XXX-000', title='示例标题',
                 cover_url='https://example.invalid/cover.jpg',
                 actors=('演员甲',), tags=('标签一',),
                 release='2026-08-07', runtime='135',
                 studio='示例制作商', label=label, series=series)


class WellFormed(unittest.TestCase):

    def test_each_field_in_its_own_p(self):
        self.assertEqual(fields(NORMAL), ('Madonna', '人妻秘書'))


class MissingValueYieldsEmpty(unittest.TestCase):
    """取不到值只能是空字符串，绝不能顺手取邻居的"""

    def test_label_row_absent(self):
        self.assertEqual(fields(NO_LABEL_ROW), ('', '人妻秘書'))

    def test_label_value_is_not_a_link(self):
        self.assertEqual(fields(LABEL_NOT_LINKED), ('', '人妻秘書'))

    def test_unclosed_p_then_series_starts_new_p(self):
        self.assertEqual(fields(UNCLOSED_THEN_P), ('', '人妻秘書'))


class FieldsNeverBleed(unittest.TestCase):
    """
    两个 header 落进同一个父节点的三种走法。按父节点取链接会在这里全线失守，
    issue #5 报的就是这个形状。
    """

    def test_two_headers_side_by_side(self):
        self.assertEqual(fields(HEADERS_SHARE_P), ('', '人妻秘書'))

    def test_unclosed_p_then_series_uses_span(self):
        self.assertEqual(fields(UNCLOSED_THEN_SPAN), ('', '人妻秘書'))

    def test_both_valued_in_one_p(self):
        """反向也要挡住：系列不能被写成发行商的值"""
        self.assertEqual(fields(BOTH_IN_ONE_P), ('Madonna', '人妻秘書'))


class ActorNamesAreWholeNames(unittest.TestCase):
    """
    头像墙的 <span> 是站点截断过的显示名——按 15 字节切，五个中日文字符以上
    的名字全被削一截，而且削出来的是非空值，缺字段自检一路放行。
    名字只能从 img 的 title 取。
    """

    def actors(self, fragment):
        return _actors(dom(fragment))

    def test_span_is_truncated_title_is_not(self):
        self.assertEqual(
            self.actors(WALL),
            ('明日花キララ', '森沢かな（飯岡かなこ）', '森日向子'))

    def test_actor_without_photo_is_still_named(self):
        """没头像不等于没名字，占位图与空 src 都得取到人"""
        self.assertEqual(self.actors(NO_PHOTO), ('橘内ひなた', '有馬みずき'))

    def test_no_actors_listed(self):
        """企划片本就不标演员，空是正常结果"""
        self.assertEqual(self.actors(EMPTY_WALL), ())

    def test_span_is_the_fallback_not_the_source(self):
        """title 取不到才退回 span：半截名难看，整个人消失更糟"""
        self.assertEqual(self.actors(NO_TITLE), ('喜多川みら', '谷村凪咲'))

    def test_one_name_per_box(self):
        """框里多出来的角标图不能变成一位演员，否则影片会归到它名下"""
        self.assertEqual(self.actors(EXTRA_IMG), ('森日向子',))


class EveryLinkedFieldIsBounded(unittest.TestCase):
    """製作商 / 發行商 / 系列 / 導演 是同一种形状，加固不能只做一半"""

    def test_all_four_pin_their_preceding_header(self):
        for key in ('studio', 'label', 'series', 'director'):
            with self.subTest(key=key):
                self.assertIn('preceding-sibling::span[@class="header"][1]',
                              XPATH[key])


class SelftestDetectsBleeding(unittest.TestCase):
    """
    串位的值是非空的，缺字段自检会一路全绿放行。这条盯的就是那个盲区：
    站点改版把两个字段并到一起时，selftest 必须报出来。
    """

    def run_selftest(self, movie):
        with mock.patch.object(javbus, 'fetch', return_value=movie), \
             mock.patch.object(javbus, '_PROBES', ('XXX-000',)), \
             contextlib.redirect_stdout(io.StringIO()):
            return javbus.selftest()

    def test_identical_label_and_series_fails(self):
        self.assertEqual(self.run_selftest(movie('同一个值', '同一个值')), 1)

    def test_distinct_values_pass(self):
        self.assertEqual(self.run_selftest(movie('示例发行商', '示例系列')), 0)

    def test_both_empty_is_not_bleeding(self):
        """系列本来就常缺，不能因为双空就报警"""
        self.assertEqual(self.run_selftest(movie('', '')), 0)


def jpeg(width, height):
    """造一个只带 SOF0 段的最小 JPEG，够 _jpeg_size 读出尺寸。"""
    return (b'\xff\xd8\xff\xc0\x00\x11\x08'
            + height.to_bytes(2, 'big') + width.to_bytes(2, 'big') + b'\x03\x00\xff\xd9')


# MGS 系页面：截图地址与包图同目录，包图靠 cap_e 推出来
MGS_PAGE = ('<a class="bigImage" href="/pics/cover/ck0l_b.jpg">'
            '<img src="https://image.mgstage.com/images/planetplus/263clot/044/'
            'cap_e_0_263clot-044.jpg">'
            '<img src="https://image.mgstage.com/images/planetplus/263clot/044/'
            'cap_e_10_263clot-044.jpg">')
NO_MGS_PAGE = '<a class="bigImage" href="/pics/cover/byk7_b.jpg"></a>'

JAVBUS_COVER = 'https://www.javbus.com/pics/cover/ck0l_b.jpg'
PACKAGE_COVER = 'https://image.mgstage.com/images/planetplus/263clot/044/pf_e_263clot-044.jpg'


class MgsPackageCover(unittest.TestCase):
    """
    javbus 对 MGS 系的片子存的是横版宣传图（左边一条厂牌 logo），贴到竖版墙上
    会被裁得认不出。页面上带 mgstage 截图地址时，同目录的 pf_e 才是竖版包图。
    """

    def test_url_derived_from_first_capture(self):
        self.assertEqual(_mgs_package_cover(MGS_PAGE), PACKAGE_COVER)

    def test_page_without_mgstage_yields_nothing(self):
        self.assertEqual(_mgs_package_cover(NO_MGS_PAGE), '')

    def test_empty_page_yields_nothing(self):
        self.assertEqual(_mgs_package_cover(''), '')


class JpegSize(unittest.TestCase):

    def test_reads_sof_dimensions(self):
        self.assertEqual(_jpeg_size(jpeg(840, 564)), (840, 564))

    def test_rejects_other_bytes(self):
        self.assertIsNone(_jpeg_size(b'<html>not an image</html>'))

    def test_rejects_truncated_header(self):
        self.assertIsNone(_jpeg_size(b'\xff\xd8\xff\xc0'))


class CoverPrefersPortrait(unittest.TestCase):
    """
    竖版优先：DMM 有的母版本身就是横版大图，javbus 对 MGS 系存的也是横版宣传图，
    这两种直接上墙都会被裁得认不出。一个竖版都拿不到时才退回横版。
    """

    DMM_URL = javbus._dmm_candidates('CLOT-044')[0]

    def patch_network(self, sizes, head=0):
        """sizes: {url: (宽, 高)}，未列出的地址当作取不到"""
        def fake_get_bytes(url, headers=None):
            if url in sizes:
                return jpeg(*sizes[url])
            raise javbus.http.Unavailable(url)
        return (mock.patch.object(javbus.http, 'head_size', return_value=head),
                mock.patch.object(javbus.http, 'get_bytes', side_effect=fake_get_bytes))

    def test_portrait_dmm_master_wins(self):
        head, get = self.patch_network({self.DMM_URL: (1200, 1700),
                                        PACKAGE_COVER: (422, 600),
                                        JAVBUS_COVER: (379, 537)}, head=200000)
        with head, get:
            self.assertEqual(javbus.cover_url('CLOT-044', '/pics/cover/ck0l_b.jpg', MGS_PAGE),
                             self.DMM_URL)

    def test_landscape_dmm_master_falls_through_to_portrait(self):
        """母版是横版时不认体积，改用竖版那张"""
        head, get = self.patch_network({self.DMM_URL: (2184, 1468),
                                        JAVBUS_COVER: (379, 537)}, head=200000)
        with head, get:
            self.assertEqual(javbus.cover_url('CLOT-044', '/pics/cover/ck0l_b.jpg', MGS_PAGE),
                             JAVBUS_COVER)

    def test_package_preferred_when_no_dmm_master(self):
        head, get = self.patch_network({PACKAGE_COVER: (422, 600),
                                        JAVBUS_COVER: (840, 564)})
        with head, get:
            self.assertEqual(javbus.cover_url('CLOT-044', '/pics/cover/ck0l_b.jpg', MGS_PAGE),
                             PACKAGE_COVER)

    def test_portrait_javbus_cover_is_kept(self):
        head, get = self.patch_network({JAVBUS_COVER: (379, 537)})
        with head, get:
            self.assertEqual(javbus.cover_url('CLOT-037', '/pics/cover/ck0l_b.jpg', MGS_PAGE),
                             JAVBUS_COVER)

    def test_landscape_without_package_keeps_javbus(self):
        """页面上没有 mgstage 地址时，宁可用横版也不凭空造一个地址"""
        head, get = self.patch_network({JAVBUS_COVER: (840, 564)})
        with head, get:
            self.assertEqual(javbus.cover_url('XXXX-001', '/pics/cover/ck0l_b.jpg', NO_MGS_PAGE),
                             JAVBUS_COVER)

    def test_all_landscape_returns_the_biggest(self):
        """一张竖版都没有时，退回体积最大的那张，不做无米之炊"""
        head, get = self.patch_network({self.DMM_URL: (2184, 1468),
                                        JAVBUS_COVER: (800, 538)}, head=200000)
        with head, get:
            self.assertEqual(javbus.cover_url('CLOT-044', '/pics/cover/ck0l_b.jpg', NO_MGS_PAGE),
                             self.DMM_URL)

    def test_no_candidate_reachable_returns_empty(self):
        head, get = self.patch_network({})
        with head, get:
            self.assertEqual(javbus.cover_url('XXXX-003', '', NO_MGS_PAGE), '')


class ImageHeaders(unittest.TestCase):

    def test_javbus_image_carries_user_agent(self):
        """urllib 直取图时没有默认 UA，请求头里必须自带一个，否则 403"""
        self.assertIn('User-Agent', javbus.image_headers(JAVBUS_COVER))

    def test_dmm_image_keeps_its_referer(self):
        self.assertEqual(javbus.image_headers('https://awsimgsrc.dmm.co.jp/x/pl.jpg'),
                         {'Referer': 'https://www.dmm.co.jp/'})


if __name__ == '__main__':
    unittest.main()
