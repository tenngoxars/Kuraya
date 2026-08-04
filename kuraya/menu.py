# -*- coding: utf-8 -*-
"""
交互式菜单。不带参数运行时进入，做完一件事回到菜单，直到选择退出。

命令行子命令仍然可用，供脚本与计划任务调用。
"""
import json
import os
import re
import subprocess
import sys

from . import launcher, picker, settings
from .launcher import C, W, brand, dw, rule, say


def clear_screen():
    """清屏。终端不支持时退回打印空行，不让报错干扰界面"""
    try:
        if os.name == 'nt':
            os.system('cls')
        elif os.environ.get('TERM'):
            os.system('clear')
        else:
            print('\n' * 3)
    except OSError:
        pass


def count_pending(source):
    """待整理目录里有多少个视频文件"""
    if not source or not os.path.isdir(source):
        return 0
    return sum(1 for _, _, files in os.walk(source)
               for f in files if os.path.splitext(f)[1].lower() in settings.VIDEO_EXTS)


def count_library(library):
    """片库页面里已收录多少部。页面还没生成时返回 None"""
    index = os.path.join(str(library), 'index.html')
    if not os.path.isfile(index):
        return None
    try:
        with open(index, encoding='utf-8') as fp:
            match = re.search(r'const DATA = (\[.*?\]);', fp.read(), re.S)
        return len(json.loads(match.group(1))) if match else None
    except (OSError, ValueError):
        return None


def status_line(label, value, note=''):
    """路径过长时从中间截断，保证右侧的统计数字不被挤走"""
    room = W - dw(label) - dw(note) - 6
    value = shorten(str(value), room)
    gap = W - dw(label) - dw(value) - dw(note) - 4
    say(f'    {C.GREY}{label}{C.RESET}  {value}'
        f'{" " * max(1, gap)}{C.FAINT}{note}{C.RESET}')


def shorten(path, room):
    """路径超长时保留首尾，中间用省略号代替"""
    if dw(path) <= room or room < 12:
        return path
    keep = (room - 3) // 2
    head, tail = path[:keep], path[-keep:]
    return f'{head}…{tail}'


def entry(key, name, desc):
    say(f'    {C.GOLD}{key}{C.RESET}  {C.BOLD}{name}{C.RESET}'
        f'{" " * max(2, 14 - dw(name))}{C.FAINT}{desc}{C.RESET}')


def draw(library, source):
    """绘制菜单主体，同时显示当前状态"""
    clear_screen()
    say()
    brand()
    say()

    total = count_library(library)
    pending = count_pending(source)
    status_line('影片库', str(library),
                f'{total} 部' if total is not None else '尚未生成页面')
    status_line('待整理', str(source),
                f'{pending} 个文件' if pending else '空')
    say()
    rule()
    say()

    entry('1', '刮削入库', '处理待整理目录并归入片库')
    entry('2', '重建页面', '重新扫描片库并生成 index.html')
    entry('3', '打开片库', '在浏览器中查看')
    entry('4', '设置', '影片库位置、待整理目录、播放器')
    entry('0', '退出', '')
    say()


def pause():
    try:
        input(f'\n  {C.FAINT}按回车返回菜单{C.RESET}')
    except (EOFError, KeyboardInterrupt):
        pass


def ask(prompt='请选择'):
    try:
        return input(f'  {prompt} {C.GOLD}›{C.RESET} ').strip()
    except (EOFError, KeyboardInterrupt):
        return '0'


def open_library(library):
    """用默认浏览器打开片库页面"""
    index = os.path.join(str(library), 'index.html')
    if not os.path.isfile(index):
        say(f'    {C.RED}✕ 页面尚未生成，请先执行「重建页面」{C.RESET}')
        return
    try:
        if os.name == 'nt':
            os.startfile(index)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', index])
        else:
            subprocess.Popen(['xdg-open', index])
        say(f'    {C.GREEN}✓{C.RESET} 已在浏览器中打开')
    except OSError as exc:
        say(f'    {C.RED}✕ 打开失败：{exc}{C.RESET}')


