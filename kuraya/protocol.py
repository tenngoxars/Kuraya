# -*- coding: utf-8 -*-
"""
自定义 URL 协议 kuraya: 的注册与调用。

片库页面是静态 HTML，浏览器无法直接启动播放器，需借助自定义协议：
页面上的链接形如 kuraya:<百分号编码的绝对路径>，由本程序接管并唤起播放器。

注册写入 HKEY_CURRENT_USER，不需要管理员权限。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

SCHEME = 'kuraya'

_LSREGISTER = ('/System/Library/Frameworks/CoreServices.framework/Frameworks/'
               'LaunchServices.framework/Support/lsregister')


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


def _shell_app_ready(base):
    """base 目录下的壳 app 是否完整可用：Contents/MacOS 下要有可执行文件。
    后台安装可能被中断留下半成品目录，只有目录骨架不算装好。
    play_mode 与 ensure_shell_app 共用同一判定，避免一处判好一处判坏。
    """
    macos = Path(base) / 'Kuraya.app' / 'Contents' / 'MacOS'
    return macos.is_dir() and any(macos.iterdir())


def ensure_shell_app():
    """
    打包版在 macOS 上的点击封面播放：把随包分发的 Kuraya.app
    （osacompile 生成的协议壳，见 packaging/scheme_handler.applescript）
    装到 ~/Applications 并注册。放 main() 里自愈，安装方式无关——
    brew 的 sandbox 写不了用户目录，由程序自身来完成。
    失败静默，不影响主流程。
    """
    if sys.platform != 'darwin' or not getattr(sys, 'frozen', False):
        return False
    target = Path.home() / 'Applications' / 'Kuraya.app'
    if _shell_app_ready(target.parent):
        return True
    # 随包位置：zip/brew/脚本安装的壳 app 都在 exe 父级（如 ~/.local/opt/Kuraya.app、
    # libexec/Kuraya.app），exe 同级只兜底手动布局
    here = Path(sys.executable).resolve().parent
    sources = (here / 'Kuraya.app', here.parent / 'Kuraya.app')
    src = next((p for p in sources if p.is_dir()), None)
    if src is None:
        return False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
        subprocess.run([_LSREGISTER, '-f', str(target)],
                       capture_output=True, timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def play_mode():
    """当前平台能否用 kuraya: 协议点封面播放，返回 'protocol' 或 'copy'。
    页面据此决定链接形态：协议不可用时降级为复制路径，不留点了没反应的封面。
    """
    if os.name == 'nt':
        # Windows 自动注册，被安全软件拦截未注册时降级
        return 'protocol' if is_registered() else 'copy'
    if sys.platform == 'darwin':
        # mac 依赖首次运行自装的壳 app（~/Applications/Kuraya.app）
        home = Path.home()
        apps = (home / 'Applications', Path('/Applications'))
        return 'protocol' if any(_shell_app_ready(base) for base in apps) else 'copy'
    # Linux: 看 xdg 是否已注册 kuraya: 协议处理器（安装脚本负责注册）
    try:
        out = subprocess.run(
            ['xdg-mime', 'query', 'default', 'x-scheme-handler/kuraya'],
            capture_output=True, text=True, timeout=5)
        return 'protocol' if out.stdout.strip() else 'copy'
    except (OSError, subprocess.SubprocessError):
        return 'copy'


def parse_url(raw):
    """从 kuraya:xxx 中还原出文件路径"""
    text = raw.strip().strip('"')
    if text.lower().startswith(SCHEME + ':'):
        text = text[len(SCHEME) + 1:]
    text = unquote(text)
    # 浏览器可能把路径当作 //host/path 处理，需要去掉多余的前导斜杠。
    # 但只能处理相对路径——POSIX 绝对路径的根斜杠一旦被去掉就再找不回来了
    if not os.path.isabs(text):
        text = text.lstrip('/')
    return os.path.normpath(text)
