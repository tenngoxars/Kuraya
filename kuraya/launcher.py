# -*- coding: utf-8 -*-
"""
影片入库启动器：串起刮削、清理源目录、刷新网页三步，统一美化控制台输出。
用法: python -m kuraya.launcher [all|refresh]
"""
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata

from . import media, settings
from .i18n import tr
from .media.model import (CoverReady, FailReason, Failed, Fetched, Found,
                          PosterReady, Probing, Stage, Started, Stored)


class ConfigError(Exception):
    """配置缺失或无效"""


W = 60  # 版面宽度

# 由命令行参数设置：精简输出 / 输出刮削程序原始日志
QUIET = False
VERBOSE = False


class C:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    GOLD = '\033[38;5;179m'
    GREEN = '\033[38;5;114m'
    RED = '\033[38;5;167m'
    BLUE = '\033[38;5;110m'
    GREY = '\033[38;5;245m'
    FAINT = '\033[38;5;240m'


def enable_ansi():
    """老版本 cmd 需要手动开启 ANSI 转义支持"""
    if os.name != 'nt':
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
    except Exception:
        pass


# ---------- 排版 ----------
def dw(text):
    """中日文字符占两列，按实际显示宽度计算"""
    return sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1 for ch in text)


def center(text, width):
    space = max(0, width - dw(text))
    left = space // 2
    return ' ' * left + text + ' ' * (space - left)


def pad(text, width):
    return text + ' ' * max(0, width - dw(text))


def clip(text, width):
    """按显示宽度截断，超出加省略号"""
    if dw(text) <= width:
        return text
    out = ''
    for ch in text:
        if dw(out) + dw(ch) > width - 1:
            break
        out += ch
    return out + '…'


# ---------- 等待动画 ----------
class Spinner:
    """在当前行滚动显示工作状态，有正式输出时先擦除本行"""
    FRAMES = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'

    def __init__(self):
        self.lock = threading.RLock()
        self.text = ''
        self.active = False
        self.t0 = 0.0
        self.thread = None

    def _loop(self):
        i = 0
        while self.active:
            with self.lock:
                if self.active and self.text:
                    frame = self.FRAMES[i % len(self.FRAMES)]
                    sys.stdout.write(
                        f'\r     {C.FAINT}{frame}{C.RESET} {C.GREY}{self.text}{C.RESET}'
                        f' {C.FAINT}{time.time() - self.t0:.0f}s{C.RESET}\033[K')
                    sys.stdout.flush()
            i += 1
            time.sleep(0.1)

    def set(self, text):
        """切换提示文字并重新计时"""
        if QUIET:
            return
        with self.lock:
            self.text = text
            self.t0 = time.time()
        if not self.active:
            self.active = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def hide(self):
        if QUIET:
            return          # 精简模式没有动画行，不应写入清行指令
        with self.lock:
            self.text = ''
            sys.stdout.write('\r\033[K')
            sys.stdout.flush()

    def stop(self):
        self.active = False
        if self.thread:
            self.thread.join(timeout=0.5)
        self.hide()


spin = Spinner()


def say(text=''):
    """输出正式内容。有动画行在跑时先擦掉它，否则直接输出。
    菜单等静态绘制不带 \\r 前缀——无谓的回车会被终端（尤其 Warp）
    当成输出块边界，方向键导航会被终端拦截"""
    if QUIET:
        return
    with spin.lock:
        if spin.active and spin.text:
            sys.stdout.write('\r\033[K')
        print(text)


# ---------- 输出组件 ----------
def rule(char='─'):
    say(f'{C.FAINT}  {char * W}{C.RESET}')


def box(lines, color=None):
    """圆角边框卡片"""
    color = color or C.GOLD
    say(f'{color}  ╭{"─" * W}╮{C.RESET}')
    for text, style in lines:
        say(f'{color}  │{C.RESET}{style}{center(text, W)}{C.RESET}{color}│{C.RESET}')
    say(f'{color}  ╰{"─" * W}╯{C.RESET}')


def brand():
    """程序标识。◈ 取自家纹的圆框套菱格，与图标同一意象"""
    from . import NAME, KANJI, __version__
    spaced = ' '.join(NAME)                    # 拉开字距，做出徽标感
    left = f'◈  {spaced}   {KANJI}'
    version = f'v{__version__}'
    gap = W - dw(left) - dw(version)
    say(f'  {C.GOLD}◈{C.RESET}  {C.BOLD}{spaced}{C.RESET}'
        f'   {C.GOLD}{KANJI}{C.RESET}'
        f'{" " * max(1, gap)}{C.FAINT}{version}{C.RESET}')
    rule()


def section(num, name):
    say(f'  {C.BLUE}{num}{C.RESET} {C.BOLD}{name}{C.RESET}')
    rule()


def info(text):
    say(f'    {C.GREY}{text}{C.RESET}')


BRANCH_W = W - 12  # 分步状态行中正文可用的显示宽度


