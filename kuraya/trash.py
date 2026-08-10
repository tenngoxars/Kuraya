# -*- coding: utf-8 -*-
"""影片目录校验与跨平台移入系统废纸篓。"""
import ctypes
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .formats import VIDEO_EXTS


def movie_path(path, library):
    """校验路径形态（影片库下正好两级的绝对路径），不要求目录仍存在。

    删除请求幂等时目标目录可能已被移走（上次删除成功但页面重建失败），
    此时仍算合法删除对象，只是不再检查 NFO/视频是否齐全。
    """
    if not path or not library:
        return None
    try:
        # 目标可能已不存在（幂等删除），resolve 不要求存在，只展开
        # 已存在部分的符号链接，保证与 base 同基准后词法可比
        raw = Path(path).expanduser().resolve()
        base = Path(library).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not raw.is_absolute() or not base.is_dir():
        return None
    try:
        parts = raw.relative_to(base).parts
    except ValueError:
        return None
    if len(parts) != 2:
        return None
    return base.joinpath(*parts)


def movie_dir(path, library):
    """返回仍在片库中的合法影片目录；已不存在或形态不合法时返回 None。"""
    target = movie_path(path, library)
    if target is None or not target.is_dir() or not _looks_like_movie(target):
        return None
    return target


def _looks_like_movie(path):
    """影片卡片必然同时有视频和以目录名开头的 NFO。"""
    try:
        names = os.listdir(path)
    except OSError:
        return False
    prefix = path.name.upper()
    has_nfo = any(name.lower().endswith('.nfo')
                  and name.upper().startswith(prefix) for name in names)
    has_video = any(Path(name).suffix.lower() in VIDEO_EXTS for name in names)
    return has_nfo and has_video


def move_to_trash(path):
    """把目录移入系统废纸篓，成功返回 True，失败返回 False。"""
    path = Path(path)
    if os.name == 'nt':
        return _windows_trash(path)
    if sys.platform == 'darwin':
        return _macos_trash(path)
    return _linux_trash(path)


def _windows_trash(path):
    """调用 Shell API 的 FO_DELETE + FOF_ALLOWUNDO，支持恢复。"""
    try:
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ('hwnd', wintypes.HWND),
                ('wFunc', wintypes.UINT),
                ('pFrom', wintypes.LPCWSTR),
                ('pTo', wintypes.LPCWSTR),
                ('fFlags', wintypes.UINT),
                ('fAnyOperationsAborted', wintypes.BOOL),
                ('hNameMappings', ctypes.c_void_p),
                ('lpszProgressTitle', wintypes.LPCWSTR),
            ]

        flags = 0x0004 | 0x0010 | 0x0040 | 0x0400
        operation = SHFILEOPSTRUCTW(
            None, 0x0003, str(path) + '\0\0', None, flags,
            False, None, None)
        result = ctypes.windll.shell32.SHFileOperationW(
            ctypes.byref(operation))
        return result == 0 and not operation.fAnyOperationsAborted
    except (AttributeError, OSError, TypeError):
        return False


def _macos_trash(path):
    """让 Finder 处理废纸篓，避免手写 ~/.Trash 的权限与卷问题。"""
    script = ('on run argv\n'
              '  tell application "Finder" to delete POSIX file (item 1 of argv)\n'
              'end run')
    try:
        subprocess.run(
            ['osascript', '-e', script, '--', str(path)],
            check=True, capture_output=True, timeout=30)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _discard_trash_path(path):
    """清理回退搬运留下的明确临时目标，失败时保留原错误结果。"""
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except (OSError, shutil.Error):
        pass


def _write_trash_record(record, metadata):
    """先完整写临时记录，再原子放入 info，避免出现半份元数据。"""
    temp_record = record.with_name(f'.{record.name}.{uuid.uuid4().hex}.tmp')
    try:
        with temp_record.open('x', encoding='utf-8') as stream:
            stream.write(metadata)
        os.replace(temp_record, record)
    except (OSError, shutil.Error):
        _discard_trash_path(temp_record)
        _discard_trash_path(record)
        return False
    return True


def _linux_trash(path):
    """优先用 gio；没有 gio 时按 Freedesktop Trash 规范写入用户废纸篓。"""
    gio = shutil.which('gio')
    if gio:
        try:
            subprocess.run([gio, 'trash', str(path)],
                           check=True, capture_output=True, timeout=30)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    root = Path(os.environ.get(
        'XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))) / 'Trash'
    files = root / 'files'
    info = root / 'info'
    try:
        files.mkdir(parents=True, exist_ok=True)
        info.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    name = path.name
    for _ in range(20):
        suffix = '' if _ == 0 else f'.{uuid.uuid4().hex}'
        dest = files / f'{name}{suffix}'
        record = info / f'{dest.name}.trashinfo'
        if dest.exists() or record.exists():
            continue
        metadata = ('[Trash Info]\n'
                    f'Path={quote(str(path), safe="/")}\n'
                    f'DeletionDate={datetime.now():%Y-%m-%dT%H:%M:%S}\n')

        # 先把完整记录落盘，记录写不成时源目录仍留在原处。
        if not _write_trash_record(record, metadata):
            return False
        try:
            shutil.move(str(path), str(dest))
        except (OSError, shutil.Error):
            if path.exists():
                _discard_trash_path(dest)
                _discard_trash_path(record)
                return False
            if dest.exists():
                # move 可能已完成但在返回前抛错；记录和目录均完整时可视为成功。
                return True
            _discard_trash_path(record)
            return False
        return True
    return False
