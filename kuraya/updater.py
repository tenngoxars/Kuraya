# -*- coding: utf-8 -*-
"""
更新检查与自更新：启动时查询 GitHub 是否有新版本，有则在 CLI 里提示；
`kuraya update` 下载最新包并替换当前安装。

设计约束：
- 检查 24 小时最多请求一次，其余时间复用上次结果（GitHub 未认证 API 限流 60 次/小时）；
- 网络失败、解析失败一律静默并缓存，绝不让检查拖慢或打断主流程；
- 替换顺序：旧目录改名 .old → 新目录就位 → 删除旧目录，中途失败恢复旧目录。
  Windows 上运行中的 exe 占着旧目录删不掉，残留的 .old 留待下次更新清理；
- brew 安装由 brew 管理不自行替换，提示用 brew upgrade。
"""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import requests

from . import settings
from .i18n import tr
from .settings import FROZEN

REPO = 'tenngoxars/Kuraya'
RELEASES_API = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES_URL = f'https://github.com/{REPO}/releases/latest'

HEADERS = {'Accept': 'application/vnd.github+json'}

# 检查间隔：一天一次
CHECK_INTERVAL = 24 * 3600
TIMEOUT = (3, 5)          # 更新提示不值得让人等，超时从严
DOWNLOAD_TIMEOUT = (10, 60)  # 安装包下载放宽

_shown = False  # 同一进程只在主流程开头提示一次


class UpdateError(Exception):
    """更新失败。报错但不动现有安装"""

    def __init__(self, message, winerror=None):
        super().__init__(message)
        self.winerror = winerror


def is_newer(remote, current):
    """
    remote 是否比 current 新。版本为点分数字段，逐段比较，
    容忍 v 前缀；非数字段按字符串比较兜底，0.10.0 > 0.9.9。
    """
    a, b = _parts(remote), _parts(current)
    for x, y in zip(a, b):
        if isinstance(x, int) and isinstance(y, int):
            if x != y:
                return x > y
        elif str(x) != str(y):
            return str(x) > str(y)
    return len(a) > len(b)


def _parts(version):
    return [int(seg) if seg.isdigit() else seg
            for seg in version.strip().lstrip('vV').split('.')]


