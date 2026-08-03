# -*- coding: utf-8 -*-
"""
刮削后清理源目录。

三种情况分开处理：
  已入库   视频与影片库中的文件是同一份（硬链接），源目录只是多余的一份链接，删除
  未成功   视频仍是独立文件，说明没被处理，保留待重试
  已处理   视频已被移走，只剩种子等残留，删除

用法: python cleanup.py <待整理目录> [影片库目录]
"""
import os
import shutil
import sys

VIDEO_EXTS = ('.mp4', '.avi', '.mkv', '.wmv', '.ts', '.mov', '.m4v', '.rmvb', '.iso', '.mpg')

if len(sys.argv) < 2:
    raise SystemExit('用法: python cleanup.py <待整理目录> [影片库目录]')
SOURCE = os.path.abspath(sys.argv[1])
LIBRARY = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else ''

if not os.path.isdir(SOURCE):
    raise SystemExit(f'源目录不存在: {SOURCE}')


def library_inodes():
    """影片库中所有视频的 inode，用于判断源文件是否已入库"""
    if not LIBRARY or not os.path.isdir(LIBRARY):
        return set()
    found = set()
    src_real = os.path.realpath(SOURCE)
    for root, dirs, files in os.walk(LIBRARY):
        if os.path.realpath(root).startswith(src_real):
            dirs[:] = []          # 不把待整理目录本身算进去
            continue
        for f in files:
            if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                try:
                    found.add(os.stat(os.path.join(root, f)).st_ino)
                except OSError:
                    pass
    return found


def videos_in(folder):
    out = []
    for root, _, files in os.walk(folder):
        for f in files:
            if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                out.append(os.path.join(root, f))
    return out


in_library = library_inodes()
removed = linked = kept = 0

for name in sorted(os.listdir(SOURCE)):
    folder = os.path.join(SOURCE, name)
    if not os.path.isdir(folder):
        continue

    videos = videos_in(folder)

    if not videos:
        shutil.rmtree(folder)
        removed += 1
        print(f'[清理] {name}')
        continue

    # 视频还在：看它是不是已经在影片库里（同一 inode 即同一份文件）
    try:
        already = all(os.stat(v).st_ino in in_library for v in videos)
    except OSError:
        already = False

    if already and in_library:
        shutil.rmtree(folder)
        linked += 1
        print(f'[已入库] {name}')
    else:
        kept += 1
        print(f'[保留] {name}')

print(f'\n清理完成：删除 {removed} 个，移除已入库的 {linked} 个，保留待重试 {kept} 个。')