def edit_setting(label, key, kind='folder'):
    """弹出选择框修改单项设置"""
    say(f'  {C.GOLD}▸{C.RESET} 即将弹出选择窗口：{label}')
    launcher.spin.set('等待选择')
    path, err = picker.pick(kind, label)
    launcher.spin.hide()

    if err:
        # 无桌面/无 tkinter 的环境改为手动输入，不把设置堵死
        say(f'    {C.RED}✕ 无法打开选择窗口：{err}{C.RESET}')
        path = ask_path(label, kind)
        if not path:
            say(f'    {C.GREY}已取消{C.RESET}')
            return
    elif not path:
        say(f'    {C.GREY}已取消{C.RESET}')
        return
    settings.save(**{key: path})
    say(f'    {C.GREEN}✓{C.RESET} 已保存：{path}')


def ask_path(label, kind='folder'):
    """选择框用不了时改为终端输入（与首次引导的手动输入同款）"""
    say(f'    {C.GREY}改为手动输入，路径支持 ~ 展开{C.RESET}')
    try:
        raw = input(f'  {label}路径（回车取消） {C.GOLD}›{C.RESET} ').strip().strip('"\'')
    except (EOFError, KeyboardInterrupt):
        return ''
    if not raw:
        return ''
    path = os.path.expanduser(raw)
    if kind == 'folder' and not os.path.isdir(path):
        say(f'    {C.RED}✕{C.RESET} 目录不存在：{path}')
        return ''
    if kind == 'file' and not os.path.isfile(path):
        say(f'    {C.RED}✕{C.RESET} 文件不存在：{path}（留空可使用系统默认播放器）')
        return ''
    return path


def settings_menu():
    while True:
        cfg = settings.load()
        clear_screen()
        say()
        brand()
        say()
        say(f'  {C.BOLD}设置{C.RESET}')
        say()
        status_line('影片库', cfg['library'] or '(未设置)')
        status_line('待整理', cfg['source'] or '(默认为影片库下的「待整理」)')
        status_line('播放器', cfg['player'] or '(使用系统默认程序)')
        say()
        rule()
        say()
        entry('1', '影片库', '整理好的影片存放位置')
        entry('2', '待整理', '新下载的影片放这里')
        entry('3', '播放器', '留空则用系统默认程序')
        entry('0', '返回', '')
        say()

        choice = ask()
        if choice == '0':
            return
        if choice == '1':
            edit_setting('选择影片库目录', 'library')
        elif choice == '2':
            edit_setting('选择待整理目录', 'source')
        elif choice == '3':
            edit_setting('选择播放器程序', 'player', kind='file')
        else:
            continue
        pause()


def run():
    """菜单主循环。返回退出码"""
    launcher.enable_ansi()

    while True:
        cfg = settings.load()
        if not cfg['configured']:
            # 未配置时先走引导，完成后再进菜单
            say()
            if launcher.first_run_setup() is None:
                launcher.wait_exit()
                return 2
            continue

        try:
            library, source = settings.ensure_dirs(cfg['library'], cfg['source'])
        except settings.LibraryMissing as exc:
            say()
            launcher.show_error(exc)
            say()
            say(f'  {C.GREY}请选择「设置」重新指定影片库位置{C.RESET}')
            pause()
            settings_menu()
            continue

        draw(library, source)
        choice = ask()

        if choice == '0':
            return 0
        if choice == '1':
            say()
            launcher.cmd_all(library, source)
            launcher.spin.stop()
            pause()
        elif choice == '2':
            say()
            launcher.cmd_rebuild(library)
            launcher.spin.stop()
            pause()
        elif choice == '3':
            say()
            open_library(library)
            pause()
        elif choice == '4':
            settings_menu()
