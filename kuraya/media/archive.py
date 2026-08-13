# -*- coding: utf-8 -*-
"""
落盘：建目录、写 nfo、把影片与字幕搬进影片库。布局写死为「演员名/番号」。

出错一律抛异常，本部计失败，整批继续。
"""
import shutil
from pathlib import Path

from ..trash import move_to_trash
from .model import Movie

SUBTITLE_EXTENSIONS = ('.srt', '.ass', '.ssa', '.sub', '.idx', '.vtt', '.smi', '.sup')


class ArchiveFailed(Exception):
    """目录建不了、目标已存在、文件移不动"""


def prepare(movie: Movie, library: Path) -> Path:
    """建好这部影片的归档目录并返回，已存在则直接用"""
    folder = Path(library) / movie.folder_actor / movie.number
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArchiveFailed(f'无法建立目录 {folder}：{exc}') from exc
    return folder


def write_nfo(text: str, folder: Path, stem: str) -> Path:
    """写入元数据文件，与影片本体同名，因此分卷各有各的一份"""
    path = folder / f'{stem}.nfo'
    try:
        path.write_text(text, encoding='utf-8')
    except OSError as exc:
        raise ArchiveFailed(f'无法写入 {path.name}：{exc}') from exc
    return path


def store(video: Path, folder: Path, stem: str, confirm=None) -> Path:
    """
    把影片搬进归档目录并改名，同名字幕一并搬走。

    放在最后一步：前面任何一步失败，影片都还在待整理目录里，重跑即可。
    confirm 为洗版确认回调：目标已存在时调用（参数为旧文件与待入库
    新文件路径），返回 True 则旧文件移入系统废纸篓（可恢复）再放新版；
    返回 False 或未提供回调都报错，旧文件不动——洗版必须用户确认，
    不自动删。
    """
    video = Path(video)
    target = folder / f'{stem}{video.suffix.lower()}'

    if target.exists():
        if confirm is None or not confirm(target, video):
            raise ArchiveFailed(f'{target.name} 已存在于 {folder.name}')
        if not move_to_trash(target):
            raise ArchiveFailed(f'旧文件 {target.name} 移入废纸篓失败，未替换')

    subtitles = list(_subtitles(video))
    _move(video, target)
    for subtitle in subtitles:
        try:
            _move(subtitle, folder / f'{stem}{_subtitle_suffix(video, subtitle)}')
        except ArchiveFailed:
            pass
    return target


def _subtitles(video: Path):
    """
    同名字幕，也收 `影片名.chs.srt` 这种带语言标记的写法 ——
    漏下的会随源目录被随后的清理步骤一并删掉。
    """
    stem = video.stem.lower()
    try:
        siblings = list(video.parent.iterdir())
    except OSError:
        return

    for path in siblings:
        if not path.is_file() or path.suffix.lower() not in SUBTITLE_EXTENSIONS:
            continue
        name = path.stem.lower()
        if name == stem or name.startswith(f'{stem}.'):
            yield path


def _subtitle_suffix(video: Path, subtitle: Path) -> str:
    """保留影片名之后的部分，多语言字幕才不会互相覆盖"""
    extra = subtitle.stem[len(video.stem):]
    return f'{extra}{subtitle.suffix.lower()}'


def _move(source: Path, target: Path) -> None:
    try:
        shutil.move(str(source), str(target))
    except OSError as exc:
        raise ArchiveFailed(f'无法移动 {source.name}：{exc}') from exc
