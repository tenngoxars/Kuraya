# -*- coding: utf-8 -*-
"""
跨平台单键读取：菜单与确认提示支持 Esc 返回上一步。

Windows 走 msvcrt；POSIX 走 termios raw 模式，一次读一个字节。
方向键等转义序列以 \x1b 开头，用非阻塞读取吃掉整个序列，
避免把「按方向键」误判成 Esc。
"""
import os
import re
import sys

if os.name != 'nt':
    # POSIX 终端控制模块。模块顶部加载：query_cursor 需要在写出
    # 查询序列前立即进入 raw 模式，函数内 import 的耗时会让终端
    # 应答在 ECHO 开启时到达并被回显到屏幕（^[[18;1R 之类）
    import select
    import termios
    import tty
    import time

# VT 鼠标报告：1003（all motion）让终端把移动与点击都以 SGR 序列
# （\x1b[<b;x;yM）发到输入流——移动事件（btn 32-35）用于悬停高亮，
# 按下事件用于点击执行。仅现代终端支持（Windows Terminal / iTerm2 /
# xterm 等）；旧 conhost 忽略，点击无效但方向键照常。
MOUSE_ENABLE = '\x1b[?1003h\x1b[?1006h'
MOUSE_DISABLE = '\x1b[?1003l\x1b[?1006l'

_mouse_depth = 0  # 菜单嵌套时引用计数，最外层退出才真正关闭
_win_stdin_mode = None  # Windows 原始 stdin 控制台模式，退出时恢复


def _win_stdin_vt(on):
    """
    Windows 切换 stdin 的 VT 输入模式。

    默认控制台 stdin 是 LINE+ECHO 模式，方向键/鼠标报告/CPR 应答的
    \\x1b 序列进不来且会被回显（屏幕上出现 ^[[18;1R 之类）；切到
    PROCESSED+VT_INPUT 后以原始序列到达。退出时恢复原模式，
    避免影响 input() 等行输入（如 updater 的更新确认）。
    """
    global _win_stdin_mode
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return
        if on:
            if _win_stdin_mode is None:
                _win_stdin_mode = mode.value
            k.SetConsoleMode(h, 0x201)  # PROCESSED_INPUT | VT_INPUT
        else:
            k.SetConsoleMode(h, _win_stdin_mode or 3)
            _win_stdin_mode = None
    except Exception:
        pass


def terminal_mouse_status():
    """
    终端对鼠标报告的支持状态：
      'ok'                —— 应用启用序列即可生效
      'warp-needs-toggle' —— Warp 需用户手动开启 Mouse Reporting（默认关）
      'unsupported'       —— 系统 Terminal.app 不支持鼠标报告
    """
    prog = os.environ.get('TERM_PROGRAM', '')
    if prog == 'WarpTerminal':
        return 'warp-needs-toggle'
    if prog == 'Apple_Terminal':
        return 'unsupported'
    return 'ok'


def enable_mouse():
    """启用鼠标报告，让点击菜单项变成输入事件。非 TTY 静默跳过"""
    global _mouse_depth
    if not os.isatty(sys.stdin.fileno()):
        return
    _mouse_depth += 1
    if _mouse_depth == 1:
        if os.name == 'nt':
            _win_stdin_vt(True)
        sys.stdout.write(MOUSE_ENABLE)
        sys.stdout.flush()


def disable_mouse():
    """与 enable_mouse 配对，全部退出后恢复文本选择等终端默认行为"""
    global _mouse_depth
    if _mouse_depth > 0:
        _mouse_depth -= 1
    if _mouse_depth == 0:
        if os.name == 'nt':
            _win_stdin_vt(False)
        try:
            sys.stdout.write(MOUSE_DISABLE)
            sys.stdout.flush()
        except OSError:
            pass


def query_cursor():
    """查询光标位置，返回 (行, 列)。非 TTY 或终端无响应时返回 None"""
    if not os.isatty(sys.stdin.fileno()):
        return None
    if os.name == 'nt':
        return _query_cursor_win()
    return _query_cursor_posix()


