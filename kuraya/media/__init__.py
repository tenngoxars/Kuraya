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

# 视频扩展名唯一来源在 kuraya/formats.py（叶子模块，避免界面层为取
# 常量而拖入整个引擎）
from ..formats import VIDEO_EXTS


def _fmt_size(path):
    """文件大小人类可读（GB/MB），读不到返回 ?"""
    try:
        size = path.stat().st_size
    except OSError:
        return '?'
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.2f} TB'


def _confirm_replace(old_path, new_path):
    """
    洗版确认：显示新旧文件大小，方向键选择替换/跳过，回车确认。

    用户明确说「不要自动」，非交互场景（管道/定时任务）无法确认，
    宁可报错让用户手动处理，也不能悄悄替换文件。
    """
    # 延迟导入：引擎冷启动要快，console/keys/i18n 只在这个回调真正被
    # 调用（交互洗版）时才加载
    from .. import console
    from ..console import C
    from ..i18n import tr
    from ..keys import read_key
    if console.QUIET or not console.interactive():
        return False
    labels = (tr('替换'), tr('跳过'))
    selected = 0

    def render():
        parts = [
            f'{C.GOLD}▸{C.RESET} {C.BOLD}{label}{C.RESET}'
            if i == selected else f'{C.GREY}·{C.RESET}  {label}{C.RESET}'
            for i, label in enumerate(labels)
        ]
        print(f'\r  {"   ".join(parts)}\x1b[K', end='', flush=True)

    print()
    print(f'  {C.GOLD}◈{C.RESET} {tr("发现旧版本 {name}", name=old_path.name)}')
    print(f'    {C.GREY}{tr("旧文件")}{C.RESET}  {_fmt_size(old_path)}')
    print(f'    {C.GREY}{tr("新文件")}{C.RESET}  {_fmt_size(new_path)}')
    print(f'  {C.GREY}{tr("用新文件替换（旧文件移入废纸篓）？")}{C.RESET}')
    render()
    while True:
        key = read_key()
        if key in ('left', 'right'):
            selected = 1 - selected
            render()
        elif key == 'enter':
            print()
            return selected == 0
        elif key in ('esc', 'eof'):
            print()
            return False


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
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS
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
    # 洗版确认：目标已存在同版本文件时询问是否替换（非交互自动拒绝）
    archive.store(video, folder, file_id.stem(), confirm=_confirm_replace)

    yield Stored(path=folder, elapsed=time.time() - started)
