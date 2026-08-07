# -*- coding: utf-8 -*-
"""
影片入库启动器：串起刮削、清理源目录、刷新网页三步，统一美化控制台输出。
用法: python -m kuraya.launcher [all|refresh]
"""
import os
import re
import subprocess
import sys
import time

from . import console, media, protocol, settings
from .console import (C, W, brand, branch, box, clip, dw, info,
                      movie_detail, say, section, spin)
from .i18n import tr
from .media.model import (CoverReady, FailReason, Failed, Fetched, Found,
                          PosterReady, Probing, Stage, Started, Stored)


class ConfigError(Exception):
    """配置缺失或无效"""


def child_argv(kind, *args):
    """
    构造子进程命令。打包成 EXE 后 sys.executable 是 EXE 自身，
    不能再拿它执行 .py，改为让同一个程序按内部子命令重新入口。
    """
    flag = f'--internal-{kind}'
    if getattr(sys, 'frozen', False):
        return [sys.executable, flag, *args]
    return [sys.executable, '-W', 'ignore', '-m', 'kuraya', flag, *args]


CHILD_FAILED = '\x00child-exit'      # 内部标记，用于把子进程异常退出传给调用方


def run(kind, *args):
    """
    执行子进程，逐行返回输出（统一用 UTF-8，避免控制台编码干扰）。
    子进程非正常退出时，末尾追加一条标记，避免失败被当成「结果为空」。
    """
    env = dict(os.environ, PYTHONIOENCODING='utf-8',
               PYTHONUTF8='1', PYTHONUNBUFFERED='1')
    proc = subprocess.Popen(
        child_argv(kind, *args),
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding='utf-8', errors='replace',
    )
    for raw in proc.stdout:
        yield raw.rstrip('\n')
    proc.wait()
    if proc.returncode:
        yield f'{CHILD_FAILED} {proc.returncode}'


# ---------- 各步骤 ----------
def probing_text(stage, fallback):
    """阶段文案按当前语言即时翻译（模块级 tr 会冻结在导入时刻，
    切换语言后不生效）"""
    return {Stage.COVER: tr("探测封面源"),
            Stage.CROP: tr("裁剪竖版海报"),
            Stage.ARCHIVE: tr("写入元数据并移动文件")}.get(stage, fallback)


def fail_text(reason):
    """失败原因文案按当前语言即时翻译"""
    return {FailReason.NO_NUMBER: (tr("番号"), tr("未能识别番号")),
            FailReason.NOT_FOUND: (tr("查询"), tr("未找到元数据")),
            FailReason.NETWORK: (tr("网络"), tr("连不上数据源")),
            FailReason.COVER_FAILED: (tr("封面"), tr("未能取得封面")),
            FailReason.ARCHIVE_FAILED: (tr("入库"), tr("未能入库")),
            }[reason]


