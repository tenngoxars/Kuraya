# -*- coding: utf-8 -*-
"""
交互式菜单。不带参数运行时进入，做完一件事回到菜单，直到选择退出。

命令行子命令仍然可用，供脚本与计划任务调用。
"""
import json
import os
import re

from . import cleanup, console, launcher, picker, settings, setup, updater
from .console import C, W, brand, dw, rule, say
from .i18n import tr


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
    """待整理目录里有多少个视频文件（复用 cleanup 的扫描逻辑）"""
    return len(cleanup.videos_in(source)) if source and os.path.isdir(source) else 0


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


def menu_loop(draw_header, options, selected=0, esc_label=None):
    """
    方向键导航 + 回车确认的选择器。options: [(key, label, desc)]。
    返回选中项的 key；Esc / EOF 返回 None。数字键仍是快捷方式。
    esc_label 描述 Esc 在此菜单的动作（主菜单为「退出」，子菜单为「返回」）。
    """
    from .keys import query_cursor, read_key
    esc_label = esc_label or tr('返回')
    n = len(options)
    # 切到备用屏幕（vim/htop 同款）：退出时恢复主屏原内容
    print('\x1b[?1049h', end='', flush=True)
    try:
        def option_text(i):
            """选项行文本。选中行金色粗体高亮"""
            key, label, desc = options[i]
            gap = ' ' * max(2, 14 - dw(label))
            if i == selected:
                return (f'  {C.GOLD}▸{C.RESET} {C.GOLD}{key}{C.RESET}  '
                        f'{C.BOLD}{label}{C.RESET}'
                        f'{gap}{C.FAINT}{desc}{C.RESET}')
            return (f'  {C.GREY}·{C.RESET} {C.GOLD}{key}{C.RESET}  {label}'
                    f'{gap}{C.FAINT}{desc}{C.RESET}')

        hint = tr('↑↓ 选择 · 回车 确认 · Esc {action}', action=esc_label)

        def draw_all():
            """整屏重绘。只在进入菜单与 CPR 不可用（回退）时调用：
            菜单内容固定，之后方向键只局部重绘两行。
            整屏重绘期间隐藏光标：Windows cls 逐行重画时
            光标在每行短暂停留，看起来像闪屏"""
            print('\x1b[?25l', end='', flush=True)
            clear_screen()
            say()
            brand()
            say()
            draw_header()
            say()
            rule()
            say()
            for i in range(n):
                say(option_text(i))
            say()
            # 完整换行输出：光标落在下一行行首
            print(f'  {C.FAINT}{hint}{C.RESET}')
            print('\x1b[?25h', end='', flush=True)

        draw_all()
        # 光标在提示行的下一行（print 换行后）；选项 i 所在行 =
        # 光标行 - n - 2 + i，方向键局部重绘由此定位。
        # 只查一次：菜单内容固定，光标位置与行号映射此后不变，
        # 不再反复 CPR 查询（\x1b[6n 应答要等几十毫秒）
        cursor = query_cursor()

        def repaint(i):
            """局部重绘第 i 个选项行，重绘后光标移回原位不打扰"""
            row = cursor[0] - n - 2 + i
            print(f'\x1b[{row};1H\x1b[2K{option_text(i)}'
                  f'\x1b[{cursor[0]};{cursor[1]}H', end='', flush=True)

        while True:
            key = read_key()
            if key in ('up', 'down'):
                old = selected
                selected = (selected - 1 if key == 'up'
                            else selected + 1) % n
                if cursor:
                    if old != selected:
                        repaint(old)
                        repaint(selected)
                else:
                    # CPR 不可用（终端不应答）时无法定位局部重绘，
                    # 回退整屏重绘并重查光标：方向键照常可用
                    draw_all()
                    cursor = query_cursor()
                continue
            if key in ('enter', ''):
                return options[selected][0]
            if key in ('esc', 'eof'):
                return None
            if key.isdigit():
                for k, _, _ in options:
                    if k == key:
                        return k
    finally:
        print('\x1b[?1049l', end='', flush=True)


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
        path = setup.ask_path(label, kind=kind)
        if not path:
            say(f'    {C.GREY}{tr("已取消")}{C.RESET}')
            return
    elif not path:
        say(f'    {C.GREY}{tr("已取消")}{C.RESET}')
        return
    settings.save(**{key: path})
    saved = tr('已保存：{path}', path=path)
    say(f'    {C.GREEN}✓{C.RESET} {saved}')


def language_label(code):
    """语言选项显示名。语言名称用其自身语言书写，不参与翻译"""
    return {'': tr('跟随系统'), 'zh-CN': '简体中文',
            'zh-TW': '繁體中文', 'en': 'English'}.get(code, '')


def pause():
    """回车或 Esc 返回菜单"""
    from .keys import read_key
    print(f'\n  {C.FAINT}{tr("按回车返回菜单")}{C.RESET}')
    read_key()


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
        # 头部实时显示当前语言，无需暂停确认，Esc 随时可返回设置


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
            pause()
        elif choice == '2':
            edit_setting(tr('选择待整理目录'), 'source')
            pause()
        elif choice == '3':
            edit_setting(tr('选择播放器程序'), 'player', kind='file')
            pause()
        elif choice == '4':
            language_menu()
            # 语言菜单内按 Esc 返回即完成，不再追加「按回车返回菜单」


def run():
    """菜单主循环。返回退出码"""
    console.enable_ansi()

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

        def header():
            draw_header(library, source)

        options = [
            ('1', tr("刮削入库"), tr("处理待整理目录并归入片库")),
            ('2', tr("重建页面"), tr("重新扫描片库并生成 index.html")),
            ('3', tr("打开片库"), tr("在浏览器中查看")),
            ('4', tr("设置"), tr("影片库位置、待整理目录、播放器")),
            ('5', tr("更新"), tr("检查并安装新版本")),
            ('0', tr("退出"), ''),
        ]
        choice = menu_loop(header, options,
                           esc_label=tr('退出'))

        # Esc 与管道 EOF 视为退出（EOF 是脚本/双击场景的默认收尾）
        if choice is None or choice == '0':
            return 0
        if choice == '1':
            # menu_loop 已退出备用屏幕，主屏还停在运行前的内容上；
            # 先清屏再执行，让刮削/重建的输出从干净起点开始
            clear_screen()
            say()
            _, offered = launcher.cmd_all(library, source)
            launcher.spin.stop()
            # 刮削后的「打开片库」选择器已经让用户按过键，不必再等一次回车
            if not offered:
                pause()
        elif choice == '2':
            clear_screen()
            say()
            launcher.cmd_rebuild(library)
            launcher.spin.stop()
            pause()
        elif choice == '3':
            clear_screen()
            say()
            launcher.open_library(library)
            pause()
        elif choice == '4':
            settings_menu()
        elif choice == '5':
            clear_screen()
            say()
            updater.update()
            # 程序文件已换成新版，内存里跑的还是旧版：重开新版再退出，
            # 用户不用自己关了再点一次
            if updater.restart_needed():
                if not updater.relaunch():
                    say()
                    say(f'  {C.GREY}{tr("已更新，请重新启动本程序")}{C.RESET}')
                    pause()
                return 0
            pause()
