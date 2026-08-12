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
from kuraya.media.javbus import XPATH, _one
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


if __name__ == '__main__':
    unittest.main()
