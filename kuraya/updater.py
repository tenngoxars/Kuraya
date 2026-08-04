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
        if quiet:
            print('updated=error')
        else:
            msg = tr('当前是 Homebrew 安装，请运行')
            print(f'  {C.RED}✕{C.RESET} {msg} '
                  f'{C.BOLD}brew upgrade kuraya{C.RESET}')
        return 1
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
        from .keys import read_key
        prompt = tr('发现新版本 v{remote}（当前 v{__version__}），'
                    '是否更新？[Y/n]',
                    remote=remote, __version__=__version__)
        print(f'  {prompt} {C.GOLD}›{C.RESET} ', end='', flush=True)
        key = read_key()
        print()
        if key not in ('y', 'Y', 'enter', ''):
            print(tr('  已取消'))
            return 0

    try:
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
        except UpdateError:
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
    elif os.name == 'nt':
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
    except UpdateError:
        raise
    except (requests.RequestException, OSError, zipfile.BadZipFile) as exc:
        raise UpdateError(tr("下载或解压失败：{kind}",
                             kind=type(exc).__name__)) from exc

    new = tmp / 'x' / 'Kuraya'
    exe = 'Kuraya.exe' if os.name == 'nt' else 'Kuraya'
    if not new.is_dir() or not (new / exe).is_file():
        raise UpdateError(tr("安装包结构不符，已放弃（现有安装未动）"))
    return new, tmp


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
        target.rename(backup)
        try:
            shutil.move(str(new_dir), str(target))
        except OSError:
            backup.rename(target)
            raise
    except OSError as exc:
        raise UpdateError(tr("替换程序目录失败：{exc}", exc=exc)) from exc
    shutil.rmtree(backup, ignore_errors=True)
