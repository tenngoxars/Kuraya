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


# 站点在头像墙上给的是显示名，比全名短一截（见 media/javbus.py 的 _actors）。
# 截出来的名字都落在 12-15 字节，也就是 4-5 个中日文字符。
# 下限一样要卡：不卡的话，「葵」这种真实的一字名会被并进「葵つかさ」，
# 两位不同的演员就此混成一个目录。ASCII 名一字节一字符，从来没被截过，另行排除。
_CLIPPED_BYTES = range(12, 16)


def prepare(movie: Movie, library: Path) -> Path:
    """建好这部影片的归档目录并返回，已存在则直接用"""
    actor = Path(library) / movie.folder_actor
    _merge_clipped(actor)
    folder = actor / movie.number
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArchiveFailed(f'无法建立目录 {folder}：{exc}') from exc
    return folder


def _merge_clipped(actor: Path) -> None:
    """
    把半截名目录并进全名目录。

    取值路径修好之前，演员名取的是站点截短的显示名，那时入库的影片留在
    半截名目录里；此后同一位演员的新片会建全名目录，收藏就此劈成两半。
    建目录前先并过来，不必让用户自己发现、自己搬。

    只认截断的确切形状：旧目录名是新名字的严格前缀，长度落在显示名被截断后的
    区间内，且不是纯 ASCII。合法的五字名也可能落进这个形状（「小島みなみ」是
    「小島みなみ（旧名）」的前缀），但那是同一个人加了艺名记法，本就该合。

    只做加法：番号目录整个搬，两边都有的留在原地不动，空了才删旧目录。
    判错了文件也还在，用户自己搬得回去。出错一律忽略 —— 合并失败顶多是
    维持现状，不该让一部本来能入库的影片失败。
    """
    if not actor.parent.is_dir():
        return
    try:
        siblings = list(actor.parent.iterdir())
    except OSError:
        return

    for old in siblings:
        if old.name == actor.name or not actor.name.startswith(old.name):
            continue
        if old.name.isascii() or not old.is_dir():
            continue
        if len(old.name.encode('utf-8')) not in _CLIPPED_BYTES:
            continue
        try:
            if not actor.exists():
                old.rename(actor)
                continue
            for item in old.iterdir():
                if not (actor / item.name).exists():
                    item.rename(actor / item.name)
            old.rmdir()                      # 还剩东西就留着，rmdir 自己会拒绝
        except OSError:
            pass


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
