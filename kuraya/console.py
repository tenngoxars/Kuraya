# -*- coding: utf-8 -*-
"""
终端输出原语：颜色、排版、动画、正式输出。与业务流程无关，
菜单 / 启动器 / 引导 / 更新提示共用，避免业务模块互相延迟 import。
"""
import os
import sys
import threading
import time
import unicodedata

from . import NAME, KANJI, __version__
from .i18n import tr

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


def ensure_utf8():
    """stdout/stderr 统一 UTF-8 输出（Windows 控制台默认 cp1252/gbk 会乱码）"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def interactive():
    """
    屏幕前有人吗：键盘读得到、输出没被重定向。

    定时任务、管道、agent 调用都读不到按键，此时凡是等人输入的分支
    都必须跳过——读到 EOF 就静默返回，看起来像做完了，其实一件事没做。
    """
    for stream in (sys.stdin, sys.stdout):
        try:
            if not stream.isatty():
                return False
        except (AttributeError, ValueError):
            # 打包成窗口程序时 stdin 可能是 None，或流已关闭
            return False
    return True


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


class ScrapePanel:
    """
    刮削进度面板：固定 6 行区域原地重绘，不随影片增多而滚动。

    行结构（行数恒定 → 不会占满屏幕）：
      0  ▸ 番号  [i/n]
      1  ├ 封面  已下载
      2  ├ 裁剪  已生成竖版海报
      3  ├ 元数据  演员 · 厂商 · 发行日期
      4  └ 入库  …  3.2s
      5  已处理 i/n · 成功 x · 失败 y

    只在交互终端启用（TTY + 非 QUIET + 非 VERBOSE）；否则调用方
    回退为逐行输出，面板不做任何事。
    """

    ROWS = 6

    def __init__(self):
        self.active = False
        self.top = 0          # 面板首行（1-based），CPR 查得后不再变
        self.lines = [''] * self.ROWS

    def start(self):
        """进入面板模式：先输出占位行再查光标定位首行。失败则保持 inactive"""
        if QUIET or VERBOSE or not sys.stdout.isatty():
            return
        from .keys import query_cursor
        # 先写占位行再查光标：写完 6 行后光标落在面板底部，
        # 首行 = 当前行 - ROWS（滚动/不滚动两种情况都对）
        sys.stdout.write('\n' * self.ROWS)
        sys.stdout.flush()
        pos = query_cursor()
        if not pos:
            return            # 终端不应答 CPR，回退逐行输出
        self.top = pos[0] - self.ROWS
        self.active = True
        self.render()

    def set(self, index, text):
        """更新面板第 index 行（0-based），原地重绘"""
        if not self.active:
            return
        self.lines[index] = text
        self.render()

    def set_many(self, updates):
        """一次更新多行（index: text），只重绘一次。
        逐行 set() 在慢终端会闪（每次全屏重绘）"""
        if not self.active:
            return
        for index, text in updates.items():
            self.lines[index] = text
        self.render()

    def render(self):
        out = [f'\x1b[{self.top};1H']
        for line in self.lines:
            out.append(f'\x1b[2K{line}\n')
        out.append(f'\x1b[{self.top + self.ROWS};1H')
        sys.stdout.write(''.join(out))
        sys.stdout.flush()

    def end(self):
        """收尾：光标移到面板底部，面板内容保留在屏幕上。
        无内容场景（Found=0）用 clear() 清空区域"""
        if not self.active:
            return
        sys.stdout.write(f'\x1b[{self.top + self.ROWS};1H')
        sys.stdout.flush()
        self.active = False

    def clear(self):
        """清空面板区域（Found=0 等场景不留 6 行空白）"""
        if not self.active:
            return
        out = [f'\x1b[{self.top};1H']
        for _ in range(self.ROWS):
            out.append('\x1b[2K\n')
        out.append(f'\x1b[{self.top};1H')
        sys.stdout.write(''.join(out))
        sys.stdout.flush()
        self.active = False


def panel_stat(stats, index):
    """面板统计行：已处理 i/n · 成功 x · 失败 y"""
    total = stats['found'] or '?'
    bits = [tr('已处理 {index}/{total}', index=index, total=total),
            tr('成功 {done}', done=stats['done']),
            tr('失败 {failed}', failed=stats['failed'])]
    return f'   {C.GREY}{" · ".join(bits)}{C.RESET}'


# ---------- 输出组件 ----------
def rule():
    say(f'{C.FAINT}  {"─" * W}{C.RESET}')


def box(lines, color=None):
    """圆角边框卡片"""
    color = color or C.GOLD
    say(f'{color}  ╭{"─" * W}╮{C.RESET}')
    for text, style in lines:
        say(f'{color}  │{C.RESET}{style}{center(text, W)}{C.RESET}{color}│{C.RESET}')
    say(f'{color}  ╰{"─" * W}╯{C.RESET}')


def brand():
    """程序标识。◈ 取自家纹的圆框套菱格，与图标同一意象"""
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
    say(branch_text(connector, label, detail, right=right, color=color))


def branch_text(connector, label, detail, right='', color=None):
    """与 branch() 相同的排版，返回文本而非输出，供面板行使用"""
    body = clip(detail, BRANCH_W - (dw(right) + 2 if right else 0))
    space = ' ' * max(1, BRANCH_W - dw(body) - dw(right)) if right else ''
    tail = f'{space}{C.FAINT}{right}{C.RESET}' if right else ''
    return (f'     {C.FAINT}{connector}{C.RESET} {C.GREY}{pad(label, 7)}{C.RESET}'
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