def branch(connector, label, detail, right='', color=None):
    """影片处理过程中的分步状态。detail 为纯文本，right 右对齐显示"""
    body = clip(detail, BRANCH_W - (dw(right) + 2 if right else 0))
    space = ' ' * max(1, BRANCH_W - dw(body) - dw(right)) if right else ''
    tail = f'{space}{C.FAINT}{right}{C.RESET}' if right else ''
    say(f'     {C.FAINT}{connector}{C.RESET} {C.GREY}{pad(label, 7)}{C.RESET}'
        f'{color or ""}{body}{C.RESET if color else ""}{tail}')


def movie_detail(movie):
    """元数据行：演员 · 厂商 · 发行日期"""
    bits = []
    if movie.actors:
        bits.append('、'.join(movie.actors[:3]) + ('…' if len(movie.actors) > 3 else ''))
    if movie.studio:
        bits.append(movie.studio)
    if movie.release:
        bits.append(movie.release)
    return ' · '.join(bits)


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
PROBING_TEXT = {
    Stage.COVER: tr("探测封面源"),
    Stage.CROP: tr("裁剪竖版海报"),
    Stage.ARCHIVE: tr("写入元数据并移动文件"),
}

FAIL_TEXT = {
    FailReason.NO_NUMBER: (tr("番号"), tr("未能识别番号")),
    FailReason.NOT_FOUND: (tr("查询"), tr("未找到元数据")),
    FailReason.NETWORK: (tr("网络"), tr("连不上数据源")),
    FailReason.COVER_FAILED: (tr("封面"), tr("未能取得封面")),
    FailReason.ARCHIVE_FAILED: (tr("入库"), tr("未能入库")),
}


def do_scrape(library, source, opts=None):
    opts = opts or {}
    stats = {'found': 0, 'done': 0, 'failed': 0}
    current = None
    detail = ''
    resolved = True

    def close_pending():
        """引擎保证每部都以 Stored 或 Failed 收尾，这里只是兜底"""
        nonlocal resolved
        if current and not resolved:
            branch('└', '失败', '未能入库', color=C.RED)
            stats['failed'] += 1
        resolved = True

    config = media.Settings(
        library=library,
        source=source,
        sleep=settings.load()['sleep'],
        limit=opts.get('limit') or 0,
        dry_run=opts.get('dry_run', False),
    )

    spin.set(tr("正在扫描待处理影片"))

    for event in media.process(config):
        if VERBOSE:
            say(f'{C.FAINT}    {event}{C.RESET}')

        match event:
            case Found(count=count):
                stats['found'] = count
                if count == 0:
                    spin.hide()
                    info(tr("没有待处理的影片"))

            case Started(number=number, index=index):
                close_pending()
                say()
                current, detail, resolved = number, '', config.dry_run
                tag = f'[{index}/{stats["found"] or "?"}]'
                gap = W - dw(f'▸ {number}') - dw(tag) - 1
                say(f'   {C.GOLD}▸{C.RESET} {C.BOLD}{number}{C.RESET}'
                    f'{" " * max(1, gap)}{C.GREY}{tag}{C.RESET}')
                spin.set(tr("查询 {number} 的元数据", number=number))

            case Fetched(movie=movie):
                # 元数据这一行排在「入库」之前，先攒着
                detail = movie_detail(movie)

            case Probing(stage=stage):
                spin.set(PROBING_TEXT.get(stage, tr("查询 {number} 的元数据",
                                                    number=current)))

            case CoverReady():
                branch('├', tr("封面"), tr("已下载"), color=C.GREY)

            case PosterReady():
                branch('├', tr("裁剪"), tr("已生成竖版海报"), color=C.GREY)

            case Stored(path=path, elapsed=elapsed):
                if detail:
                    branch('├', tr("元数据"), detail)
                where = '\\'.join(str(path).replace('/', '\\').split('\\')[-2:])
                branch('└', tr("入库"), where, right=f'{elapsed:.1f}s')
                stats['done'] += 1
                resolved = True
                spin.set(tr("准备处理下一部"))

            case Failed(reason=reason):
                label, text = FAIL_TEXT[reason]
                branch('└', label, text, color=C.RED)
                stats['failed'] += 1
                resolved = True
                spin.set(tr("准备处理下一部"))

    close_pending()
    spin.hide()
    return stats


def do_clean(source, library):
    removed = kept = linked = 0
    failed = False
    spin.set(tr("检查源目录"))
    for text in run('cleanup', str(source), str(library)):
        if VERBOSE:
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
        if VERBOSE:
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
    try:
        if os.name == 'nt':
            os.startfile(index)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', index])
        else:
            subprocess.Popen(['xdg-open', index])
        say(f'    {C.GREEN}✓{C.RESET} {tr("已在浏览器中打开")}')
    except OSError as exc:
        open_err = tr('打开失败：{exc}', exc=exc)
        say(f'    {C.RED}✕ {open_err}{C.RESET}')


def offer_open_library(library, opts=None):
    """刮削完成后选择是否直接打开片库；quiet / 计划任务模式跳过。
    返回是否出现过选择器——调用方用它决定是否还需要「按回车继续」"""
    if QUIET or (opts or {}).get('yes'):
        return False
    from . import keys
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
        print(f'  {C.FAINT}{tr("↑↓ 选择 · 回车 确认 · Esc 跳过")}{C.RESET}'
              f'\x1b[K')

    say()
    render()
    while True:
        key = keys.read_key()
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
