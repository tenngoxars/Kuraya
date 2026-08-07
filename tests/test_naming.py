# -*- coding: utf-8 -*-
"""
番号识别的测试。用例表见 .agentdocs/spec/引擎行为规格.md 第二节。

用标准库 unittest，不引入 pytest —— 项目的第三方依赖保持在 4 个。

    python -m unittest discover tests
"""
import unittest

from kuraya.media.naming import parse


class ParseNumber(unittest.TestCase):
    """基本形态：字母 + 数字，分隔符可有可无，一律归一为大写带连字符"""

    def test_standard(self):
        self.assertEqual(parse('XXX-000.mp4').number, 'XXX-000')

    def test_lowercase(self):
        self.assertEqual(parse('xxx-000.mp4').number, 'XXX-000')

    def test_no_separator(self):
        self.assertEqual(parse('xxx000.mp4').number, 'XXX-000')

    def test_five_letter_label(self):
        self.assertEqual(parse('UUUUU-555.mp4').number, 'UUUUU-555')

    def test_four_digit_serial(self):
        self.assertEqual(parse('TTTTT-3021.mp4').number, 'TTTTT-3021')


class StripNoise(unittest.TestCase):
    """文件名上的各种附着物"""

    def test_site_prefix(self):
        self.assertEqual(parse('example.com@XXX-000.mp4').number, 'XXX-000')

    def test_site_prefix_with_dash(self):
        self.assertEqual(parse('a-b.example@YYYY-111.mp4').number, 'YYYY-111')

    def test_brackets(self):
        self.assertEqual(parse('[JAV]WWW-333.mp4').number, 'WWW-333')

    def test_quality_prefix(self):
        self.assertEqual(parse('1080p-XXX-000.mp4').number, 'XXX-000')

    def test_quality_and_codec_suffix(self):
        self.assertEqual(parse('XXX-000.1080p.x265.mp4').number, 'XXX-000')

    def test_trailing_chinese_text(self):
        self.assertEqual(parse('YYYY-111 中文字幕.mp4').number, 'YYYY-111')


class Editions(unittest.TestCase):
    """版本标记"""

    def test_chinese_sub(self):
        got = parse('example.com@XXX-000-C.mp4')
        self.assertEqual(got.number, 'XXX-000')
        self.assertTrue(got.edition.chinese_sub)

    def test_chinese_sub_ch_after_digits(self):
        got = parse('XXX000ch.mp4')
        self.assertEqual(got.number, 'XXX-000')
        self.assertTrue(got.edition.chinese_sub)

    def test_chinese_sub_bare_c_after_digits(self):
        """下载站中字版常见 XXX-000C 命名：裸 C 紧跟数字。
        正规番号没有尾字母（javbus 无此形态），C 只可能是中字标记"""
        got = parse('XXX-000C.mp4')
        self.assertEqual(got.number, 'XXX-000')
        self.assertTrue(got.edition.chinese_sub)

    def test_chinese_sub_bare_c_lowercase(self):
        got = parse('XXX000c.mp4')
        self.assertEqual(got.number, 'XXX-000')
        self.assertTrue(got.edition.chinese_sub)

    def test_bare_c_does_not_consume_uc(self):
        """防回归锁（新旧代码均通过）：XXX000UC 的 C 属于 UC 流出标记
        （无分隔符时不剥），不能被裸 C 规则拆成 XXX-000 + 残留 U——
        保持无法识别，由数据源范围兜底"""
        self.assertIsNone(parse('XXX000UC.mp4'))

    def test_chinese_sub_by_keyword(self):
        self.assertTrue(parse('YYYY-111 中文字幕.mp4').edition.chinese_sub)

    def test_leaked_uc(self):
        got = parse('VVVV-444-UC.mp4')
        self.assertEqual(got.number, 'VVVV-444')
        self.assertTrue(got.edition.leaked)
        self.assertEqual(got.edition.leak_mark, '-UC')

    def test_leaked_u(self):
        got = parse('VVVV-444-U.mp4')
        self.assertEqual(got.number, 'VVVV-444')
        self.assertTrue(got.edition.leaked)
        self.assertEqual(got.edition.leak_mark, '-U')

    def test_leaked_is_not_chinese_sub(self):
        """现状的缺陷：-UC 会被连带标成中文字幕"""
        self.assertFalse(parse('VVVV-444-UC.mp4').edition.chinese_sub)

    def test_4k(self):
        got = parse('UUUUU-555-4K.mp4')
        self.assertEqual(got.number, 'UUUUU-555')
        self.assertTrue(got.edition.hd4k)

    def test_part(self):
        self.assertEqual(parse('YYYY-111-CD1.mkv').edition.part, 1)

    def test_part_underscore_lowercase(self):
        self.assertEqual(parse('YYYY-111_cd2.mkv').edition.part, 2)

    def test_part_and_chinese_sub(self):
        got = parse('ZZZ-222-C-CD1.mp4')
        self.assertEqual(got.number, 'ZZZ-222')
        self.assertEqual(got.edition.part, 1)
        self.assertTrue(got.edition.chinese_sub)


class OutOfShape(unittest.TestCase):
    """不符合「字母 + 数字」形态的一律返回 None，调用方原样留下文件"""

    def test_fc2(self):
        self.assertIsNone(parse('FC2-PPV-1234567.mp4'))

    def test_date_style(self):
        self.assertIsNone(parse('230825_001.mp4'))

    def test_carib(self):
        self.assertIsNone(parse('carib-123456-789.mp4'))

    def test_western_date(self):
        self.assertIsNone(parse('x-art.23.08.25.mp4'))

    def test_single_letter_label(self):
        self.assertIsNone(parse('n1234.mp4'))

    def test_chinese_only(self):
        self.assertIsNone(parse('新建文件夹.mp4'))

    def test_extension_only(self):
        self.assertIsNone(parse('.mp4'))

    def test_empty(self):
        self.assertIsNone(parse(''))


class ArchiveNames(unittest.TestCase):
    """识别结果决定归档后的文件名，顺序固定：分卷 → 中字 → 流出"""

    def test_plain(self):
        self.assertEqual(parse('XXX-000.mp4').stem(), 'XXX-000')

    def test_chinese_sub(self):
        self.assertEqual(parse('XXX-000-C.mp4').stem(), 'XXX-000-C')

    def test_part_before_chinese_sub(self):
        self.assertEqual(parse('ZZZ-222-C-CD1.mp4').stem(), 'ZZZ-222-CD1-C')

    def test_leak_mark_preserved(self):
        self.assertEqual(parse('VVVV-444-U.mp4').stem(), 'VVVV-444-U')

    def test_images_shared_across_parts(self):
        """分卷共用一套图，图片名不带 -CDn"""
        cd1 = parse('ZZZ-222-C-CD1.mp4')
        cd2 = parse('ZZZ-222-C-CD2.mp4')
        self.assertEqual(cd1.image_stem(), cd2.image_stem())
        self.assertEqual(cd1.image_stem(), 'ZZZ-222-C')
        self.assertNotEqual(cd1.stem(), cd2.stem())

    def test_4k_stays_out_of_filename(self):
        """4K 描述画质而非版本，只进 nfo 标签"""
        got = parse('UUUUU-555-4K.mp4')
        self.assertEqual(got.stem(), 'UUUUU-555')
        self.assertIn('4k', got.edition.extra_tags)


if __name__ == '__main__':
    unittest.main()