def do_scrape(library, source, opts=None):
    opts = opts or {}
    stats = {'found': 0, 'done': 0, 'failed': 0}
    current = None
    detail = ''
    resolved = True

    panel = console.ScrapePanel()
    panel.start()
    pending_count = 0      # 已开始处理的影片数（面板统计行用）

    def close_pending():
        """引擎保证每部都以 Stored 或 Failed 收尾，这里只是兜底"""
        nonlocal resolved
        if current and not resolved:
            stats['failed'] += 1
            if panel.active:
                panel.set(4, console.branch_text('└', tr('失败'),
                                                 tr('未能入库'), color=C.RED))
                panel.set(5, console.panel_stat(stats, pending_count))
            else:
                branch('└', tr('失败'), tr('未能入库'), color=C.RED)
        resolved = True

    config = media.Settings(
        library=library,
        source=source,
        sleep=settings.load()['sleep'],
        limit=opts.get('limit') or 0,
        dry_run=opts.get('dry_run', False),
    )

    if not panel.active:
        spin.set(tr("正在扫描待处理影片"))

    try:
        for event in media.process(config):
            if console.VERBOSE:
                say(f'{C.FAINT}    {event}{C.RESET}')

            match event:
                case Found(count=count):
                    stats['found'] = count
                    if count == 0:
                        panel.clear()        # 无影片：清掉面板区域不留空白
                        spin.hide()
                        info(tr("没有待处理的影片"))

                case Started(number=number, index=index):
                    close_pending()
                    current, detail, resolved = number, '', config.dry_run
                    pending_count = index
                    tag = f'[{index}/{stats["found"] or "?"}]'
                    # 先截番号再拼 head：clip 不认 ANSI，截整行会把 [i/n] 吞掉
                    number = clip(number, W - dw(tag) - 8)
                    gap = W - dw(f'▸ {number}') - dw(tag) - 1
                    head = (f'   {C.GOLD}▸{C.RESET} {C.BOLD}{number}{C.RESET}'
                            f'{" " * max(1, gap)}{C.GREY}{tag}{C.RESET}')
                    if panel.active:
                        panel.set_many({0: head, 1: '', 2: '', 3: '', 4: '',
                                        5: console.panel_stat(stats, index)})
                    else:
                        say()
                        say(head)
                        spin.set(tr("查询 {number} 的元数据", number=number))

                case Fetched(movie=movie):
                    # 元数据这一行排在「入库」之前，先攒着
                    detail = movie_detail(movie)

                case Probing(stage=stage):
                    if not panel.active:
                        spin.set(probing_text(stage,
                                              tr("查询 {number} 的元数据",
                                                 number=current)))

                case CoverReady():
                    if panel.active:
                        panel.set(1, console.branch_text('├', tr("封面"),
                                                         tr("已下载"),
                                                         color=C.GREY))
                    else:
                        branch('├', tr("封面"), tr("已下载"), color=C.GREY)

                case PosterReady():
                    if panel.active:
                        panel.set(2, console.branch_text('├', tr("裁剪"),
                                                         tr("已生成竖版海报"),
                                                         color=C.GREY))
                    else:
                        branch('├', tr("裁剪"), tr("已生成竖版海报"),
                               color=C.GREY)

                case Stored(path=path, elapsed=elapsed):
                    stats['done'] += 1
                    if panel.active:
                        if detail:
                            panel.set(3, console.branch_text('├', tr("元数据"),
                                                             detail))
                        where = '\\'.join(str(path).replace('/', '\\').split('\\')[-2:])
                        panel.set(4, console.branch_text('└', tr("入库"), where,
                                                         right=f'{elapsed:.1f}s'))
                        panel.set(5, console.panel_stat(stats, pending_count))
                    else:
                        if detail:
                            branch('├', tr("元数据"), detail)
                        where = '\\'.join(str(path).replace('/', '\\').split('\\')[-2:])
                        branch('└', tr("入库"), where, right=f'{elapsed:.1f}s')
                    resolved = True
                    if not panel.active:
                        spin.set(tr("准备处理下一部"))

                case Failed(reason=reason):
                    label, text = fail_text(reason)
                    stats['failed'] += 1
                    if panel.active:
                        panel.set(4, console.branch_text('└', label, text,
                                                         color=C.RED))
                        panel.set(5, console.panel_stat(stats, pending_count))
                    else:
                        branch('└', label, text, color=C.RED)
                    resolved = True
                    if not panel.active:
                        spin.set(tr("准备处理下一部"))
    finally:
        close_pending()
        spin.hide()
        panel.end()
    return stats


def do_clean(source, library):
    removed = kept = linked = 0
    failed = False
    spin.set(tr("检查源目录"))
    for text in run('cleanup', str(source), str(library)):
        if console.VERBOSE:
            say(f'{C.FAINT}    {text}{C.RESET}')
        if text.startswith(CHILD_FAILED):
            failed = True
        elif text.startswith('[cleanup:rm]'):
            info(tr("移除 {name}", name=text[len('[cleanup:rm]'):].strip()))
            removed += 1
        elif text.startswith('[cleanup:linked]'):
            info(tr("{name} 此前已入库，移除重复文件",
                    name=text[len('[cleanup:linked]'):].strip()))
            linked += 1
        elif text.startswith('[cleanup:kept]'):
            prefix = len('[cleanup:kept]')
            say(f'    {C.RED}!{C.RESET} {C.GREY}{text[prefix:].strip()}{C.RESET} '
                f'{C.FAINT}{tr("未能刮削，已留在待整理目录")}{C.RESET}')
            kept += 1
    spin.hide()
    if failed:
        say(f'    {C.RED}✕ {tr("清理源目录失败，可用 -v 查看详细输出")}{C.RESET}')
    elif removed == 0 and kept == 0 and linked == 0:
        info(tr("源目录已是干净的"))
    return removed


