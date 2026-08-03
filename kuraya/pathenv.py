# -*- coding: utf-8 -*-
"""
把程序目录登记到用户级 PATH，使其可在任何目录直接调用。

只改 HKEY_CURRENT_USER\\Environment，不需要管理员权限，也不影响其他用户。
不使用 setx：它有 1024 字符上限，PATH 较长时会被静默截断。
"""
import os
import sys

VAR = 'Path'
KEY = 'Environment'


def program_dir():
    """需要加入 PATH 的目录。打包后是 exe 所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read():
    """返回 (原始值, 注册表类型)。未设置过则返回空值"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            return winreg.QueryValueEx(k, VAR)
    except FileNotFoundError:
        return '', winreg.REG_EXPAND_SZ
    except OSError:
        return '', winreg.REG_EXPAND_SZ


def _write(value, kind):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, VAR, 0, kind, value)
    _broadcast()


def _broadcast():
    """通知系统环境变量已变，新开的窗口才能读到"""
    try:
        import ctypes
        HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment',
            SMTO_ABORTIFHUNG, 3000, ctypes.byref(ctypes.c_ulong()))
    except Exception:
        pass


def _entries(raw):
    return [p for p in raw.split(os.pathsep) if p.strip()]


def is_installed():
    """程序目录是否已在用户 PATH 中"""
    if os.name != 'nt':
        return False
    target = os.path.normcase(program_dir().rstrip('\\'))
    raw, _ = _read()
    return any(os.path.normcase(p.rstrip('\\')) == target for p in _entries(raw))


def install():
    """加入用户 PATH。返回 (是否成功, 说明)"""
    if os.name != 'nt':
        return False, '仅 Windows 支持自动登记'
    if is_installed():
        return True, '已在 PATH 中'
    try:
        raw, kind = _read()
        parts = _entries(raw)
        parts.append(program_dir())
        _write(os.pathsep.join(parts), kind)
        return True, ''
    except OSError as exc:
        return False, str(exc)


def uninstall():
    """从用户 PATH 中移除。返回 (是否成功, 说明)"""
    if os.name != 'nt':
        return False, '仅 Windows 支持'
    try:
        raw, kind = _read()
        target = os.path.normcase(program_dir().rstrip('\\'))
        parts = [p for p in _entries(raw)
                 if os.path.normcase(p.rstrip('\\')) != target]
        _write(os.pathsep.join(parts), kind)
        return True, ''
    except OSError as exc:
        return False, str(exc)