def latest(force=False):
    """
    返回 GitHub 上最新版本号（不带 v 前缀），拿不到返回 None。
    24 小时内的结果直接复用上次缓存；force 时（主动更新）总是重新请求；
    检查失败也写缓存，避免离线时每次启动都等超时。
    """
    state = settings.update_state()
    if not force and state['checked']:
        try:
            fresh = time.time() - float(state['checked']) < CHECK_INTERVAL
        except ValueError:
            fresh = False
        if fresh:
            return state['latest'] or None

    tag = ''
    try:
        resp = requests.get(RELEASES_API, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            tag = resp.json().get('tag_name', '')
    except (requests.RequestException, ValueError):
        pass
    version = tag.strip().lstrip('vV') if isinstance(tag, str) else ''
    settings.save_update_state(str(int(time.time())), version)
    return version or None


def text():
    """有新版本时返回提示文案，否则返回空串"""
    from . import __version__
    from .launcher import C

    remote = latest()
    if not remote or not is_newer(remote, __version__):
        return ''
    notice_new = tr('发现新版本 v{remote}', remote=remote)
    notice_cur = tr('（当前 v{__version__}）', __version__=__version__)
    notice_act = tr('更新：菜单选「更新」，或运行')
    notice_url = tr('详情：')
    return (f'  {C.GOLD}◈{C.RESET} {C.GREEN}{notice_new}{C.RESET}'
            f'{C.GREY}{notice_cur}{C.RESET}\n'
            f'  {C.GREY}{notice_act}{C.RESET} '
            f'{C.BOLD}kuraya update{C.RESET}\n'
            f'  {C.GREY}{notice_url}{RELEASES_URL}{C.RESET}')


def show():
    """主流程命令开头输出一次更新提示；quiet 或已提示过则跳过"""
    global _shown
    if _shown:
        return
    from . import launcher
    if launcher.QUIET:
        return
    notice = text()
    if notice:
        _shown = True
        launcher.say(notice)


# ---------- 自更新 ----------
def update(yes=False, quiet=False):
    """`kuraya update`：下载并安装最新版。返回进程退出码"""
    # 打包后 PYTHONIOENCODING 不一定生效，中文提示须显式指定输出编码
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass
    from . import __version__
    from .launcher import C, enable_ansi
    enable_ansi()

    if _brew_install():
        # brew 维护自己的版本记录（Cellar 目录、formula sha256），
        # 直接替换文件会让 brew 状态错乱，委托 brew upgrade 保持一致
        return _brew_update(yes=yes, quiet=quiet)
    if not FROZEN:
        if quiet:
            print('updated=error')
        else:
            msg1 = tr('源码或 pip 安装无法自更新。')
            msg2 = tr('源码运行请 git pull；pipx 安装请运行')
            print(f'  {C.RED}✕{C.RESET} {msg1}\n'
                  f'  {msg2} {C.BOLD}pipx upgrade kuraya{C.RESET}')
        return 1

    remote = latest(force=True)
    if remote is None:
        _finish(tr("无法检查更新（网络或服务不可用）"), quiet)
        return 1
    if not is_newer(remote, __version__):
        if quiet:
            print('updated=none')
        else:
            latest_msg = tr('已是最新版本 v{__version__}', __version__=__version__)
            print(f'  {C.GREEN}✓{C.RESET} {latest_msg}')
        return 0

    if not (yes or quiet):
        prompt = tr('发现新版本 v{remote}（当前 v{__version__}），'
                    '是否更新？[Y/n]',
                    remote=remote, __version__=__version__)
        # 用 input() 而非 raw 读键：终端原生回显按键，
        # raw 模式的手动回显在部分终端（Warp 等）不可见
        try:
            answer = input(f'  {prompt} {C.GOLD}›{C.RESET} ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 0
        if answer not in ('', 'y', 'yes'):
            print(tr('  已取消'))
            return 0

    try:
        # Windows 上若程序自身的 CWD 在目标目录内，目录重命名会被拒绝
        # （WinError 5），先切到临时目录消除自身占用
        os.chdir(tempfile.gettempdir())
        new, tmp = _download(remote)
        target = Path(sys.executable).parent
        app_src = tmp / 'x' / 'Kuraya.app'
        app_target = target.parent / 'Kuraya.app'
        app_old = None

        # 先换壳 app：失败时主目录未动，整体保持一致
        if app_src.is_dir():
            if app_target.exists():
                app_old = app_target.parent / 'Kuraya.old'
                shutil.rmtree(app_old, ignore_errors=True)
                app_target.rename(app_old)
            try:
                shutil.move(str(app_src), str(app_target))
            except OSError as exc:
                if app_old is not None:
                    app_old.rename(app_target)
                raise UpdateError(tr('替换程序目录失败：{exc}', exc=exc)) from exc

        # 再换主目录；失败时回滚已就位的 app
        try:
            _replace(new, target)
        except UpdateError as exc:
            if sys.platform == 'win32' and getattr(exc, 'winerror', None) == 5:
                # 安全软件拦截程序自修改：安排独立进程在程序退出后替换
                if _replace_later(new, target):
                    if app_old is not None:
                        shutil.rmtree(app_target, ignore_errors=True)
                        app_old.rename(app_target)
                    if quiet:
                        print(f'updated={remote}')
                    else:
                        later_msg = tr('安全软件拦截了直接替换，'
                                       '已安排程序退出后自动完成更新')
                        print(f'  {C.GOLD}◈{C.RESET} {later_msg}')
                        print(f'  {C.GREY}{tr("请退出本程序，稍候片刻再重新打开")}'
                              f'{C.RESET}')
                        fallback = tr('若重新打开后版本未变，请运行安装命令：'
                                      'irm https://raw.githubusercontent.com/'
                                      'tenngoxars/Kuraya/main/install.ps1 | iex')
                        print(f'  {C.GREY}{fallback}{C.RESET}')
                    return 0
            if app_old is not None:
                shutil.rmtree(app_target, ignore_errors=True)
                app_old.rename(app_target)
            raise
        if app_old is not None:
            shutil.rmtree(app_old, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
    except UpdateError as exc:
        _finish(str(exc), quiet)
        return 1

    if quiet:
        print(f'updated={remote}')
    else:
        done_msg = tr('已更新到 v{remote}，重启 kuraya 后生效', remote=remote)
        print(f'  {C.GREEN}✓{C.RESET} {done_msg}')
    return 0


def _finish(message, quiet):
    """更新失败的收尾输出。quiet 模式给一行稳定格式供脚本判断"""
    if quiet:
        print('updated=error')
    else:
        from .launcher import C
        print(f'  {C.RED}✕{C.RESET} {message}')


def _brew_update(yes=False, quiet=False):
    """
    Homebrew 安装的升级：委托 brew upgrade（保持 brew 状态一致）。
    返回进程退出码。
    """
    from .launcher import C, enable_ansi
    enable_ansi()

    if not (yes or quiet):
        prompt = tr('将调用 brew upgrade kuraya（保持 Homebrew 状态一致），'
                    '是否继续？[Y/n]')
        try:
            answer = input(f'  {prompt} {C.GOLD}›{C.RESET} ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 0
        if answer not in ('', 'y', 'yes'):
            print(tr('  已取消'))
            return 0

    if not quiet:
        print(f'  {C.GREY}{tr("检测到 Homebrew 安装，正在调用 brew upgrade kuraya……")}'
              f'{C.RESET}')

    ok, version, already = _run_brew_upgrade()
    if quiet:
        print(f'updated={version or ("none" if already else "error")}')
        return 0 if ok else 1

    if not ok:
        fail_msg = tr('brew upgrade 执行失败，请手动运行该命令查看原因')
        print(f'  {C.RED}✕{C.RESET} {fail_msg}')
        return 1
    if already:
        from . import __version__
        latest_msg = tr('已是最新版本 v{__version__}', __version__=__version__)
        print(f'  {C.GREEN}✓{C.RESET} {latest_msg}')
        return 0
    done_msg = tr('已更新到 v{version}，重启 kuraya 后生效', version=version)
    print(f'  {C.GREEN}✓{C.RESET} {done_msg}')
    return 0


def _run_brew_upgrade():
    """
    执行 brew upgrade kuraya。返回 (是否成功, 新版本号, 是否本就最新)。
    新版本号从 brew list --versions 读取。
    """
    try:
        result = subprocess.run(['brew', 'upgrade', 'kuraya'],
                                capture_output=True, text=True)
        output = (result.stdout or '') + (result.stderr or '')
    except OSError as exc:
        return False, '', False
    if result.returncode != 0:
        return False, '', False

    already = 'up-to-date' in output
    version = ''
    if not already:
        try:
            listed = subprocess.run(['brew', 'list', '--versions', 'kuraya'],
                                    capture_output=True, text=True)
            version = listed.stdout.strip().split()[-1]
        except (OSError, IndexError):
            version = ''
    return True, version, already


def _brew_install():
    """Homebrew 的 Cellar 布局：<prefix>/Cellar/kuraya/<ver>/libexec/..."""
    if sys.platform != 'darwin':
        return False
    parts = Path(sys.executable).resolve().parts
    return 'Cellar' in parts and 'kuraya' in parts


def _asset_url(version):
    """按平台与架构拼安装包地址。发行版没有的架构组合直接报错"""
    machine = platform.machine().lower()
    if sys.platform == 'darwin':
        if machine not in ('arm64', 'aarch64'):
            raise UpdateError(tr("官方包仅支持 Apple Silicon（GitHub 已无 "
                                 'Intel 构建机），请改用 brew 安装'))
        os_arch = 'mac-arm64'
    elif sys.platform == 'win32':
        os_arch = 'win-x64'
    else:
        if machine not in ('x86_64', 'amd64'):
            raise UpdateError(tr("暂无 {machine} 架构的官方包", machine=machine))
        os_arch = 'linux-x86_64'
    return (f'https://github.com/{REPO}/releases/download/v{version}/'
            f'Kuraya-{version}-{os_arch}.zip')


def _download(version):
    """
    下载并解压指定版本的安装包，返回 (程序目录, 临时根)。
    结构不符视为失败（抛 UpdateError），现有安装不受影响。
    """
    url = _asset_url(version)
    tmp = Path(tempfile.mkdtemp(prefix='kuraya-update-'))
    zip_path = tmp / 'kuraya.zip'
    try:
        with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
            if resp.status_code != 200:
                raise UpdateError(tr("下载失败：{status} {url}",
                                     status=resp.status_code, url=url))
            with open(zip_path, 'wb') as fp:
                for chunk in resp.iter_content(65536):
                    fp.write(chunk)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp / 'x')
            # zipfile 不保留 Unix 权限位（unzip 命令会），
            # 从 external_attr 恢复，否则可执行文件失去 +x 无法运行
            for info in zf.infolist():
                perm = (info.external_attr >> 16) & 0o7777
                if perm:
                    try:
                        (tmp / 'x' / info.filename).chmod(perm)
                    except OSError:
                        pass
    except UpdateError:
        raise
    except (requests.RequestException, OSError, zipfile.BadZipFile) as exc:
        raise UpdateError(tr("下载或解压失败：{kind}",
                             kind=type(exc).__name__)) from exc

    new = tmp / 'x' / 'Kuraya'
    exe = 'Kuraya.exe' if sys.platform == 'win32' else 'Kuraya'
    if not new.is_dir() or not (new / exe).is_file():
        raise UpdateError(tr("安装包结构不符，已放弃（现有安装未动）"))
    if os.name != 'nt':
        # 双保险：即使 zip 没带权限位，可执行文件也必须有 +x
        exe_path = new / exe
        mode = exe_path.stat().st_mode
        if not mode & 0o111:
            exe_path.chmod(mode | 0o111)
    return new, tmp


def _replace_later(new_dir, target):
    """
    延迟替换：安全软件拦截程序自修改时，写一个独立 PowerShell 脚本，
    由它在程序退出后完成替换（独立进程通常不被行为检测拦截）。
    返回是否已安排。临时目录保留给脚本使用，脚本完成后自行清理。
    """
    tmp = new_dir.parent.parent
    script = tmp / 'replace.ps1'

    def ps_str(path):
        return str(path).replace("'", "''")

    ps = f"""$ErrorActionPreference = 'Stop'
$log = '{ps_str(tmp / 'update.log')}'
Start-Sleep -Seconds 3
$target = '{ps_str(target)}'
$new = '{ps_str(new_dir)}'
$old = "$target.old"
try {{
  if (Test-Path -LiteralPath $old) {{ Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue }}
  Rename-Item -LiteralPath $target -NewName 'Kuraya.old' -ErrorAction Stop
  Move-Item -LiteralPath $new -Destination $target -ErrorAction Stop
  Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue
  Set-Content -LiteralPath $log -Value 'OK' -Encoding UTF8
  Remove-Item -LiteralPath '{ps_str(tmp)}' -Recurse -Force -ErrorAction SilentlyContinue
}} catch {{
  if (Test-Path -LiteralPath $old) {{
    if (-not (Test-Path -LiteralPath $target)) {{
      Rename-Item -LiteralPath $old -NewName 'Kuraya' -ErrorAction SilentlyContinue
    }}
  }}
  Set-Content -LiteralPath $log -Value ('FAIL: ' + $_.Exception.Message) -Encoding UTF8
}}
"""
    script.write_text(ps, encoding='utf-8-sig')
    log = tmp / 'update.log'
    try:
        log.write_text('PENDING', encoding='utf-8')
    except OSError:
        pass
    try:
        subprocess.Popen(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
             '-WindowStyle', 'Hidden', '-File', str(script)])
        return True
    except OSError:
        return False


def _replace(new_dir, target):
    """
    原子替换目录：旧目录改名 .old → 新目录就位 → 删除旧目录。
    就位失败时恢复旧目录。Windows 上运行中的 exe 占着旧目录，
    删除会失败，残留的 .old 留待下次更新时清理（不影响使用）。
    """
    backup = target.parent / (target.name + '.old')
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    try:
        # Windows 上目录可能被杀软/资源管理器短暂占用，重试几次再放弃
        for attempt in range(6):
            try:
                target.rename(backup)
                break
            except OSError:
                if attempt == 5:
                    raise
                time.sleep(0.8)
        try:
            shutil.move(str(new_dir), str(target))
        except OSError:
            backup.rename(target)
            raise
    except OSError as exc:
        if sys.platform == 'win32':
            if getattr(exc, 'winerror', None) == 5:
                hint = tr('（拒绝访问：多为安全软件拦截或目录权限问题，'
                          '请将程序目录加入安全软件白名单，'
                          '确认没有窗口停留在程序目录内后重试）')
            else:
                hint = tr('（Windows 常见原因：有窗口停留在程序目录内，'
                          '或安全软件正在扫描，关闭后重试）')
        else:
            hint = ''
        raise UpdateError(tr('替换程序目录失败：{exc}', exc=exc) + hint,
                          winerror=getattr(exc, 'winerror', None)) from exc
    shutil.rmtree(backup, ignore_errors=True)
