# -*- coding: utf-8 -*-
"""
Kuraya 命令行入口。

不带参数时走交互流程（双击运行即此行为）；带参数时提供细分命令，
可被脚本或计划任务调用。
"""
import argparse
import os
import runpy
import subprocess
import sys
import threading

from . import NAME, TAGLINE, KANJI, __version__, console, protocol, settings
from .i18n import tr
from .settings import FROZEN

# 退出码：供脚本判断结果
OK, PARTIAL, CONFIG_ERROR = 0, 1, 2

# 内部子命令：主流程以子进程方式再次调用本程序时使用，不对外暴露
INTERNAL = {'--internal-gallery': 'gallery',
            '--internal-cleanup': 'cleanup'}


def run_internal(kind, args):
    """
    打包成 EXE 后 sys.executable 指向 EXE 自身，无法再用它执行 .py 脚本，
    因此让同一个可执行文件按参数分派，保持子进程隔离不变。
    """
    # 打包后 PYTHONIOENCODING 不一定生效，须显式指定输出编码，
    # 否则父进程收到的中文路径会是乱码
    console.ensure_utf8()
    if kind == 'gallery':
        sys.argv = ['gallery', *args]
        runpy.run_module('kuraya.gallery', run_name='__main__')
    elif kind == 'cleanup':
        sys.argv = ['cleanup', *args]
        runpy.run_module('kuraya.cleanup', run_name='__main__')
    return OK


# ---------- 各命令 ----------
def resolve_paths(launcher, library_opt=None, source_opt=None):
    """确定影片库与待整理目录，命令行参数优先于配置文件"""
    if library_opt:
        return settings.ensure_dirs(library_opt, source_opt or '', create_library=False)

    from . import setup
    paths = setup.load_paths()
    if paths is None:
        return None
    library, source = paths
    if source_opt:
        source = settings.Path(source_opt).expanduser().resolve()
        source.mkdir(parents=True, exist_ok=True)
    return library, source


def do_play(raw_path):
    """由 kuraya: 协议调用，唤起播放器后立即退出"""
    path = protocol.parse_url(raw_path)
    if not os.path.isfile(path):
        return 1
    player = settings.load().get('player') or settings.detect_player()
    try:
        if player and os.path.isfile(player):
            subprocess.Popen([player, path])
            return OK
    except OSError:
        return 1
    return OK if protocol.open_default(path) else 1


def do_register(quiet=False):
    ok, why = protocol.register()
    if not quiet:
        if ok:
            print(tr("  已注册 kuraya: 协议，片库页面可以直接唤起播放器。"))
        else:
            print(tr("  注册失败：{why}", why=why))
            print(tr("  若被安全软件拦截，可将本程序加入白名单后重试。"))
    return OK if ok else 1


def do_install(remove=False):
    """把程序目录登记到用户 PATH，或卸载（移除命令入口与程序文件）"""
    from . import pathenv
    if remove:
        return do_uninstall()

    ok, why = pathenv.install()
    if ok:
        print(tr("  设置完成。"))
        print(tr("  下次新打开一个命令行窗口，输入 kuraya 就能启动。"))
        print(tr("  （当前已经打开的窗口不会生效，需要新开一个）"))
    else:
        print(tr("  设置失败：{why}", why=why))
    return OK if ok else 1


