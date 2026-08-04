# -*- coding: utf-8 -*-
"""
跨平台单键读取：菜单与确认提示支持 Esc 返回上一步。

Windows 走 msvcrt；POSIX 走 termios raw 模式，一次读一个字节。
方向键等转义序列以 \x1b 开头，用非阻塞读取吃掉整个序列，
避免把「按方向键」误判成 Esc。
"""
import os
import sys


def read_key():
    """
    读取单个按键。返回：
      'esc' / 'enter' / 'backspace' / 'eof' / '?'（无法识别）
      普通字符（'0'-'9'、'y'、'n' 等）
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
            return 'esc'
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
