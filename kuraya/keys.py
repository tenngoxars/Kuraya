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

# VT 鼠标报告：启用后终端把点击以 SGR 序列（\x1b[<b;x;yM）发到输入流。
# 仅现代终端支持（Windows Terminal / iTerm2 / xterm 等）；旧 conhost 忽略，
# 点击无效但方向键照常。
MOUSE_ENABLE = '\x1b[?1000h\x1b[?1006h'
MOUSE_DISABLE = '\x1b[?1000l\x1b[?1006l'

_mouse_depth = 0  # 菜单嵌套时引用计数，最外层退出才真正关闭


def enable_mouse():
    """启用鼠标报告，让点击菜单项变成输入事件。非 TTY 静默跳过"""
    global _mouse_depth
    if not os.isatty(sys.stdin.fileno()):
        return
    _mouse_depth += 1
    if _mouse_depth == 1:
        sys.stdout.write(MOUSE_ENABLE)
        sys.stdout.flush()


def disable_mouse():
    """与 enable_mouse 配对，全部退出后恢复文本选择等终端默认行为"""
    global _mouse_depth
    if _mouse_depth > 0:
        _mouse_depth -= 1
    if _mouse_depth == 0:
        try:
            sys.stdout.write(MOUSE_DISABLE)
            sys.stdout.flush()
        except OSError:
            pass


def query_cursor():
    """查询光标位置，返回 (行, 列)。非 TTY 或终端无响应时返回 None"""
    if not os.isatty(sys.stdin.fileno()):
        return None
    sys.stdout.write('\x1b[6n')
    sys.stdout.flush()
    if os.name == 'nt':
        return _query_cursor_win()
    return _query_cursor_posix()


def _query_cursor_posix():
    import select
    import termios
    import tty
    import time
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf = b''
    try:
        tty.setraw(fd)
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
    import time
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
    """SGR 鼠标序列 [<b;x;yM/m → ('click', 列, 行)"""
    m = re.match(rb'\[<(\d+);(\d+);(\d+)[Mm]', seq)
    return ('click', int(m.group(2)), int(m.group(3))) if m else None


def read_key():
    """
    读取单个按键。返回：
      'esc' / 'enter' / 'backspace' / 'eof' / '?'（无法识别）
      普通字符（'0'-'9'、'y'、'n' 等）
      鼠标点击（启用鼠标报告后）：('click', 列, 行)
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

    import select
    import termios
    import tty
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