def do_refresh(library):
    total = None
    failed = False
    spin.set(tr("扫描影片库并生成页面"))
    for text in run('gallery', str(library)):
        if console.VERBOSE:
            say(f'{C.FAINT}    {text}{C.RESET}')
        if text.startswith(CHILD_FAILED):
            failed = True
            continue
        m = re.search(r'gallery-collected=(\d+)', text)
        if m:
            total = int(m.group(1))
    spin.hide()

    # 拿不到收录数说明子进程没正常跑完，不能当成「库里就是 0 部」
    if failed or total is None:
        say(f'    {C.RED}✕ {tr("重建页面失败，片库页面未更新")}{C.RESET}')
        say(f'    {C.GREY}{tr("可用 -v 查看详细输出")}{C.RESET}')
        return 0
    say(f'    {C.GREEN}✓{C.RESET} {C.GREY}{tr("页面已重新生成，收录")}{C.RESET} '
        f'{C.BOLD}{total}{C.RESET} {C.GREY}{tr("部")}{C.RESET}')
    return total


# ---------- 命令 ----------
def cmd_scrape(library, source, opts=None):
    """只刮削，不重建页面。返回统计结果"""
    section('①', tr("刮削影片"))
    stats = do_scrape(library, source, opts)
    say()
    section('②', tr("清理源目录"))
    do_clean(source, library)
    source.mkdir(parents=True, exist_ok=True)
    return stats


def open_library(library):
    """用默认浏览器打开片库页面。页面未生成或打开失败时给出提示"""
    index = os.path.join(str(library), 'index.html')
    if not os.path.isfile(index):
        say(f'    {C.RED}✕ {tr("页面尚未生成，请先执行「重建页面」")}{C.RESET}')
        return
    if protocol.open_default(index):
        say(f'    {C.GREEN}✓{C.RESET} {tr("已在浏览器中打开")}')
    else:
        open_err = tr('打开失败：{path}', path=index)
        say(f'    {C.RED}✕ {open_err}{C.RESET}')


def offer_open_library(library, opts=None):
    """刮削完成后选择是否直接打开片库；quiet / 计划任务模式跳过。
    返回是否出现过选择器——调用方用它决定是否还需要「按回车继续」"""
    if console.QUIET or (opts or {}).get('yes'):
        return False
    from .keys import read_key
    choices = [(tr('打开片库'), tr('在浏览器中查看')),
               (tr('稍后再说'), '')]
    selected = 0
    height = len(choices) + 1  # 选项行 + 提示行

    def render():
        for i, (label, desc) in enumerate(choices):
            mark, style = ((C.GOLD + '▸', C.BOLD) if i == selected
                           else (C.GREY + '·', ''))
            print(f'  {mark}{C.RESET}  {style}{label}{C.RESET}'
                  f'{" " * max(2, 14 - dw(label))}{C.FAINT}{desc}{C.RESET}'
                  f'\x1b[K')
        print(f'  {C.FAINT}{tr("↑↓ 选择 · 回车 确认 · Esc 跳过")}'
              f'{C.RESET}\x1b[K')

    say()
    # 留在主屏渲染：上方是刮削结果卡片，选择器只画底部两行
    render()
    while True:
        key = read_key()
        if key == 'up':
            selected = (selected - 1) % len(choices)
        elif key == 'down':
            selected = (selected + 1) % len(choices)
        elif key in ('enter', ''):
            if selected == 0:
                open_library(library)
            return True
        elif key in ('esc', 'eof', 'backspace', '?'):
            return True
        else:
            continue
        sys.stdout.write(f'\x1b[{height}A')
        render()


def cmd_rebuild(library):
    """只重建片库页面。返回收录总数"""
    brand()
    say()
    section('①', tr("重新扫描并生成页面"))
    total = do_refresh(library)
    say()
    box([(tr("库内共 {total} 部", total=total), C.GREEN)], C.GREEN)
    return total


def cmd_all(library, source, opts=None):
    """完整流程：刮削 → 清理 → 重建页面"""
    t0 = time.time()
    brand()
    say()

    stats = cmd_scrape(library, source, opts)
    say()

    section('③', tr("重建片库页面"))
    total = do_refresh(library)
    say()

    bits = [tr("新入库 {done} 部", done=stats['done'])]
    if stats['failed']:
        bits.append(tr("失败 {failed} 部", failed=stats['failed']))
    bits.append(tr("库内共 {total} 部", total=total))
    bits.append(tr("耗时 {elapsed:.0f}s", elapsed=time.time() - t0))
    tone = C.RED if stats['failed'] else C.GREEN
    box([(' · '.join(bits), tone)], tone)
    offered = offer_open_library(library, opts)
    return stats, offered
