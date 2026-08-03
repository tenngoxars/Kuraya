# -*- coding: utf-8 -*-
"""
自定义 URL 协议 kuraya: 的注册与调用。

片库页面是静态 HTML，浏览器无法直接启动播放器，需借助自定义协议：
页面上的链接形如 kuraya:<百分号编码的绝对路径>，由本程序接管并唤起播放器。

注册写入 HKEY_CURRENT_USER，不需要管理员权限。
"""
import os
import sys
from urllib.parse import unquote

SCHEME = 'kuraya'


def handler_command():
    """协议处理命令。打包成 exe 后指向 exe 自身，否则指向解释器加模块"""
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}" --play "%1"'
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return f'"{sys.executable}" -m kuraya --play "%1"'


def is_registered():
    """已注册且处理命令未变则无需重复写入"""
    if os.name != 'nt':
        return False
    try:
        import winreg
        key = rf'Software\Classes\{SCHEME}\shell\open\command'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            current, _ = winreg.QueryValueEx(k, '')
            return current == handler_command()
    except OSError:
        return False


def register():
    """把协议注册到当前用户。返回 (是否成功, 说明)"""
    if os.name != 'nt':
        return False, '仅 Windows 支持自定义协议'
    try:
        import winreg
        base = rf'Software\Classes\{SCHEME}'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, '', 0, winreg.REG_SZ, f'URL:{SCHEME}')
            winreg.SetValueEx(k, 'URL Protocol', 0, winreg.REG_SZ, '')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf'{base}\shell\open\command') as k:
            winreg.SetValueEx(k, '', 0, winreg.REG_SZ, handler_command())
        return True, ''
    except OSError as exc:
        return False, str(exc)


def ensure_registered():
    """首次运行或程序位置变化时自动注册，静默失败不打断主流程"""
    if os.name != 'nt' or is_registered():
        return False
    ok, _ = register()
    return ok


def parse_url(raw):
    """从 kuraya:xxx 中还原出文件路径"""
    text = raw.strip().strip('"')
    if text.lower().startswith(SCHEME + ':'):
        text = text[len(SCHEME) + 1:]
    # 浏览器可能把路径当作 //host/path 处理，去掉多余的前导斜杠
    text = text.lstrip('/')
    return os.path.normpath(unquote(text))
