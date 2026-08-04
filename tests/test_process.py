# -*- coding: utf-8 -*-
"""
编排的测试：事件顺序、失败归类、磁盘上的结果。

只挡住网络那一层（javbus.fetch 与 http.get_bytes），其余全是真的 ——
裁剪、写 nfo、移文件都在临时目录里真跑一遍，这样测的才是整条流水线。

    python -m unittest discover tests
"""
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from kuraya import media
from kuraya.media.http import Unavailable
from kuraya.media.model import (CoverReady, FailReason, Failed, Fetched, Found,
                                Movie, Settings, Started, Stored)

MOVIE = Movie(
    number='XXX-000',
    title='标题',
    cover_url='https://example.invalid/cover.jpg',
    actors=('演员甲',),
    tags=('标签一',),
    release='2026-08-07',
    runtime='135',
    studio='示例制作商',
)


def cover_bytes(size=(800, 538)):
    buffer = io.BytesIO()
    Image.new('RGB', size, 'white').save(buffer, format='JPEG')
    return buffer.getvalue()


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.library = root / 'Library'
        self.source = self.library / '待整理'
        self.source.mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)

    def settings(self, **kwargs):
        kwargs.setdefault('sleep', 0)
        return Settings(library=self.library, source=self.source, **kwargs)

    def put(self, name, folder=None):
        """在待整理目录里放一个影片文件"""
        target = (folder or self.source) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'video')
        return target

    def run_engine(self, fetch=None, download=cover_bytes, **kwargs):
        fetch = fetch if fetch is not None else (lambda number: MOVIE)
        with mock.patch('kuraya.media.javbus.fetch', side_effect=fetch), \
             mock.patch('kuraya.media.http.get_bytes',
                        side_effect=lambda url, headers=None: download()):
            return list(media.process(self.settings(**kwargs)))

    def kinds(self, events):
        return [type(e).__name__ for e in events]


