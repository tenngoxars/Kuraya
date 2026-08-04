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

from . import launcher, picker, settings, setup, updater
from .i18n import tr
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

    # 有新版本时每轮都提示，直到升级
    notice = updater.text()
    if notice:
        say(notice)
        say()

    entry('1', tr("刮削入库"), tr("处理待整理目录并归入片库"))
    entry('2', tr("重建页面"), tr("重新扫描片库并生成 index.html"))
    entry('3', tr("打开片库"), tr("在浏览器中查看"))
    entry('4', tr("设置"), tr("影片库位置、待整理目录、播放器"))
    entry('5', tr("更新"), tr("检查并安装新版本"))
    entry('0', tr("退出"), '')
    say()


def pause():
    try:
        input(f'\n  {C.FAINT}{tr("按回车返回菜单")}{C.RESET}')
    except (EOFError, KeyboardInterrupt):
        pass


def ask(prompt=tr("请选择")):
    try:
        return input(f'  {prompt} {C.GOLD}›{C.RESET} ').strip()
    except (EOFError, KeyboardInterrupt):
        return '0'


def open_library(library):
    """用默认浏览器打开片库页面"""
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


def edit_setting(label, key, kind='folder'):
    """弹出选择框修改单项设置"""
    pick_msg = tr('即将弹出选择窗口：{label}', label=label)
    say(f'  {C.GOLD}▸{C.RESET} {pick_msg}')
    launcher.spin.set(tr('等待选择'))
    path, err = picker.pick(kind, label)
    launcher.spin.hide()

    if err:
        # 无桌面/无 tkinter 的环境改为手动输入，不把设置堵死
        pick_err = tr('无法打开选择窗口：{err}', err=err)
        say(f'    {C.RED}✕ {pick_err}{C.RESET}')
        path = ask_path(label, kind)
        if not path:
            say(f'    {C.GREY}{tr("已取消")}{C.RESET}')
            return
    elif not path:
        say(f'    {C.GREY}{tr("已取消")}{C.RESET}')
        return
    settings.save(**{key: path})
    saved = tr('已保存：{path}', path=path)
    say(f'    {C.GREEN}✓{C.RESET} {saved}')


def ask_path(label, kind='folder'):
    """选择框用不了时改为终端输入（与首次引导的手动输入同款）"""
    manual_msg = tr('改为手动输入，路径支持 ~ 展开')
    say(f'    {C.GREY}{manual_msg}{C.RESET}')
    try:
        path_prompt = tr('{label}路径（回车取消）', label=label)
        raw = input(f'  {path_prompt} {C.GOLD}›{C.RESET} ').strip().strip('"\'')
    except (EOFError, KeyboardInterrupt):
        return ''
    if not raw:
        return ''
    path = os.path.expanduser(raw)
    if kind == 'folder' and not os.path.isdir(path):
        missing = tr('目录不存在：{path}', path=path)
        say(f'    {C.RED}✕{C.RESET} {missing}')
        return ''
    if kind == 'file' and not os.path.isfile(path):
        missing = tr('文件不存在：{path}（留空可使用系统默认播放器）', path=path)
        say(f'    {C.RED}✕{C.RESET} {missing}')
        return ''
    return path


def settings_menu():
    while True:
        cfg = settings.load()
        clear_screen()
        say()
        brand()
        say()
        say(f'  {C.BOLD}{tr("设置")}{C.RESET}')
        say()
        status_line(tr("影片库"), cfg['library'] or tr("(未设置)"))
        status_line(tr("待整理"), cfg['source'] or tr("(默认为影片库下的「待整理」)"))
        status_line(tr("播放器"), cfg['player'] or tr("(使用系统默认程序)"))
        say()
        rule()
        say()
        entry('1', tr("影片库"), tr("整理好的影片存放位置"))
        entry('2', tr("待整理"), tr("新下载的影片放这里"))
        entry('3', tr("播放器"), tr("留空则用系统默认程序"))
        entry('0', tr("返回"), '')
        say()

        choice = ask()
        if choice == '0':
            return
        if choice == '1':
            edit_setting(tr("选择影片库目录"), 'library')
        elif choice == '2':
            edit_setting(tr("选择待整理目录"), 'source')
        elif choice == '3':
            edit_setting(tr("选择播放器程序"), 'player', kind='file')
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
            if setup.first_run_setup() is None:
                setup.wait_exit()
                return 2
            continue

        try:
            library, source = settings.ensure_dirs(cfg['library'], cfg['source'])
        except settings.LibraryMissing as exc:
            say()
            setup.show_error(exc)
            say()
            say(f'  {C.GREY}{tr("请选择「设置」重新指定影片库位置")}{C.RESET}')
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
        elif choice == '5':
            say()
            updater.update()
            pause()
