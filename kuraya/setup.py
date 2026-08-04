# -*- coding: utf-8 -*-
"""
首次运行引导与启动前准备：说明用途、弹出原生目录选择框、登记 PATH、
读取配置。从 launcher 拆出，避免单文件超过行数规范。
"""
import os
import sys

from . import picker, settings
from .i18n import tr
from .launcher import C, ConfigError, brand, box, info, say, spin


def ask_library_path():
    """
    选择框用不了时改为在终端里输入。

    装成命令行工具的场景下这不是退路而是常态：macOS 的 Homebrew Python 默认不带
    tkinter，服务器上更是连桌面都没有。让人去手动创建一个还不存在的配置文件，
    等于把首次运行堵死。
    """
    say(f'    {C.GREY}{tr("改为手动输入。也可以随时用下面这条命令设置：")}{C.RESET}')
    say(f'    {C.FAINT}kuraya config --set-library <{tr("影片库目录")}>{C.RESET}')
    say()
    try:
        raw = input(f'  {tr("影片库目录")} {C.GOLD}›{C.RESET} ').strip().strip('"\'')
    except (EOFError, KeyboardInterrupt):
        return ''
    if not raw:
        return ''

    path = os.path.expanduser(raw)
    if not os.path.isdir(path):
        missing = tr('目录不存在：{path}', path=path)
        say(f'    {C.RED}✕{C.RESET} {missing}')
        return ''
    return path


def first_run_setup():
    """没有配置时的引导：说明用途，弹出原生目录选择框，写入配置"""
    brand()
    say()
    say(f'  {C.BOLD}{tr("初次使用")}{C.RESET}')
    say()
    info(tr("需要先指定影片库位置——整理好的影片会按「演员名\\番号」存放在那里。"))
    info(tr("待整理目录默认为影片库下的「待整理」，把新下载的影片放进去即可。"))
    say()

    say(f'  {C.GOLD}▸{C.RESET} {tr("即将弹出目录选择窗口，请选择影片库位置")}')
    spin.set(tr("等待选择目录"))
    path, err = picker.pick('folder', tr("选择影片库目录"))
    spin.hide()

    if err:
        pick_err = tr('无法打开选择窗口：{err}', err=err)
        say(f'    {C.RED}✕{C.RESET} {pick_err}')
        path = ask_library_path()
    if not path:
        say(f'    {C.GREY}{tr("已取消")}{C.RESET}')
        return None

    player = settings.detect_player()
    cfg = settings.save(library=path, source='', player=player)
    # 用户刚亲自选定，允许创建
    library, source = settings.ensure_dirs(cfg['library'], cfg['source'], create_library=True)

    say(f'    {C.GREEN}✓{C.RESET} {tr("影片库")}  {library}')
    say(f'    {C.GREEN}✓{C.RESET} {tr("待整理")}  {source}')
    if player:
        say(f'    {C.GREEN}✓{C.RESET} {tr("播放器")}  {player}')
    else:
        say(f'    {C.GREY}{tr("未检测到常见播放器，将用系统默认程序打开")}{C.RESET}')
    say()
    info(tr("以上设置已保存，之后可在「设置.ini」中修改。"))
    say()
    offer_path_install()
    return library, source


def offer_path_install():
    """登记到 PATH 会改动用户环境变量，须先征得同意，且只问一次"""
    from . import pathenv
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        return
    if pathenv.is_installed() or settings.load().get('path_asked'):
        return

    say(f'  {C.BOLD}{tr("以后想更方便地打开吗？")}{C.RESET}')
    info(tr("现在每次都要找到这个程序双击。设置一下的话，"))
    info(tr("在任意窗口输入 kuraya 就能直接打开，不用再翻文件夹。"))
    say()
    info(tr("这项设置只影响你自己的账户，之后随时可以取消。"))
    say()
    from .keys import read_key
    print(f'  {tr("设置吗？输入 y 确认，直接回车跳过")} {C.GOLD}›{C.RESET}')
    key = read_key()

    settings.save(path_asked='1')      # 无论选什么都不再追问
    if key != 'y' and key != 'Y':
        say(f'    {C.GREY}{tr("已跳过。以后想设置，运行 kuraya install 即可")}{C.RESET}')
        say()
        return

    ok, why = pathenv.install()
    if ok:
        say(f'    {C.GREEN}✓{C.RESET} {tr("设置完成")}')
        say(f'    {C.GREY}{tr("下次")}{C.RESET}{C.BOLD}{tr("新打开")}{C.RESET}'
            f'{C.GREY}{tr("一个命令行窗口，输入 kuraya 就能启动（当前已打开的窗口不算）")}'
            f'{C.RESET}')
    else:
        why_msg = tr('设置失败：{why}', why=why)
        say(f'    {C.RED}✕ {why_msg}{C.RESET}')
    say()


def load_paths():
    """读取配置；未配置则走首次运行引导。返回 (影片库, 待整理) 或 None"""
    cfg = settings.load()
    if not cfg['configured']:
        return first_run_setup()
    try:
        return settings.ensure_dirs(cfg['library'], cfg['source'])
    except settings.LibraryMissing as exc:
        raise ConfigError(str(exc))
    except OSError as exc:
        raise ConfigError(tr('无法访问影片库目录：{exc}', exc=exc))


def wait_exit():
    try:
        input(f'\n  {C.FAINT}{tr("按回车键关闭窗口")}{C.RESET}')
    except (EOFError, KeyboardInterrupt):
        pass


def show_error(exc):
    box([(tr('无法启动'), C.BOLD)], C.RED)
    say()
    for row in str(exc).split('\n'):
        say(f'  {C.RED if not row.startswith(" ") else C.GREY}{row}{C.RESET}')