def _query_cursor_posix():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        # 先进入 raw 再写查询：若先写 6n，终端应答可能抢在
        # setraw 之前到达，在 ECHO 开启时被回显到屏幕
        tty.setraw(fd)
        sys.stdout.write('\x1b[6n')
        sys.stdout.flush()
        buf = b''
        deadline = time.monotonic() + 1  # 终端不应答时兜底，避免挂死
        while time.monotonic() < deadline:
            if not select.select([fd], [], [], 0.1)[0]:
                continue
            ch = os.read(fd, 1)
            if not ch:
                return None
            buf += ch
            if ch == b'R':
                break
        else:
            return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return _parse_cpr(buf)


def _query_cursor_win():
    import msvcrt
    sys.stdout.write('\x1b[6n')
    sys.stdout.flush()
    buf = b''
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if not msvcrt.kbhit():
            continue
        ch = msvcrt.getch()
        if ch == b'\x03':
            raise KeyboardInterrupt
        buf += ch
        if ch == b'R':
            break
    else:
        return None
    return _parse_cpr(buf)


def _parse_cpr(buf):
    """CPR 应答 \x1b[行;列R → (行, 列)"""
    m = re.match(rb'\x1b\[(\d+);(\d+)R', buf)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _parse_mouse(seq):
    """
    SGR 鼠标序列 [<b;x;yM：
      btn 32-35（移动/拖动）→ ('hover', 列, 行)
      btn 0-1（左/中键按下）→ ('click', 列, 行)
      btn 2（右键按下）、3-5（释放）、64-67（滚轮）、
      修饰键组合（128+）→ None（忽略）
    """
    m = re.match(rb'\[<(\d+);(\d+);(\d+)[Mm]', seq)
    if not m:
        return None
    btn, col, row = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 32 <= btn <= 35:
        return ('hover', col, row)
    if btn in (0, 1):
        return ('click', col, row)
    return None


def read_key():
    """
    读取单个按键。返回：
      'esc' / 'enter' / 'backspace' / 'eof' / '?'（无法识别）
      普通字符（'0'-'9'、'y'、'n' 等）
      鼠标（启用鼠标报告后）：('click', 列, 行) 按下 / ('hover', 列, 行) 移动
    Ctrl+C 抛 KeyboardInterrupt。
    """
    if os.name == 'nt':
        return _read_key_win()
    return _read_key_posix()


def _read_key_win():
    import msvcrt
    while True:
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):      # 功能键前缀，第二字节才是键名
            fn = msvcrt.getch()
            return {b'H': 'up', b'P': 'down', b'M': 'right',
                    b'K': 'left'}.get(fn, '?')
        if ch == b'\x1b':
            seq = b''
            while msvcrt.kbhit():
                seq += msvcrt.getch()
            if not seq:
                return 'esc'
            if seq.startswith(b'[<'):
                return _parse_mouse(seq) or '?'
            return {b'[A': 'up', b'[B': 'down', b'[C': 'right',
                    b'[D': 'left'}.get(seq, '?')
        if ch in (b'\r', b'\n'):
            return 'enter'
        if ch == b'\x03':
            raise KeyboardInterrupt
        if ch == b'\x08':
            return 'backspace'
        try:
            return ch.decode('utf-8')
        except UnicodeDecodeError:
            return '?'


def _read_key_posix():
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        # 管道/脚本输入：进不了 raw 模式，直接读一个字符
        ch = sys.stdin.read(1)
        if not ch:
            return 'eof'
        if ch == '\x1b':
            return 'esc'
        if ch in ('\r', '\n'):
            return 'enter'
        if ch == '\x03':
            raise KeyboardInterrupt
        return ch

    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1)
        rest = b''
        if ch == b'\x1b':
            # 后续字节必须在 raw 模式下读完：提前恢复会把 [B 等字节回显到屏幕
            while select.select([fd], [], [], 0.06)[0]:
                rest += os.read(fd, 16)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    if not ch:
        return 'eof'
    if ch == b'\x1b':
        if not rest:
            return 'esc'
        if rest.startswith(b'[<'):
            return _parse_mouse(rest) or '?'
        return {b'[A': 'up', b'[B': 'down', b'[C': 'right',
                b'[D': 'left'}.get(rest, '?')
    if ch in (b'\r', b'\n'):
        return 'enter'
    if ch == b'\x03':
        raise KeyboardInterrupt
    if ch == b'\x7f':
        return 'backspace'
    try:
        return ch.decode('utf-8')
    except UnicodeDecodeError:
        return '?'
