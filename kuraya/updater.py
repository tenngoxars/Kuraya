# -*- coding: utf-8 -*-
"""
更新检查与自更新：启动时查询 GitHub 是否有新版本，有则在 CLI 里提示；
`kuraya update` 下载最新包并替换当前安装。

设计约束：
- 检查 24 小时最多请求一次，其余时间复用上次结果（GitHub 未认证 API 限流 60 次/小时）；
- 网络失败、解析失败一律静默并缓存，绝不让检查拖慢或打断主流程；
- 替换分两种形态。mac / Linux 整目录换：旧目录改名 .old → 新目录就位 → 删旧。
  Windows 换不了目录 —— 系统不许重命名含有已打开文件的目录，而 exe 与 _internal
  下的 dll 正被本进程加载；但它允许重命名运行中的 exe 与已加载的 dll 本身，
  于是改用逐个文件替换（见 _replace_in_place）。两种形态都是要么全成、
  要么现有安装分毫未动；
- 让位的旧文件本进程删不掉（还加载着），改名留到下次启动由 sweep_old() 清；
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

from . import __version__, console, settings
from .console import C, enable_ansi
from .i18n import tr
from .settings import FROZEN

REPO = 'tenngoxars/Kuraya'
TAP = 'tenngoxars/homebrew-tap'
RELEASES_API = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES_URL = f'https://github.com/{REPO}/releases/latest'

HEADERS = {'Accept': 'application/vnd.github+json'}

# 检查间隔：一天一次；失败缓存只顶 1 小时，避免网络恢复后长时间不提示
CHECK_INTERVAL = 24 * 3600
FAIL_INTERVAL = 3600
TIMEOUT = (3, 5)          # 更新提示不值得让人等，超时从严
DOWNLOAD_TIMEOUT = (10, 60)  # 安装包下载放宽
ERROR_LINES = 6           # brew 失败时透出的输出行数（够放下 Error 与解法）
DOWNLOAD_TRIES = 3        # 含首次；网络抖动重试
RETRY_BACKOFF = (1, 3)    # 每次重试前的等待秒数，用尽后按最后一个值等
# 就地替换时给旧文件加的后缀。运行中的进程删不掉自己加载的文件，
# 只能先改名，留到下次启动时删 —— 那时谁也没加载它们
OLD_SUFFIX = '.kuraya-old'

_shown = False  # 同一进程只在主流程开头提示一次

# 本进程是否已经把程序文件换成了新版：磁盘上是新版，内存里跑的还是旧版，
# 菜单据此重开新版再退出
_restart_needed = False


def restart_needed():
    """本次运行是否已换过程序文件（换过就得重启才生效）"""
    return _restart_needed


def relaunch():
    """
    重开新版，成功返回 True（调用方随即退出本进程）。

    只在 Windows 上做：那里的程序多是双击启动，CREATE_NEW_CONSOLE 能给新进程
    一个自己的窗口，用户看得见。其余平台从终端或壳 app 启动，脱离会话重开只会
    得到一个看不见的进程，不如老实提示用户自己重启。
    """
    if sys.platform != 'win32' or not FROZEN:
        return False
    try:
        subprocess.Popen([sys.executable],
                         creationflags=getattr(subprocess,
                                               'CREATE_NEW_CONSOLE', 0))
        return True
    except OSError:
        return False


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
    if version:
        settings.save_update_state(str(int(time.time())), version)
    else:
        # 失败也写缓存，但把 checked 倒拨到只剩 1 小时有效期：
        # 离线时避免每次启动都等超时，网络恢复后不至于一整天不提示
        settings.save_update_state(
            str(int(time.time()) - CHECK_INTERVAL + FAIL_INTERVAL), '')
    return version or None


def text():
    """有新版本时返回提示文案，否则返回空串"""
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
    """交互主流程开头输出一次更新提示；非交互、quiet 或已提示过则跳过"""
    global _shown
    if _shown:
        return
    # 非交互时一并跳过：这行提示没人看，而 text() 要联网查版本，
    # 平白给定时任务和脚本调用添一次网络等待
    if console.QUIET or not console.interactive():
        return
    notice = text()
    if notice:
        _shown = True
        console.say(notice)


def sweep_old(target=None):
    """
    清掉上次就地替换留下的旧文件。

    替换时运行中的进程占着自己加载的文件，删不掉，只能改名成 OLD_SUFFIX
    留在原地；这一刻是新进程，没人加载它们，删得掉。启动时扫一遍即可，
    失败一律忽略 —— 残留只占盘，不影响使用，不值得打断启动。
    """
    if not FROZEN:
        return
    root = Path(target) if target else Path(sys.executable).parent
    try:
        stale = list(root.rglob(f'*{OLD_SUFFIX}'))
    except OSError:
        return
    for path in stale:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()
        except OSError:
            pass


# ---------- 自更新 ----------
def update(yes=False, quiet=False):
    """`kuraya update`：下载并安装最新版。返回进程退出码"""
    # 打包后 PYTHONIOENCODING 不一定生效，中文提示须显式指定输出编码
    console.ensure_utf8()
    enable_ansi()
    global _restart_needed

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

    if not quiet:
        print(f'  {C.GOLD}◈{C.RESET} {tr("正在检查更新...")}')
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
        if not quiet:
            print(f'  {C.GOLD}◈{C.RESET} '
                  f'{tr("正在下载 v{remote}...", remote=remote)}')
        new, tmp = _download(remote)
        if not quiet:
            print(f'  {C.GOLD}◈{C.RESET} {tr("正在替换程序目录...")}')
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

        # 再换程序本体；失败时回滚已就位的 app
        try:
            # Windows 上目录改不了名（里面的 exe 与 dll 正被本进程加载），
            # 只能逐个文件换；其余平台没有这道限制，整目录替换更快更干净
            if sys.platform == 'win32':
                _replace_in_place(new, target)
            else:
                _replace(new, target)
        except UpdateError:
            if app_old is not None:
                shutil.rmtree(app_target, ignore_errors=True)
                app_old.rename(app_target)
            raise
        _restart_needed = True
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
        print(f'  {C.RED}✕{C.RESET} {message}')


def _brew_update(yes=False, quiet=False):
    """
    Homebrew 安装的升级：委托 brew upgrade（保持 brew 状态一致）。
    返回进程退出码。
    """
    enable_ansi()

    if not (yes or quiet):
        prompt = tr('将调用 brew 更新 kuraya（先刷新索引再升级），'
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

    ok, version, already, err = _run_brew_upgrade(quiet=quiet)
    if quiet:
        # 稳定的一行给脚本判断，brew 的报错走 stderr 不污染它
        if err:
            print(err, file=sys.stderr)
        print(f'updated={version or ("none" if already else "error")}')
        return 0 if ok else 1

    if not ok:
        if err:
            # brew 的报错自带解法（如未信任 tap 会给出 brew trust 命令），
            # 原样透出；吞掉再让用户手动重跑一遍等于没给诊断
            print(f'  {C.RED}✕{C.RESET} {tr("brew upgrade 执行失败：")}')
            for line in err.splitlines():
                print(f'    {C.GREY}{line}{C.RESET}')
        else:
            fail_msg = tr('brew upgrade 执行失败，请手动运行该命令查看原因')
            print(f'  {C.RED}✕{C.RESET} {fail_msg}')
        return 1
    if already:
        latest_msg = tr('已是最新版本 v{__version__}', __version__=__version__)
        print(f'  {C.GREEN}✓{C.RESET} {latest_msg}')
        return 0
    done_msg = tr('已更新到 v{version}，重启 kuraya 后生效', version=version)
    print(f'  {C.GREEN}✓{C.RESET} {done_msg}')
    return 0


def _run_brew_upgrade(quiet=False):
    """
    执行 brew upgrade kuraya。返回 (是否成功, 新版本号, 是否本就最新, 报错)。
    新版本号从 brew list --versions 读取。
    失败时带回 brew 输出的末尾几行：brew 的报错本身就是诊断（未信任 tap、
    权限、网络等各有解法），不在这里匹配错误模式——brew 措辞一变就失效。
    必须**先刷新 tap 再 upgrade**：brew 不自动刷新 tap 索引，本地
    formula 停在旧版时 upgrade 会「成功」装到旧 formula 的版本（永远
    追不上最新）；全量 brew update 会拉 homebrew-core 等所有仓库
    （国内网络经常卡在 Updating Homebrew），因此只 git pull kuraya
    所在的 tap，并禁用 upgrade 自带的自动更新。
    「已是最新」的判定兼容新旧 brew 措辞：up-to-date / already installed
    （实测现代 brew 输出 Warning: ... already installed）。
    """

    def upgrade():
        env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE='1')
        try:
            return subprocess.run(['brew', 'upgrade', 'kuraya'],
                                  capture_output=True, text=True,
                                  env=env, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            return None

    def tap_update():
        """刷新 kuraya 所在 tap：brew tap-update 各版本命令集不同，
        直接 git pull tap 仓库目录，所有版本通用"""
        try:
            repo = subprocess.run(['brew', '--repository', TAP],
                                  capture_output=True, text=True,
                                  timeout=30)
            if repo.returncode != 0:
                return False
            path = repo.stdout.strip()
            if not path:
                return False
            pull = subprocess.run(['git', '-C', path, 'pull'],
                                  capture_output=True, text=True,
                                  timeout=120)
            return pull.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    if not tap_update() and not quiet:
        # formula 停在旧版时 upgrade 仍会「成功」装旧版，须让用户知情
        print(f'  {C.GREY}{tr("tap 刷新失败，可能不是最新版本")}{C.RESET}')
    result = upgrade()
    if result is None:
        return False, '', False, ''
    output = (result.stdout or '') + (result.stderr or '')
    if result.returncode != 0:
        # brew 把 Error 放在最后，取末尾即可；空行剔掉免得刷屏
        lines = [ln for ln in output.splitlines() if ln.strip()]
        return False, '', False, '\n'.join(lines[-ERROR_LINES:])
    if 'up-to-date' in output or 'already installed' in output:
        return True, '', True, ''

    version = ''
    try:
        listed = subprocess.run(['brew', 'list', '--versions', 'kuraya'],
                                capture_output=True, text=True)
        version = listed.stdout.strip().split()[-1]
    except (OSError, IndexError):
        version = ''
    return True, version, False, ''


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


def _fetch(url, zip_path):
    """
    下载安装包到 zip_path。成功返回 None，失败返回最后一次异常。

    网络类失败必须重试：几十 MB 的单流传输中途断一次很常见（连 GitHub
    尤其如此），一次卡顿不该让整个更新失败。非 200 不重试——资产不存在
    重试多少次结果都一样，直接抛 UpdateError 让调用方原样报出来。
    """
    failed = None
    for attempt in range(DOWNLOAD_TRIES):
        try:
            with requests.get(url, stream=True,
                              timeout=DOWNLOAD_TIMEOUT) as resp:
                if resp.status_code != 200:
                    raise UpdateError(tr("下载失败：{status} {url}",
                                         status=resp.status_code, url=url))
                with open(zip_path, 'wb') as fp:
                    for chunk in resp.iter_content(65536):
                        fp.write(chunk)
            return None
        # requests 的异常全是 OSError 子类，磁盘写入失败也一并兜住
        except OSError as exc:
            failed = exc
            if attempt < DOWNLOAD_TRIES - 1:
                time.sleep(RETRY_BACKOFF[min(attempt,
                                             len(RETRY_BACKOFF) - 1)])
    return failed


def _download(version):
    """
    下载并解压指定版本的安装包，返回 (程序目录, 临时根)。
    结构不符视为失败（抛 UpdateError），现有安装不受影响。
    """
    url = _asset_url(version)
    tmp = Path(tempfile.mkdtemp(prefix='kuraya-update-'))
    zip_path = tmp / 'kuraya.zip'
    failed = _fetch(url, zip_path)
    if failed is not None:
        # 失败就把临时目录收掉：留着只是几十 MB 的半截 zip，谁也用不上
        shutil.rmtree(tmp, ignore_errors=True)
        raise UpdateError(
            tr('下载失败（已重试 {tries} 次）：{kind}',
               tries=DOWNLOAD_TRIES - 1, kind=type(failed).__name__)
            + tr('（网络不稳或连不上 GitHub：可设 HTTPS_PROXY 后重试，'
                 '或到 {url} 手动下载解压）', url=RELEASES_URL)) from failed
    try:
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
    except (OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise UpdateError(tr('解压失败：{kind}',
                             kind=type(exc).__name__)) from exc

    new = tmp / 'x' / 'Kuraya'
    exe = 'Kuraya.exe' if sys.platform == 'win32' else 'Kuraya'
    if not new.is_dir() or not (new / exe).is_file():
        shutil.rmtree(tmp, ignore_errors=True)
        raise UpdateError(tr("安装包结构不符，已放弃（现有安装未动）"))
    if os.name != 'nt':
        # 双保险：即使 zip 没带权限位，可执行文件也必须有 +x
        exe_path = new / exe
        mode = exe_path.stat().st_mode
        if not mode & 0o111:
            exe_path.chmod(mode | 0o111)
    return new, tmp


def _replace_in_place(new_dir, target):
    """
    逐个文件替换程序目录的内容，不动目录本身。

    Windows 不让重命名含有已打开文件的目录 —— 而 Kuraya.exe 和 _internal 下的
    dll 正被本进程加载，所以整目录替换在 Windows 上必然失败。但同一个系统允许
    重命名正在运行的 exe 与已加载的 dll 本身（实测：exe 与 python313.dll 都能
    改名，只有 _internal 目录被拒）。于是换个粒度：旧文件改名让位，新文件就位，
    当场换完，不必等进程退出，也就不需要外部脚本。

    旧文件改名成 OLD_SUFFIX 留在原地，下次启动由 sweep_old() 删掉 —— 本进程
    删不掉自己加载的文件。新版没有的旧文件同样改名，等价于整目录替换的裁剪。

    任何一步失败就整体回滚：改过名的改回来，搬进来的删掉。要么全成，
    要么现有安装分毫未动 —— 半新半旧的程序目录是启动不起来的。
    """
    new_dir, target = Path(new_dir), Path(target)
    wanted = {path.relative_to(new_dir) for path in new_dir.rglob('*')
              if path.is_file()}
    # 旧目录里新版没有的文件也要让位，否则上一版的残留会一直留在目录里
    try:
        obsolete = {path.relative_to(target) for path in target.rglob('*')
                    if path.is_file() and not path.name.endswith(OLD_SUFFIX)
                    and path.relative_to(target) not in wanted}
    except OSError as exc:
        raise UpdateError(tr('读取程序目录失败：{exc}', exc=exc)) from exc

    renamed = []        # [(旧路径, 让位后的路径)]
    moved = []          # 已就位的新文件
    try:
        for relative in sorted(wanted | obsolete):
            current = target / relative
            if current.exists():
                aside = _aside(current)
                current.rename(aside)
                renamed.append((current, aside))
            if relative in wanted:
                current.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(new_dir / relative), str(current))
                moved.append(current)
    except OSError as exc:
        _rollback(renamed, moved)
        hint = tr('（多为安全软件拦截或目录权限问题，'
                  '请将程序目录加入安全软件白名单后重试）')
        raise UpdateError(tr('替换程序文件失败：{exc}', exc=exc) + hint,
                          winerror=getattr(exc, 'winerror', None)) from exc


def _aside(path):
    """
    给旧文件挑一个让位的名字。

    上次更新留下的同名让位文件可能还被本进程加载着、删不掉（同一次运行里连更
    两版就会撞上）。删不掉就往后排一个，别让这一次更新卡在上一次的残留上。
    """
    aside = path.with_name(path.name + OLD_SUFFIX)
    attempt = 0
    while aside.exists():
        try:
            aside.unlink()
        except OSError:
            attempt += 1
            aside = path.with_name(f'{path.name}.{attempt}{OLD_SUFFIX}')
    return aside


def _rollback(renamed, moved):
    """把 _replace_in_place 做过的改动退回去。回滚本身失败无处可退，只能忽略"""
    for path in moved:
        try:
            path.unlink()
        except OSError:
            pass
    for current, aside in reversed(renamed):
        try:
            aside.rename(current)
        except OSError:
            pass


def _replace(new_dir, target):
    """
    整目录替换：旧目录改名 .old → 新目录就位 → 删除旧目录，就位失败恢复旧目录。

    只走 mac / Linux —— 那里没人锁着运行中的程序目录，一次改名就换完。
    Windows 改不动目录，走 _replace_in_place()。
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
        raise UpdateError(tr('替换程序目录失败：{exc}', exc=exc)) from exc
    shutil.rmtree(backup, ignore_errors=True)
