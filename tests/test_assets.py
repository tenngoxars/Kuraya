# -*- coding: utf-8 -*-
"""
封面处理的测试。规则见 .agentdocs/spec/引擎行为规格.md 第四节。

裁剪算式是纯函数，单独测；下载那一半要联网，不在单元测试里跑，
由 kuraya.media.javbus 的自测覆盖。

    python -m unittest discover tests
"""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from kuraya.media import assets
from kuraya.media.assets import Cover, CoverFailed, poster_box


class PosterBox(unittest.TestCase):
    """封面是左背板右海报，海报在右侧"""

    def test_typical_cover_takes_right_side(self):
        box = poster_box(800, 538)
        self.assertEqual(box[1:], (0, 800, 538))
        self.assertGreater(box[0], 0)

    def test_cropped_result_is_near_two_thirds(self):
        left, _, right, bottom = poster_box(800, 538)
        self.assertAlmostEqual((right - left) / bottom, 2 / 3, delta=0.06)

    def test_exact_ratio_is_not_cropped(self):
        self.assertIsNone(poster_box(400, 600))

    def test_narrow_image_cut_from_top(self):
        """比 2:3 还窄时从顶部往下切，底部通常是文字条"""
        self.assertEqual(poster_box(400, 900), (0, 0, 400, 600))

    def test_narrow_but_shorter_than_target(self):
        """算出的下边界超过实际高度时不能越界"""
        left, top, right, bottom = poster_box(400, 620)
        self.assertLessEqual(bottom, 620)

    def test_left_never_negative(self):
        left, *_ = poster_box(3, 2000)
        self.assertGreaterEqual(left, 0)

    def test_zero_size_rejected(self):
        with self.assertRaises(CoverFailed):
            poster_box(0, 538)


class Extension(unittest.TestCase):
    """扩展名跟随封面地址，认不出的一律按 jpg"""

    def test_known(self):
        self.assertEqual(assets._extension('https://x.invalid/a/b.png'), '.png')

    def test_uppercase(self):
        self.assertEqual(assets._extension('https://x.invalid/a/b.JPG'), '.jpg')

    def test_unknown_falls_back(self):
        self.assertEqual(assets._extension('https://x.invalid/a/b.webp'), '.jpg')

    def test_no_extension(self):
        self.assertEqual(assets._extension('https://x.invalid/image'), '.jpg')

    def test_query_string_ignored(self):
        self.assertEqual(assets._extension('https://x.invalid/b.png?v=2'), '.png')


class Build(unittest.TestCase):
    """由已下载的 fanart 派生 poster 与 thumb"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def make_cover(self, size=(800, 538), extension='.jpg', mode='RGB', fmt=None):
        path = self.dest / f'XXX-000-fanart{extension}'
        Image.new(mode, size, 'white').save(path, format=fmt)
        return Cover(path=path, stem='XXX-000', extension=extension)

    def test_three_files_written(self):
        built = assets.build(self.make_cover())
        for name in (built.poster, built.fanart, built.thumb):
            self.assertTrue((self.dest / name).is_file(), name)

    def test_names(self):
        built = assets.build(self.make_cover())
        self.assertEqual(built.poster, 'XXX-000-poster.jpg')
        self.assertEqual(built.fanart, 'XXX-000-fanart.jpg')
        self.assertEqual(built.thumb, 'XXX-000-thumb.jpg')

    def test_poster_is_portrait(self):
        built = assets.build(self.make_cover())
        with Image.open(self.dest / built.poster) as poster:
            self.assertLess(poster.width, poster.height)

    def test_thumb_matches_fanart(self):
        built = assets.build(self.make_cover())
        self.assertEqual((self.dest / built.thumb).read_bytes(),
                         (self.dest / built.fanart).read_bytes())

    def test_extension_carried_through(self):
        built = assets.build(self.make_cover(extension='.png'))
        self.assertEqual(built.poster, 'XXX-000-poster.png')

    def test_transparent_source_saved_as_jpeg(self):
        """
        地址后缀是 .jpg、内容却是带 alpha 的 PNG —— 图床上并不罕见。
        扩展名跟地址走，于是要把 RGBA 存成 JPEG，不转 RGB 就会报错。
        """
        built = assets.build(self.make_cover(mode='RGBA', fmt='PNG'))
        self.assertTrue((self.dest / built.poster).is_file())

    def test_broken_file_is_reported(self):
        path = self.dest / 'XXX-000-fanart.jpg'
        path.write_bytes(b'<html>403 Forbidden</html>')
        with self.assertRaises(CoverFailed):
            assets.build(Cover(path=path, stem='XXX-000', extension='.jpg'))


if __name__ == '__main__':
    unittest.main()
