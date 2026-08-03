# -*- coding: utf-8 -*-
"""
归档的测试。布局契约见 .agentdocs/spec/引擎行为规格.md 第一节。

全部在临时目录里跑，不碰真实影片库。

    python -m unittest discover tests
"""
import tempfile
import unittest
from pathlib import Path

from kuraya.media import archive
from kuraya.media.archive import ArchiveFailed
from kuraya.media.model import Movie

MOVIE = Movie(number='XXX-000', title='标题', cover_url='',
              actors=('演员甲', '演员乙'))


class Layout(unittest.TestCase):
    """演员名/番号"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.library = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_folder_path(self):
        folder = archive.prepare(MOVIE, self.library)
        self.assertEqual(folder, self.library / '演员甲' / 'XXX-000')
        self.assertTrue(folder.is_dir())

    def test_first_actor_only(self):
        folder = archive.prepare(MOVIE, self.library)
        self.assertEqual(folder.parent.name, '演员甲')

    def test_anonymous_when_no_actor(self):
        movie = Movie(number='XXX-000', title='t', cover_url='')
        folder = archive.prepare(movie, self.library)
        self.assertEqual(folder.parent.name, '佚名')

    def test_illegal_characters_removed(self):
        movie = Movie(number='XXX-000', title='t', cover_url='',
                      actors=('A/B\\C:D*E?F"G<H>I|J',))
        folder = archive.prepare(movie, self.library)
        self.assertEqual(folder.parent.name, 'ABCDEFGHIJ')
        self.assertTrue(folder.is_dir())

    def test_parentheses_kept(self):
        """艺名改名记法带括号，剔除会为同一位演员另开一个目录"""
        movie = Movie(number='XXX-000', title='t', cover_url='',
                      actors=('演员丁（旧艺名）',))
        folder = archive.prepare(movie, self.library)
        self.assertEqual(folder.parent.name, '演员丁（旧艺名）')

    def test_reuse_existing_folder(self):
        first = archive.prepare(MOVIE, self.library)
        (first / 'XXX-000-CD1.mp4').write_bytes(b'x')
        second = archive.prepare(MOVIE, self.library)
        self.assertEqual(first, second)
        self.assertTrue((second / 'XXX-000-CD1.mp4').is_file())

    def test_cannot_create_raises(self):
        """建目录失败要抛出来，不能静默终止整个进程"""
        blocker = self.library / '演员甲'
        blocker.write_bytes(b'not a folder')
        with self.assertRaises(ArchiveFailed):
            archive.prepare(MOVIE, self.library)


class StoreVideo(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source = root / '待整理' / 'XXX-000'
        self.source.mkdir(parents=True)
        self.folder = root / '演员甲' / 'XXX-000'
        self.folder.mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)

    def make(self, name, data=b'video'):
        path = self.source / name
        path.write_bytes(data)
        return path

    def test_moved_and_renamed(self):
        video = self.make('example.com@XXX-000-C.mp4')
        target = archive.store(video, self.folder, 'XXX-000-C')
        self.assertEqual(target.name, 'XXX-000-C.mp4')
        self.assertTrue(target.is_file())
        self.assertFalse(video.exists())

    def test_extension_lowercased(self):
        video = self.make('XXX-000.MP4')
        self.assertEqual(archive.store(video, self.folder, 'XXX-000').name,
                         'XXX-000.mp4')

    def test_parts_do_not_collide(self):
        """影片本体带分卷标记，第二卷才不会撞上第一卷"""
        first = self.make('XXX-000-CD1.mp4', b'one')
        second = self.make('XXX-000-CD2.mp4', b'two')
        archive.store(first, self.folder, 'XXX-000-CD1')
        archive.store(second, self.folder, 'XXX-000-CD2')
        self.assertEqual((self.folder / 'XXX-000-CD1.mp4').read_bytes(), b'one')
        self.assertEqual((self.folder / 'XXX-000-CD2.mp4').read_bytes(), b'two')

    def test_existing_target_raises(self):
        (self.folder / 'XXX-000.mp4').write_bytes(b'old')
        video = self.make('XXX-000.mp4')
        with self.assertRaises(ArchiveFailed):
            archive.store(video, self.folder, 'XXX-000')
        self.assertTrue(video.exists(), '失败时源文件应留在原地')


class Subtitles(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source = root / '待整理' / 'XXX-000'
        self.source.mkdir(parents=True)
        self.folder = root / '演员甲' / 'XXX-000'
        self.folder.mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)
        self.video = self.source / 'XXX-000-C.mp4'
        self.video.write_bytes(b'video')

    def test_same_name_subtitle(self):
        (self.source / 'XXX-000-C.srt').write_text('sub', encoding='utf-8')
        archive.store(self.video, self.folder, 'XXX-000-C')
        self.assertTrue((self.folder / 'XXX-000-C.srt').is_file())

    def test_language_tagged_subtitle(self):
        """`影片名.chs.srt` 是常见写法，漏下会被随后的清理步骤删掉"""
        (self.source / 'XXX-000-C.chs.srt').write_text('sub', encoding='utf-8')
        archive.store(self.video, self.folder, 'XXX-000-C')
        self.assertTrue((self.folder / 'XXX-000-C.chs.srt').is_file())

    def test_multiple_languages_do_not_overwrite(self):
        (self.source / 'XXX-000-C.chs.srt').write_text('简', encoding='utf-8')
        (self.source / 'XXX-000-C.cht.srt').write_text('繁', encoding='utf-8')
        archive.store(self.video, self.folder, 'XXX-000-C')
        self.assertEqual((self.folder / 'XXX-000-C.chs.srt').read_text('utf-8'), '简')
        self.assertEqual((self.folder / 'XXX-000-C.cht.srt').read_text('utf-8'), '繁')

    def test_renamed_along_with_video(self):
        video = self.source / 'example.com@XXX-000.mp4'
        video.write_bytes(b'video')
        (self.source / 'example.com@XXX-000.ass').write_text('sub', encoding='utf-8')
        archive.store(video, self.folder, 'XXX-000')
        self.assertTrue((self.folder / 'XXX-000.ass').is_file())

    def test_unrelated_files_left_alone(self):
        (self.source / '别的片子.srt').write_text('sub', encoding='utf-8')
        (self.source / 'XXX-000-C.torrent').write_bytes(b'x')
        archive.store(self.video, self.folder, 'XXX-000-C')
        self.assertTrue((self.source / '别的片子.srt').is_file())
        self.assertTrue((self.source / 'XXX-000-C.torrent').is_file())


class WriteNfo(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_written_as_utf8(self):
        path = archive.write_nfo('<movie>演员甲</movie>', self.folder, 'XXX-000-C')
        self.assertEqual(path.name, 'XXX-000-C.nfo')
        self.assertEqual(path.read_text('utf-8'), '<movie>演员甲</movie>')

    def test_paired_with_video_name(self):
        """nfo 与影片本体同名，分卷各有各的一份"""
        for stem in ('XXX-000-CD1', 'XXX-000-CD2'):
            archive.write_nfo('<movie/>', self.folder, stem)
        self.assertTrue((self.folder / 'XXX-000-CD1.nfo').is_file())
        self.assertTrue((self.folder / 'XXX-000-CD2.nfo').is_file())


if __name__ == '__main__':
    unittest.main()
