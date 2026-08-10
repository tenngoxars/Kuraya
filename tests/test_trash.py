# -*- coding: utf-8 -*-
"""片库删除的路径边界与系统废纸篓适配测试。"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kuraya import trash


class MovieDir(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.library = Path(self.tmp.name) / 'library'
        self.movie = self.library / '演员甲' / 'ABC-001'
        self.movie.mkdir(parents=True)
        (self.movie / 'ABC-001.nfo').write_text('<movie/>', encoding='utf-8')
        (self.movie / 'ABC-001.mp4').write_bytes(b'video')

    def test_accepts_a_real_movie_directory(self):
        self.assertEqual(trash.movie_dir(self.movie, self.library),
                         self.movie.resolve())

    def test_rejects_library_or_actor_directory(self):
        self.assertIsNone(trash.movie_dir(self.library, self.library))
        self.assertIsNone(trash.movie_dir(self.movie.parent, self.library))

    def test_rejects_path_outside_library(self):
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (outside / 'ABC-001.nfo').write_text('<movie/>', encoding='utf-8')
        (outside / 'ABC-001.mp4').write_bytes(b'video')
        self.assertIsNone(trash.movie_dir(outside, self.library))

    def test_requires_nfo_and_video(self):
        nfo_only = self.library / '演员甲' / 'NFO-001'
        nfo_only.mkdir(parents=True)
        (nfo_only / 'NFO-001.nfo').write_text('<movie/>', encoding='utf-8')
        self.assertIsNone(trash.movie_dir(nfo_only, self.library))


class MoviePath(unittest.TestCase):
    """形态校验不要求目录存在：删除请求幂等时目标可能已被移走。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.library = Path(self.tmp.name) / 'library'
        self.library.mkdir()

    def test_accepts_two_level_absolute_path(self):
        target = self.library / '演员甲' / 'ABC-001'
        self.assertEqual(trash.movie_path(str(target), self.library),
                         target.resolve())

    def test_accepts_missing_directory(self):
        """目录已不在（删除成功但重建失败）仍是合法删除对象"""
        missing = self.library / '演员甲' / 'ABC-001'
        self.assertEqual(trash.movie_path(str(missing), self.library),
                         missing.resolve())

    def test_rejects_wrong_depth(self):
        self.assertIsNone(trash.movie_path(str(self.library), self.library))
        self.assertIsNone(
            trash.movie_path(str(self.library / '演员甲'), self.library))
        self.assertIsNone(trash.movie_path(
            str(self.library / '演员甲' / 'ABC-001' / 'deep'), self.library))

    def test_rejects_relative_or_outside_path(self):
        self.assertIsNone(trash.movie_path('演员甲/ABC-001', self.library))
        outside = self.tmp.name + '/outside/演员甲/ABC-001'
        self.assertIsNone(trash.movie_path(outside, self.library))

    def test_rejects_unset_library(self):
        self.assertIsNone(trash.movie_path('/a/b', ''))
        self.assertIsNone(trash.movie_path('', str(self.library)))


class TrashAdapters(unittest.TestCase):

    def test_fallback_keeps_source_when_trash_record_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'ABC-001'
            target.mkdir()
            (target / 'video.mp4').write_bytes(b'video')
            xdg = root / 'xdg'
            with mock.patch.object(trash.sys, 'platform', 'linux'), \
                    mock.patch.object(trash.shutil, 'which', return_value=None), \
                    mock.patch.dict(os.environ, {'XDG_DATA_HOME': str(xdg)}), \
                    mock.patch.object(Path, 'open', side_effect=OSError('disk full')), \
                    mock.patch.object(trash.shutil, 'move') as move:
                self.assertFalse(trash.move_to_trash(target))
            move.assert_not_called()
            self.assertTrue(target.exists())
            info = xdg / 'Trash' / 'info'
            self.assertFalse(info.exists() and any(info.iterdir()))

    def test_fallback_removes_record_when_move_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'ABC-001'
            target.mkdir()
            (target / 'video.mp4').write_bytes(b'video')
            xdg = root / 'xdg'
            with mock.patch.object(trash.sys, 'platform', 'linux'), \
                    mock.patch.object(trash.shutil, 'which', return_value=None), \
                    mock.patch.dict(os.environ, {'XDG_DATA_HOME': str(xdg)}), \
                    mock.patch.object(trash.shutil, 'move', side_effect=OSError('busy')):
                self.assertFalse(trash.move_to_trash(target))
            self.assertTrue(target.exists())
            info = xdg / 'Trash' / 'info'
            self.assertFalse(info.exists() and any(info.iterdir()))

    def test_fallback_handles_shutil_error_without_moving_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'ABC-001'
            target.mkdir()
            xdg = root / 'xdg'
            with mock.patch.object(trash.sys, 'platform', 'linux'), \
                    mock.patch.object(trash.shutil, 'which', return_value=None), \
                    mock.patch.dict(os.environ, {'XDG_DATA_HOME': str(xdg)}), \
                    mock.patch.object(trash.shutil, 'move',
                                      side_effect=trash.shutil.Error('busy')):
                self.assertFalse(trash.move_to_trash(target))
            self.assertTrue(target.exists())

    def test_linux_fallback_uses_freedesktop_trash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'ABC-001'
            target.mkdir()
            (target / 'video.mp4').write_bytes(b'video')
            xdg = root / 'xdg'
            with mock.patch.object(trash.sys, 'platform', 'linux'), \
                    mock.patch.object(trash.shutil, 'which', return_value=None), \
                    mock.patch.dict(os.environ, {'XDG_DATA_HOME': str(xdg)}):
                self.assertTrue(trash.move_to_trash(target))
            self.assertFalse(target.exists())
            files = list((xdg / 'Trash' / 'files').iterdir())
            self.assertEqual(len(files), 1)
            record = xdg / 'Trash' / 'info' / f'{files[0].name}.trashinfo'
            self.assertTrue(record.is_file())
            self.assertIn('Path=', record.read_text(encoding='utf-8'))

    def test_dispatches_to_macos_adapter(self):
        with mock.patch.object(trash.sys, 'platform', 'darwin'), \
                mock.patch.object(trash, '_macos_trash', return_value=True) as move:
            self.assertTrue(trash.move_to_trash('/tmp/movie'))
        move.assert_called_once_with(Path('/tmp/movie'))

    def test_macos_path_is_passed_as_an_argument_not_script_text(self):
        path = Path('/tmp/movie "quoted"')
        with mock.patch.object(trash.subprocess, 'run') as run:
            self.assertTrue(trash._macos_trash(path))
        args = run.call_args.args[0]
        self.assertIn(str(path), args)
        self.assertNotIn(str(path), args[2])

    def test_dispatches_to_windows_adapter(self):
        path = Path('/tmp/movie')
        with mock.patch.object(trash.os, 'name', 'nt'), \
                mock.patch.object(trash, 'Path', return_value=path), \
                mock.patch.object(trash, '_windows_trash', return_value=True) as move:
            self.assertTrue(trash.move_to_trash('/tmp/movie'))
        move.assert_called_once_with(path)


if __name__ == '__main__':
    unittest.main()
