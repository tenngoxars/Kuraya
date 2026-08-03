# -*- coding: utf-8 -*-
"""
nfo 生成的测试。字段契约见 .agentdocs/spec/引擎行为规格.md 第一节。

重点不在「标签写没写对」，而在两件会静默出问题的事：
gallery.py 能不能解析出它要的六个字段，以及脏文本会不会让整份 nfo 变得无法解析。

    python -m unittest discover tests
"""
import unittest
import xml.etree.ElementTree as ET

from kuraya.media.model import Assets, Edition, Movie
from kuraya.media.nfo import render

MOVIE = Movie(
    number='XXX-000',
    title='示例标题',
    cover_url='https://example.invalid/cover.jpg',
    actors=('演员甲', '演员乙'),
    tags=('标签一', '标签二'),
    release='2026-08-07',
    runtime='135',
    studio='示例制作商',
    label='示例发行商',
    series='示例系列',
    director='示例导演',
)

ASSETS = Assets(poster='XXX-000-poster.jpg',
                fanart='XXX-000-fanart.jpg',
                thumb='XXX-000-thumb.jpg')


def build(movie=MOVIE, edition=Edition(), assets=ASSETS):
    return render(movie, edition, assets)


def root_of(text):
    return ET.fromstring(text)


class Shape(unittest.TestCase):

    def test_header(self):
        self.assertTrue(build().startswith('<?xml version="1.0" encoding="UTF-8" ?>\n'))

    def test_root_is_movie(self):
        self.assertEqual(root_of(build()).tag, 'movie')

    def test_ends_with_newline(self):
        self.assertTrue(build().endswith('\n'))

    def test_fields_present_even_when_empty(self):
        """字段集固定，数据源缺字段时输出空元素而非少一个元素"""
        bare = Movie(number='XXX-000', title='', cover_url='')
        root = root_of(build(movie=bare))
        for tag in ('title', 'studio', 'premiered', 'runtime', 'plot', 'set'):
            self.assertIsNotNone(root.find(tag), tag)


class GalleryContract(unittest.TestCase):
    """gallery.py 实际读取的六个字段，缺一个就是一张显示不全的卡片"""

    def setUp(self):
        self.root = root_of(build())

    def get(self, tag):
        el = self.root.find(tag)
        return el.text.strip() if el is not None and el.text else ''

    def test_num(self):
        self.assertEqual(self.get('num'), 'XXX-000')

    def test_studio(self):
        self.assertEqual(self.get('studio'), '示例制作商')

    def test_premiered(self):
        self.assertEqual(self.get('premiered'), '2026-08-07')

    def test_runtime_is_bare_number(self):
        self.assertEqual(self.get('runtime'), '135')

    def test_poster(self):
        self.assertEqual(self.get('poster'), 'XXX-000-poster.jpg')

    def test_actors(self):
        names = [a.findtext('name', '').strip() for a in self.root.findall('actor')]
        self.assertEqual(names, ['演员甲', '演员乙'])


class Fields(unittest.TestCase):

    def test_title_is_prefixed_with_number(self):
        self.assertEqual(root_of(build()).findtext('title'),
                         'XXX-000-示例标题')

    def test_title_falls_back_to_number(self):
        bare = Movie(number='XXX-000', title='', cover_url='')
        self.assertEqual(root_of(build(movie=bare)).findtext('title'), 'XXX-000')

    def test_title_variants_agree(self):
        root = root_of(build())
        self.assertEqual(root.findtext('title'), root.findtext('originaltitle'))
        self.assertEqual(root.findtext('title'), root.findtext('sorttitle'))

    def test_num_has_no_edition_suffix(self):
        """带标记会让中字版与原版在片库页面上显示成两张卡片"""
        root = root_of(build(edition=Edition(part=1, chinese_sub=True)))
        self.assertEqual(root.findtext('num'), 'XXX-000')

    def test_year_from_release(self):
        self.assertEqual(root_of(build()).findtext('year'), '2026')

    def test_three_date_fields_agree(self):
        root = root_of(build())
        for tag in ('premiered', 'releasedate', 'release'):
            self.assertEqual(root.findtext(tag), '2026-08-07')

    def test_maker_mirrors_studio(self):
        root = root_of(build())
        self.assertEqual(root.findtext('maker'), root.findtext('studio'))

    def test_label_and_series_are_distinct(self):
        root = root_of(build())
        self.assertEqual(root.findtext('label'), '示例发行商')
        self.assertEqual(root.findtext('set'), '示例系列')

    def test_rating(self):
        root = root_of(build())
        self.assertEqual(root.findtext('customrating'), 'JP-18+')
        self.assertEqual(root.findtext('mpaa'), 'JP-18+')

    def test_plot_empty_when_no_outline(self):
        """javbus 不提供简介，字段仍在，内容为空"""
        self.assertIn(root_of(build()).findtext('plot'), ('', None))

    def test_plot_is_number_hash_outline(self):
        movie = Movie(number='XXX-000', title='t', cover_url='', outline='梗概')
        root = root_of(build(movie=movie))
        self.assertEqual(root.findtext('plot'), 'XXX-000#梗概')
        self.assertEqual(root.findtext('outline'), 'XXX-000#梗概')


class Tags(unittest.TestCase):

    def tags_of(self, root, tag):
        return [el.text for el in root.findall(tag)]

    def test_tag_and_genre_are_paired(self):
        root = root_of(build())
        self.assertEqual(self.tags_of(root, 'tag'), self.tags_of(root, 'genre'))

    def test_source_tags_kept_in_order(self):
        self.assertEqual(self.tags_of(root_of(build()), 'tag'),
                         ['标签一', '标签二'])

    def test_edition_tags_come_first(self):
        root = root_of(build(edition=Edition(chinese_sub=True, hd4k=True)))
        self.assertEqual(self.tags_of(root, 'tag'),
                         ['中文字幕', '4k', '标签一', '标签二'])

    def test_no_edition_tags_by_default(self):
        self.assertNotIn('中文字幕', self.tags_of(root_of(build()), 'tag'))


class NoRatings(unittest.TestCase):
    """javbus 不提供评分，相关字段一概不写，也不回读旧 nfo"""

    def test_absent(self):
        root = root_of(build())
        for tag in ('rating', 'criticrating', 'ratings', 'userrating'):
            self.assertIsNone(root.find(tag), tag)


class DirtyText(unittest.TestCase):
    """站点文本进 nfo 前必须无害化，否则整份文件解析失败、影片在片库里凭空消失"""

    def make(self, title):
        return build(movie=Movie(number='XXX-000', title=title, cover_url=''))

    def test_ampersand_and_angle_brackets(self):
        text = self.make('A & B <C>')
        self.assertEqual(root_of(text).findtext('title'), 'XXX-000-A & B <C>')

    def test_cdata_terminator(self):
        text = self.make('危险]]>片段')
        self.assertEqual(root_of(text).findtext('title'), 'XXX-000-危险]]>片段')

    def test_control_characters_removed(self):
        text = self.make('前\x00\x08后')
        self.assertEqual(root_of(text).findtext('title'), 'XXX-000-前后')

    def test_dirty_actor_name(self):
        movie = Movie(number='XXX-000', title='t', cover_url='', actors=('A & B',))
        root = root_of(build(movie=movie))
        self.assertEqual(root.find('actor').findtext('name'), 'A & B')


if __name__ == '__main__':
    unittest.main()
