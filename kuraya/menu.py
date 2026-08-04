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


def menu_loop(draw_header, options, selected=0):
    """
    方向键导航 + 回车确认的选择器。options: [(key, label, desc)]。
    返回选中项的 key；Esc / EOF 返回 None。数字键仍是快捷方式。
    """
    from .keys import read_key
    while True:
        clear_screen()
        say()
        brand()
        say()
        draw_header()
        say()
        rule()
        say()
        for i, (key, label, desc) in enumerate(options):
            if i == selected:
                say(f'  {C.GOLD}▸{C.RESET} {C.GOLD}{key}{C.RESET}  '
                    f'{C.BOLD}{label}{C.RESET}'
                    f'{" " * max(2, 14 - dw(label))}{C.FAINT}{desc}{C.RESET}')
            else:
                say(f'  {C.GREY}·{C.RESET} {C.GOLD}{key}{C.RESET}  {label}'
                    f'{" " * max(2, 14 - dw(label))}{C.FAINT}{desc}{C.RESET}')
        say()
        hint = tr('↑↓ 选择 · 回车 确认 · Esc 返回')
        print(f'  {C.FAINT}{hint}{C.RESET} ', end='', flush=True)
        key = read_key()
        print()
        if key == 'up':
            selected = (selected - 1) % len(options)
        elif key == 'down':
            selected = (selected + 1) % len(options)
        elif key in ('enter', ''):
            return options[selected][0]
        elif key in ('esc', 'eof'):
            return None
        elif key.isdigit():
            for k, _, _ in options:
                if k == key:
                    return k


def draw_header(library, source):
    """主菜单头部：库状态 + 更新提示"""
    total = count_library(library)
    pending = count_pending(source)
    status_line(tr('影片库'), str(library),
                f'{total} {tr("部")}' if total is not None else tr('尚未生成页面'))
    status_line(tr('待整理'), str(source),
                f'{pending} {tr("个文件")}' if pending else tr('空'))
    # 有新版本时每轮都提示，直到升级
    notice = updater.text()
    if notice:
        say()
        say(notice)


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


def language_label(code):
    """语言选项显示名。语言名称用其自身语言书写，不参与翻译"""
    return {'': tr('跟随系统'), 'zh-CN': '简体中文',
            'zh-TW': '繁體中文', 'en': 'English'}.get(code, '')


def pause():
    """回车或 Esc 返回菜单"""
    from .keys import read_key
    print(f'\n  {C.FAINT}{tr("按回车返回菜单")}{C.RESET} ', end='', flush=True)
    read_key()
    print()


def language_menu():
    """选择界面语言：写入配置并立即生效（无需重启）"""
    from . import i18n
    lang_options = [
        ('1', tr('跟随系统'), ''),
        ('2', '简体中文', ''),
        ('3', '繁體中文', ''),
        ('4', 'English', ''),
    ]
    while True:
        cfg = settings.load()

        def header():
            say(f'  {C.BOLD}{tr("语言")}{C.RESET}')
            say()
            status_line(tr('当前'), language_label(cfg['language']))
            say()

        choice = menu_loop(header, lang_options + [('0', tr('返回'), '')])
        if choice is None or choice == '0':
            return
        code = {'1': '', '2': 'zh-CN', '3': 'zh-TW', '4': 'en'}.get(choice)
        if code is None:
            continue
        settings.save(language=code)
        i18n.refresh()
        say(f'    {C.GREEN}✓{C.RESET} {tr("已保存")}')
        pause()


def settings_menu():
    while True:
        cfg = settings.load()

        def header():
            say(f'  {C.BOLD}{tr("设置")}{C.RESET}')
            say()
            status_line(tr("影片库"), cfg['library'] or tr("(未设置)"))
            status_line(tr("待整理"), cfg['source'] or tr("(默认为影片库下的「待整理」)"))
            status_line(tr("播放器"), cfg['player'] or tr("(使用系统默认程序)"))
            say()

        options = [
            ('1', tr('影片库'), tr('整理好的影片存放位置')),
            ('2', tr('待整理'), tr('新下载的影片放这里')),
            ('3', tr('播放器'), tr('留空则用系统默认程序')),
            ('4', tr('语言'), tr('界面语言')),
            ('0', tr('返回'), ''),
        ]
        choice = menu_loop(header, options)
        if choice is None or choice == '0':
            return
        if choice == '1':
            edit_setting(tr('选择影片库目录'), 'library')
        elif choice == '2':
            edit_setting(tr('选择待整理目录'), 'source')
        elif choice == '3':
            edit_setting(tr('选择播放器程序'), 'player', kind='file')
        elif choice == '4':
            language_menu()
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

        options = [
            ('1', tr("刮削入库"), tr("处理待整理目录并归入片库")),
            ('2', tr("重建页面"), tr("重新扫描片库并生成 index.html")),
            ('3', tr("打开片库"), tr("在浏览器中查看")),
            ('4', tr("设置"), tr("影片库位置、待整理目录、播放器")),
            ('5', tr("更新"), tr("检查并安装新版本")),
            ('0', tr("退出"), ''),
        ]
        choice = menu_loop(lambda: draw_header(library, source), options)

        # Esc 与管道 EOF 视为退出（EOF 是脚本/双击场景的默认收尾）
        if choice is None or choice == '0':
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
