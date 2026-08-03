# -*- coding: utf-8 -*-
"""
封面处理：下载 → 存为 fanart → 裁出 poster → 复制出 thumb。

分成 download 与 build 两步，中间要给界面报一次进度。
竖版海报靠固定比例裁剪，不做人脸识别：支持范围内的封面版式固定，左背板右海报。
"""
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from . import http
from .model import Assets, Movie

POSTER_RATIO = (2, 3)

RATIO = 2.12

KNOWN_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif')
DEFAULT_EXTENSION = '.jpg'

_QUALITY = 95


class CoverFailed(Exception):
    """封面拿不到或不可用。整部影片按失败处理，不静默跳过"""


@dataclass(frozen=True)
class Cover:
    """已落盘的横版封面"""
    path: Path
    stem: str
    extension: str

    @property
    def size_kb(self) -> int:
        return self.path.stat().st_size // 1024


def download(movie: Movie, dest: Path, stem: str,
             headers: dict | None = None) -> Cover:
    """取回封面原图，直接存成 fanart。dest 需已存在"""
    if not movie.cover_url:
        raise CoverFailed(f'{movie.number} 没有封面地址')

    try:
        data = http.get_bytes(movie.cover_url, headers=headers)
    except http.Unavailable as exc:
        raise CoverFailed(f'{movie.number} 封面下载失败：{exc}') from exc

    if not data:
        raise CoverFailed(f'{movie.number} 封面为空')

    extension = _extension(movie.cover_url)
    path = dest / f'{stem}-fanart{extension}'
    path.write_bytes(data)
    return Cover(path=path, stem=stem, extension=extension)


def build(cover: Cover) -> Assets:
    """由已下载的 fanart 派生出 poster 与 thumb，返回三个文件名"""
    poster = cover.path.with_name(f'{cover.stem}-poster{cover.extension}')
    thumb = cover.path.with_name(f'{cover.stem}-thumb{cover.extension}')

    _crop_poster(cover.path, poster)
    shutil.copyfile(cover.path, thumb)

    return Assets(poster=poster.name, fanart=cover.path.name, thumb=thumb.name)


def _crop_poster(source: Path, target: Path) -> None:
    try:
        with Image.open(source) as image:
            image.load()
            box = poster_box(image.width, image.height)
            cropped = image if box is None else image.crop(box)
            _save(cropped, target)
    except CoverFailed:
        raise
    except (OSError, ValueError) as exc:
        raise CoverFailed(f'封面无法处理：{exc}') from exc


def poster_box(width: int, height: int) -> tuple[int, int, int, int] | None:
    """
    算出海报在封面里的位置，已经是 2:3 则返回 None。

    比 2:3 宽是常规情形，取最右边一块；比 2:3 窄多半本来就是竖图，
    从顶部往下取，因为下方通常是文字条。
    """
    if width <= 0 or height <= 0:
        raise CoverFailed(f'封面尺寸无效：{width}x{height}')

    wide, tall = POSTER_RATIO
    left_side = width * tall
    right_side = height * wide

    if left_side > right_side:
        left = int(width - height / tall * RATIO)
        return max(0, left), 0, width, height
    if left_side < right_side:
        bottom = int(width * tall / wide)
        return 0, 0, width, min(height, bottom)
    return None


def _save(image: Image.Image, target: Path) -> None:
    if target.suffix.lower() in ('.jpg', '.jpeg') and image.mode not in ('RGB', 'L'):
        image = image.convert('RGB')
    image.save(target, quality=_QUALITY)


def _extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in KNOWN_EXTENSIONS else DEFAULT_EXTENSION
