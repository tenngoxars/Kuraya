# -*- coding: utf-8 -*-
"""
刮削引擎。对外只有一个入口：

    for event in media.process(settings):
        ...

其余模块都是它的实现细节，界面层不应直接导入。
界面 match 事件类型，不再正则匹配子进程的英文日志。
"""
import time
from pathlib import Path
from typing import Iterator

from . import archive, assets, javbus, naming, nfo
from .archive import ArchiveFailed
from .assets import CoverFailed
from .http import Unavailable
from .model import (CoverReady, Event, FailReason, Failed, Fetched, Found,
                    PosterReady, Probing, Settings, Stage, Started, Stored)

__all__ = ['process', 'scan', 'Settings']

VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.wmv', '.ts', '.mov',
                    '.m4v', '.rmvb', '.iso', '.mpg', '.mpeg', '.flv')


def process(settings: Settings) -> Iterator[Event]:
    """
    处理待整理目录里的全部影片，逐步产出事件。

    单部失败不中断整批，失败的影片原样留在待整理目录，重跑即可。
    """
    videos = scan(settings.source, settings.limit)
    yield Found(count=len(videos))

    for index, video in enumerate(videos, start=1):
        yield from _one(video, index, settings)

        if settings.sleep > 0 and index < len(videos) and not settings.dry_run:
            time.sleep(settings.sleep)


def scan(source: Path, limit: int = 0) -> list[Path]:
    """
    找出待处理的影片。递归，因为下载来的影片通常各自带一层目录。

    排序后再截取，`--limit` 每次跑的才是同一批。
    """
    source = Path(source)
    if not source.is_dir():
        return []

    found = sorted(
        path for path in source.rglob('*')
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )
    return found[:limit] if limit and limit > 0 else found


def _one(video: Path, index: int, settings: Settings) -> Iterator[Event]:
    """
    处理一部影片。所有失败在这里收口，向外只表现为一个 Failed 事件 ——
    包括没预料到的崩溃，否则调用方拿到的是个半路断掉的迭代器。
    """
    started = time.time()

    file_id = naming.parse(video.name)
    if file_id is None:
        yield Started(number=video.name, index=index)
        yield Failed(number=video.name, reason=FailReason.NO_NUMBER)
        return

    yield Started(number=file_id.number, index=index)
    if settings.dry_run:
        return

    try:
        yield from _scrape(video, file_id, settings, started)
    except Unavailable:
        yield Failed(number=file_id.number, reason=FailReason.NETWORK)
    except CoverFailed:
        yield Failed(number=file_id.number, reason=FailReason.COVER_FAILED)
    except ArchiveFailed:
        yield Failed(number=file_id.number, reason=FailReason.ARCHIVE_FAILED)
    except Exception:
        yield Failed(number=file_id.number, reason=FailReason.ARCHIVE_FAILED)


def _scrape(video, file_id, settings, started) -> Iterator[Event]:
    """
    一部影片的正常路径，异常一律往上抛由 _one 归类。

    影片本体最后才移动：前面任何一步出问题，它都还在待整理目录里。
    """
    yield Probing(stage=Stage.METADATA)
    movie = javbus.fetch(file_id.number)
    if movie is None:
        yield Failed(number=file_id.number, reason=FailReason.NOT_FOUND)
        return
    yield Fetched(movie=movie)

    folder = archive.prepare(movie, settings.library)

    yield Probing(stage=Stage.COVER)
    cover = assets.download(movie, folder, file_id.image_stem(),
                            headers=javbus.image_headers(movie.cover_url))
    yield CoverReady(size_kb=cover.size_kb)

    yield Probing(stage=Stage.CROP)
    built = assets.build(cover)
    yield PosterReady()

    yield Probing(stage=Stage.ARCHIVE)
    archive.write_nfo(nfo.render(movie, file_id.edition, built),
                      folder, file_id.stem())
    archive.store(video, folder, file_id.stem())

    yield Stored(path=folder, elapsed=time.time() - started)
