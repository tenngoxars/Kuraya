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
import time  # Windows 分支 _query_cursor_win 也要用（超时兜底）

if os.name != 'nt':
    # POSIX 终端控制模块。模块顶部加载：query_cursor 需要在写出
    # 查询序列前立即进入 raw 模式，函数内 import 的耗时会让终端
    # 应答在 ECHO 开启时到达并被回显到屏幕（^[[18;1R 之类）
    import select
    import termios
    import tty

def _console_stdin_vt(on, saved=None):
    """Windows 切换 stdin 的 VT 输入模式（CPR 应答需要，LINE+ECHO 下
    应答进不来且会被回显成 ^[[18;1R 之类）。开启时返回切换前的原模式，
    关闭时恢复之；失败返回 None"""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return None
        if on:
            if saved is None:
                saved = mode.value
            k.SetConsoleMode(h, 0x201)  # PROCESSED_INPUT | VT_INPUT
        else:
            k.SetConsoleMode(h, saved or 3)
        return saved
    except Exception:
        return None


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
    # 默认 stdin 是 LINE+ECHO 模式，CPR 应答进不来且会被回显；
    # 查询期间临时切 VT 输入模式，读完恢复（避免影响 input() 等行输入）
    saved = _console_stdin_vt(True)
    try:
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
    finally:
        _console_stdin_vt(False, saved)
    return _parse_cpr(buf)


def _parse_cpr(buf):
    """CPR 应答 \x1b[行;列R → (行, 列)"""
    m = re.match(rb'\x1b\[(\d+);(\d+)R', buf)
    return (int(m.group(1)), int(m.group(2))) if m else None


def read_key():
    """
    读取单个按键。返回：
      'esc' / 'enter' / 'backspace' / 'eof' / '?'（无法识别）
      普通字符（'0'-'9'、'y'、'n' 等）、方向键 'up' / 'down'
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