class Scan(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def touch(self, relative):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
        return path

    def test_recursive(self):
        """下载来的影片通常各自带一层目录"""
        self.touch('XXX-000/XXX-000.mp4')
        self.touch('YYYY-111.mkv')
        self.assertEqual(len(media.scan(self.source)), 2)

    def test_only_video_extensions(self):
        self.touch('XXX-000.mp4')
        self.touch('XXX-000.torrent')
        self.touch('XXX-000.txt')
        self.assertEqual([p.name for p in media.scan(self.source)], ['XXX-000.mp4'])

    def test_sorted_and_limited(self):
        for name in ('C.mp4', 'A.mp4', 'B.mp4'):
            self.touch(name)
        self.assertEqual([p.name for p in media.scan(self.source, limit=2)],
                         ['A.mp4', 'B.mp4'])

    def test_missing_source(self):
        self.assertEqual(media.scan(self.source / '不存在'), [])


class HappyPath(Base):

    def setUp(self):
        super().setUp()
        self.video = self.put('example.com@XXX-000-C.mp4')
        self.events = self.run_engine()
        self.folder = self.library / '演员甲' / 'XXX-000'

    def test_event_sequence(self):
        self.assertEqual(self.kinds(self.events),
                         ['Found', 'Started', 'Probing', 'Fetched', 'Probing',
                          'CoverReady', 'Probing', 'PosterReady', 'Probing',
                          'Stored'])

    def test_found_count(self):
        self.assertEqual(self.events[0], Found(count=1))

    def test_started_carries_number_and_index(self):
        self.assertEqual(self.events[1], Started(number='XXX-000', index=1))

    def test_fetched_carries_movie(self):
        fetched = next(e for e in self.events if isinstance(e, Fetched))
        self.assertEqual(fetched.movie.studio, '示例制作商')

    def test_cover_size_reported(self):
        ready = next(e for e in self.events if isinstance(e, CoverReady))
        self.assertGreater(ready.size_kb, 0)

    def test_stored_points_at_folder(self):
        stored = next(e for e in self.events if isinstance(e, Stored))
        self.assertEqual(stored.path, self.folder)
        self.assertGreaterEqual(stored.elapsed, 0)

    def test_files_on_disk(self):
        names = sorted(p.name for p in self.folder.iterdir())
        self.assertEqual(names, ['XXX-000-C-fanart.jpg', 'XXX-000-C-poster.jpg',
                                 'XXX-000-C-thumb.jpg', 'XXX-000-C.mp4',
                                 'XXX-000-C.nfo'])

    def test_source_file_moved(self):
        self.assertFalse(self.video.exists())

    def test_nfo_is_readable(self):
        import xml.etree.ElementTree as ET
        root = ET.parse(self.folder / 'XXX-000-C.nfo').getroot()
        self.assertEqual(root.findtext('num'), 'XXX-000')
        self.assertEqual(root.findtext('poster'), 'XXX-000-C-poster.jpg')


class Parts(Base):
    """分卷共用一套图，影片与 nfo 各自带 -CDn"""

    def test_two_parts(self):
        self.put('XXX-000-CD1.mp4')
        self.put('XXX-000-CD2.mp4')
        events = self.run_engine()
        self.assertEqual(sum(isinstance(e, Stored) for e in events), 2)

        folder = self.library / '演员甲' / 'XXX-000'
        names = sorted(p.name for p in folder.iterdir())
        self.assertEqual(names, ['XXX-000-CD1.mp4', 'XXX-000-CD1.nfo',
                                 'XXX-000-CD2.mp4', 'XXX-000-CD2.nfo',
                                 'XXX-000-fanart.jpg', 'XXX-000-poster.jpg',
                                 'XXX-000-thumb.jpg'])


class Failures(Base):

    def reason(self, events):
        failed = next(e for e in events if isinstance(e, Failed))
        return failed.reason

    def test_unrecognised_filename(self):
        video = self.put('新建文件夹.mp4')
        events = self.run_engine()
        self.assertEqual(self.reason(events), FailReason.NO_NUMBER)
        self.assertTrue(video.exists(), '认不出番号的文件原样留下')

    def test_not_found(self):
        video = self.put('SSSS-4567.mp4')
        events = self.run_engine(fetch=lambda number: None)
        self.assertEqual(self.reason(events), FailReason.NOT_FOUND)
        self.assertTrue(video.exists())

    def test_network_down(self):
        """网络不可用与查不到分开：前者重跑就好"""
        def boom(number):
            raise Unavailable('connection refused')
        video = self.put('XXX-000.mp4')
        events = self.run_engine(fetch=boom)
        self.assertEqual(self.reason(events), FailReason.NETWORK)
        self.assertTrue(video.exists())

    def test_cover_download_failed(self):
        def boom():
            raise Unavailable('403')
        video = self.put('XXX-000.mp4')
        events = self.run_engine(download=boom)
        self.assertEqual(self.reason(events), FailReason.COVER_FAILED)
        self.assertTrue(video.exists(), '封面失败时影片留在待整理目录')

    def test_cover_is_not_an_image(self):
        video = self.put('XXX-000.mp4')
        events = self.run_engine(download=lambda: b'<html>403</html>')
        self.assertEqual(self.reason(events), FailReason.COVER_FAILED)
        self.assertTrue(video.exists())

    def test_already_archived(self):
        folder = self.library / '演员甲' / 'XXX-000'
        folder.mkdir(parents=True)
        (folder / 'XXX-000.mp4').write_bytes(b'old')
        video = self.put('XXX-000.mp4')
        events = self.run_engine()
        self.assertEqual(self.reason(events), FailReason.ARCHIVE_FAILED)
        self.assertTrue(video.exists())
        self.assertEqual((folder / 'XXX-000.mp4').read_bytes(), b'old')

    def test_unexpected_error_is_contained(self):
        """没预料到的崩溃也只是本部失败，不能带走整批"""
        def boom(number):
            raise RuntimeError('意外')
        self.put('XXX-000.mp4')
        events = self.run_engine(fetch=boom)
        self.assertEqual(self.reason(events), FailReason.ARCHIVE_FAILED)


class BatchContinues(Base):

    def test_one_failure_does_not_stop_the_rest(self):
        self.put('新建文件夹.mp4')
        self.put('XXX-000.mp4')
        self.put('YYYY-111.mp4')

        events = self.run_engine()
        self.assertEqual(events[0], Found(count=3))
        self.assertEqual(sum(isinstance(e, Failed) for e in events), 1)
        self.assertEqual(sum(isinstance(e, Stored) for e in events), 2)

    def test_indices_cover_every_file(self):
        for name in ('XXX-000.mp4', 'YYYY-111.mp4', '新建文件夹.mp4'):
            self.put(name)
        events = self.run_engine()
        indices = [e.index for e in events if isinstance(e, Started)]
        self.assertEqual(indices, [1, 2, 3])


class DryRun(Base):

    def test_reports_without_touching_anything(self):
        video = self.put('XXX-000.mp4')
        events = self.run_engine(dry_run=True)
        self.assertEqual(self.kinds(events), ['Found', 'Started'])
        self.assertTrue(video.exists())
        self.assertEqual(list(self.library.iterdir()), [self.source])


class Limit(Base):

    def test_stops_after_n(self):
        for name in ('XXX-000.mp4', 'YYYY-111.mp4', 'UUUUU-555.mp4'):
            self.put(name)
        events = self.run_engine(limit=2)
        self.assertEqual(events[0], Found(count=2))
        self.assertEqual(sum(isinstance(e, Started) for e in events), 2)


class Empty(Base):

    def test_nothing_to_do(self):
        self.assertEqual(self.run_engine(), [Found(count=0)])


if __name__ == '__main__':
    unittest.main()
