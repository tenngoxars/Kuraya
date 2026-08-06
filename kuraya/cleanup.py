# -*- coding: utf-8 -*-
"""
清理待整理目录：没有视频的文件夹删除，已入库（同一 inode）的文件夹移除，
其余保留待重试。删除与保留以 [cleanup:rm]/[cleanup:linked]/[cleanup:kept]
标记输出，供父进程解析。

用法: python cleanup.py <待整理目录> [影片库目录]
"""
import os
import shutil
import sys

# 多语言：裸脚本运行时包不在搜索路径，tr 回退原文
try:
    from kuraya.i18n import tr
except ImportError:
    def tr(text, **kw):
        return text.format(**kw) if kw else text

try:
    from kuraya.settings import VIDEO_EXTS
except ImportError:
    # 裸脚本运行（python cleanup.py <目录>）时包不在搜索路径
    VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.wmv', '.ts', '.mov',
                  '.m4v', '.rmvb', '.iso', '.mpg', '.mpeg', '.flv')  # 与 formats.py 同值


def library_inodes(source, library):
    """影片库中所有视频的 inode，用于判断源文件是否已入库"""
    if not library or not os.path.isdir(library):
        return set()
    found = set()
    src_real = os.path.realpath(source)
    for root, dirs, files in os.walk(library):
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


def clean(source, library):
    """清理待整理目录，返回 (删除, 移除已入库, 保留)。逐项以标记输出"""
    source = os.path.abspath(source)
    in_library = library_inodes(source, library)
    removed = linked = kept = 0

    for name in sorted(os.listdir(source)):
        folder = os.path.join(source, name)
        if not os.path.isdir(folder):
            continue

        videos = videos_in(folder)

        if not videos:
            shutil.rmtree(folder)
            removed += 1
            print(f'[cleanup:rm] {name}')
            continue

        # 视频还在：看它是不是已经在影片库里（同一 inode 即同一份文件）
        try:
            already = all(os.stat(v).st_ino in in_library for v in videos)
        except OSError:
            already = False

        if already and in_library:
            shutil.rmtree(folder)
            linked += 1
            print(f'[cleanup:linked] {name}')
        else:
            kept += 1
            print(f'[cleanup:kept] {name}')

    print(tr('\n清理完成：删除 {removed} 个，移除已入库的 {linked} 个，'
              '保留待重试 {kept} 个。',
              removed=removed, linked=linked, kept=kept))
    return removed, linked, kept


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 1:
        print(tr('用法: python cleanup.py <待整理目录> [影片库目录]'))
        return 2
    source = os.path.abspath(args[0])
    library = os.path.abspath(args[1]) if len(args) > 1 else ''

    if not os.path.isdir(source):
        print(tr('源目录不存在: {source}', source=source))
        return 1

    clean(source, library)
    return 0


if __name__ == '__main__':
    sys.exit(main())