def do_uninstall():
    """卸载：移除 PATH 登记、命令行入口与程序文件"""
    import shutil
    from pathlib import Path

    from . import pathenv, settings
    from .launcher import C

    exe = Path(sys.executable).resolve()
    if sys.platform == 'darwin' and 'Cellar' in exe.parts and 'kuraya' in exe.parts:
        print(f'  {C.RED}✕{C.RESET} {tr("当前是 Homebrew 安装，请运行")} '
              f'{C.BOLD}brew uninstall kuraya{C.RESET}')
        return 1
    if not FROZEN:
        print(f'  {C.RED}✕{C.RESET} {tr("源码或 pip 安装请直接删除对应目录")}')
        return 1

    try:
        confirm_prompt = tr('将卸载 Kuraya（移除命令入口与程序文件），'
                            '是否继续？[y/N]')
        answer = input(f'  {confirm_prompt} {C.GOLD}›{C.RESET} '
                       ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return 0
    if answer not in ('y', 'yes'):
        print(tr("  已取消"))
        return 0

    # 1. 移除 PATH 登记（Windows 注册表；POSIX 由 install.sh 写入 shell 配置）
    if sys.platform == 'win32':
        ok, why = pathenv.uninstall()
        if not ok:
            print(f'  {C.RED}✕{C.RESET} {tr("移除 PATH 失败：{why}", why=why)}')
            return 1
        print(f'  {C.GREEN}✓{C.RESET} {tr("已从 PATH 移除")}')
    else:
        path_hint = tr('PATH 条目在 shell 配置中（install.sh 写入），'
                       '请手动从 ~/.zshrc 或 ~/.bashrc 移除 ~/.local/bin')
        print(f'  {C.GREY}{path_hint}{C.RESET}')

    # 2. 删除命令行入口（install.sh 创建的 shim）
    shim = Path.home() / '.local' / 'bin' / 'kuraya'
    if os.name != 'nt' and shim.is_file():
        try:
            shim.unlink()
            print(f'  {C.GREEN}✓{C.RESET} {tr("已删除命令入口 {path}", path=shim)}')
        except OSError as exc:
            print(f'  {C.RED}✕{C.RESET} '
                  f'{tr("删除命令入口失败：{exc}", exc=exc)}')

    # 3. 删除程序目录与壳 app（Windows 上运行中的 exe 无法自删）
    target = Path(sys.executable).parent
    if sys.platform == 'win32':
        manual_msg = tr('程序目录需手动删除（运行中的程序无法自删）：{path}',
                        path=target)
        print(f'  {C.GREY}{manual_msg}{C.RESET}')
    else:
        try:
            shutil.rmtree(target)
            print(f'  {C.GREEN}✓{C.RESET} '
                  f'{tr("已删除程序目录 {path}", path=target)}')
        except OSError as exc:
            print(f'  {C.RED}✕{C.RESET} '
                  f'{tr("删除程序目录失败：{exc}", exc=exc)}')
        for app in (target.parent / 'Kuraya.app',
                    Path.home() / 'Applications' / 'Kuraya.app'):
            # ignore_errors=True 已容忍路径不存在，无需先 exists() 判断
            shutil.rmtree(app, ignore_errors=True)

    config_msg = tr('配置保留在 {path}，如需彻底清理请删除该目录',
                    path=settings.APP_DIR)
    print(f'  {C.GREY}{config_msg}{C.RESET}')
    return 0


def do_selftest():
    """
    用一组固定番号实跑数据源，核对解析规则是否仍然有效。

    单一数据源的风险是站点改版后整个工具失灵，而失灵的样子是「查不到」，
    与影片本身不在支持范围内长得一模一样。这条命令把两者分开。
    """
    # 抓来的标题与演员名是日文与繁体中文，控制台默认编码放不下
    console.ensure_utf8()

    from .media import javbus
    print(tr("  正在核对 javbus 的解析规则，需要联网……"))
    print()
    failed = javbus.selftest()
    print()
    if failed:
        print(tr("  {failed} 个番号未能取全字段。", failed=failed))
        print(tr("  若全部失败，多半是站点改版或网络不通；"))
        print(tr("  个别失败通常是该条目本身信息不全，可以忽略。"))
        return PARTIAL
    print(tr("  解析规则正常。"))
    return OK


def do_config(args):
    """查看或修改配置"""
    changed = {}
    if args.set_library:
        changed['library'] = args.set_library
    if args.set_source is not None:
        changed['source'] = args.set_source
    if args.set_player is not None:
        changed['player'] = args.set_player

    if changed:
        cfg = settings.save(**changed)
        print(tr("  已保存："), settings.SETTINGS_FILE)
    else:
        cfg = settings.load()

    print(f'  {tr("影片库")}  {cfg["library"] or tr("(未设置)")}')
    print(f'  {tr("待整理")}  {cfg["source"] or tr("(未设置)")}')
    print(f'  {tr("播放器")}  {cfg["player"] or tr("(使用系统默认程序)")}')
    return OK if cfg['configured'] else CONFIG_ERROR


# ---------- 参数定义 ----------
def build_parser():
    # 通用参数放进父解析器，主命令与各子命令都继承，
    # 这样 -v 写在子命令前后都能识别。
    # default=SUPPRESS 保证未指定时不产生属性，避免子命令的默认值覆盖前置写法。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--library', default=argparse.SUPPRESS,
                        help=tr("本次使用的影片库目录，覆盖配置"))
    common.add_argument('--source', default=argparse.SUPPRESS,
                        help=tr("本次使用的待整理目录，覆盖配置"))
    common.add_argument('--limit', type=int, default=argparse.SUPPRESS,
                        help=tr("最多处理多少部"))
    common.add_argument('--dry-run', action='store_true', default=argparse.SUPPRESS,
                        help=tr("只显示将要处理的内容，不改动文件"))
    common.add_argument('-q', '--quiet', action='store_true', default=argparse.SUPPRESS,
                        help=tr("精简输出，供脚本调用"))
    common.add_argument('-v', '--verbose', action='store_true', default=argparse.SUPPRESS,
                        help=tr("输出各步骤的原始日志"))
    common.add_argument('--yes', action='store_true', default=argparse.SUPPRESS,
                        help=tr("结束后不等待按键，供计划任务调用"))

    p = argparse.ArgumentParser(
        prog='kuraya', parents=[common],
        description=f'◈  {" ".join(NAME)}   {KANJI}\n\n'
                    f'{tr(TAGLINE)}{tr("。不带参数运行则执行完整入库流程。")}',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=tr("示例：\n"
                  '  kuraya                     完整流程：刮削 → 清理 → 重建页面\n'
                  '  kuraya scrape --limit 3    只刮削前 3 部，用于试跑\n'
                  '  kuraya rebuild -v          重建页面并输出详细日志\n'
                  '  kuraya selftest            刮不到时先跑这条，确认是不是站点改版\n'
                  '  kuraya config --set-library D:\\Media\\Library\n'))
    p.add_argument('--version', action='version',
                   version=f'{NAME} {KANJI}  v{__version__}')

    sub = p.add_subparsers(dest='command', metavar=tr("命令"))
    sub.add_parser('scrape', parents=[common], help=tr("只刮削与清理，不重建页面"))
    sub.add_parser('rebuild', parents=[common], help=tr("只重建片库页面"))
    sub.add_parser('selftest', parents=[common], help=tr("核对数据源解析规则是否仍有效"))
    sub.add_parser('update', parents=[common], help=tr("检查并安装新版本"))
    sub.add_parser('register', parents=[common], help=tr("重新注册 kuraya: 协议"))
    sub.add_parser('install', parents=[common], help=tr("设置为在任意窗口输入 kuraya 即可启动"))
    sub.add_parser('uninstall', parents=[common], help=tr('卸载 Kuraya（移除命令入口与程序文件）'))

    play = sub.add_parser('play', parents=[common], help=tr("播放指定文件"))
    play.add_argument('target', help=tr("影片路径"))

    conf = sub.add_parser('config', parents=[common], help=tr("查看或修改配置"))
    conf.add_argument('--set-library', help=tr("设置影片库目录"))
    conf.add_argument('--set-source', help=tr("设置待整理目录，留空则用默认位置"))
    conf.add_argument('--set-player', help=tr("设置播放器路径，留空则用系统默认程序"))

    return p


def main():
    argv = sys.argv[1:]

    # 内部调用与协议调用先于参数解析处理：前者格式固定，
    # 后者的 URL 可能含被 argparse 误认为选项的字符
    if argv and argv[0] in INTERNAL:
        return run_internal(INTERNAL[argv[0]], argv[1:])

    # 首次运行后台自装点击封面播放用的壳 app。lsregister 首次初始化
    # LaunchServices 数据库可能卡很久且 Ctrl+C 无效，不能阻塞主流程
    threading.Thread(target=protocol.ensure_shell_app, daemon=True).start()

    if argv and argv[0] == '--play':
        return do_play(argv[1] if len(argv) > 1 else '')

    # 不带任何参数：进入交互式菜单
    if not argv:
        from . import menu
        protocol.ensure_registered()
        return menu.run()

    args = build_parser().parse_args(argv)

    # 参数写在子命令前后都可，未指定时属性不存在，统一用 getattr 取值
    opt = lambda name, default=None: getattr(args, name, default)

    if args.command == 'play':
        return do_play(args.target)
    if args.command == 'selftest':
        return do_selftest()
    if args.command == 'update':
        from . import updater
        return updater.update(yes=opt('yes', False), quiet=opt('quiet', False))
    if args.command == 'register':
        return do_register(opt('quiet', False))
    if args.command in ('install', 'uninstall'):
        return do_install(remove=args.command == 'uninstall')
    if args.command == 'config':
        return do_config(args)

    # 以下命令需要配置就绪
    from . import launcher, setup
    console.enable_ansi()
    console.QUIET = opt('quiet', False)
    console.VERBOSE = opt('verbose', False)

    protocol.ensure_registered()
    code = OK
    try:
        from . import updater
        updater.show()
        launcher.say()
        try:
            paths = resolve_paths(launcher, opt('library'), opt('source'))
        except settings.LibraryMissing as exc:
            setup.show_error(exc)
            return CONFIG_ERROR
        except launcher.ConfigError as exc:
            setup.show_error(exc)
            return CONFIG_ERROR
        if paths is None:
            return CONFIG_ERROR
        library, source = paths

        opts = {'limit': opt('limit'), 'dry_run': opt('dry_run', False),
                'yes': opt('yes', False)}

        if args.command == 'rebuild':
            launcher.cmd_rebuild(library)
        elif args.command == 'scrape':
            stats = launcher.cmd_scrape(library, source, opts)
            code = PARTIAL if stats['failed'] else OK
        else:
            stats, _ = launcher.cmd_all(library, source, opts)
            code = PARTIAL if stats['failed'] else OK

        # 精简模式下装饰性输出全被抑制，单独给一行结果供脚本读取
        if opt('quiet', False) and args.command != 'rebuild':
            print(f'done={stats["done"]} failed={stats["failed"]} found={stats["found"]}')
    except Exception as exc:
        # 兜底：未预料的异常也要让用户看见，不能只留一个空窗口
        import traceback
        setup.show_error(f'{type(exc).__name__}: {exc}')
        if opt('verbose', False):
            traceback.print_exc()
        else:
            launcher.say(f'  {launcher.C.GREY}{tr("加 -v 可查看完整调用栈")}'
                         f'{launcher.C.RESET}')
        code = CONFIG_ERROR
    finally:
        launcher.spin.stop()
        # 双击 EXE 时窗口会随进程一起关掉，需要停住让人看结果。
        # 装成命令行工具后是在终端里跑的，输出留在屏幕上，再等一下回车纯属碍事
        if FROZEN and not opt('yes', False) and not opt('quiet', False):
            setup.wait_exit()
    return code


if __name__ == '__main__':
    sys.exit(main())
