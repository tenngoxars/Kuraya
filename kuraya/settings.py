# -*- coding: utf-8 -*-
"""
配置读写。界面在首次运行时通过接口写入，用户无需手动编辑文件。
"""
import configparser
import os
import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, 'frozen', False)
PKG_DIR = Path(__file__).resolve().parent

# 界面模板随包走，因此固定在包内。挪出包外的话 pip 安装装不到它
WEB_DIR = PKG_DIR / 'web'

# 仓库检出的标志。有它说明是在源码目录里跑，配置就放在仓库根，
# 与开发时的直觉一致；没有则是被装进了 site-packages，那里不能放用户数据
_CHECKOUT = PKG_DIR.parent if (PKG_DIR.parent / 'pyproject.toml').is_file() else None


def user_config_dir(name, environ, home):
    """
    命令行安装时配置该放哪儿。参数全部显式传入，因此在任何一个平台上
    都能验证另一个平台的分支 —— Path 的行为跟着 os.name 走，
    不把这些抽出来就只能在目标系统上才测得了。
    """
    if name == 'nt':
        base = environ.get('APPDATA') or os.path.join(home, 'AppData', 'Roaming')
        return os.path.join(base, 'Kuraya')
    base = environ.get('XDG_CONFIG_HOME') or os.path.join(home, '.config')
    return os.path.join(base, 'kuraya')


def _config_dir():
    """
    配置文件放哪儿，三种情形：

      冻结的 EXE   放可执行文件旁边，用户能直接看见和编辑
      源码检出     放仓库根，开发时改起来方便
      装成命令行   放系统的用户配置目录，site-packages 不该被写入
    """
    if FROZEN:
        return Path(sys.executable).resolve().parent
    if _CHECKOUT:
        return _CHECKOUT
    return Path(user_config_dir(os.name, os.environ, os.path.expanduser('~')))


APP_DIR = _config_dir()
SETTINGS_FILE = APP_DIR / '设置.ini'

# 播放器的默认安装位置，仅用于自动探测。
# 装在其他位置时探测不到，由用户在「设置」里指定，不在此堆砌非标准路径。
if sys.platform == 'darwin':
    PLAYER_HINTS = (
        '/Applications/IINA.app/Contents/MacOS/IINA',
        '/Applications/VLC.app/Contents/MacOS/VLC',
        '/Applications/mpv.app/Contents/MacOS/mpv',
    )
    PLAYER_NAMES = ('iina', 'mpv', 'vlc')
elif os.name == 'nt':
    PLAYER_HINTS = (
        r'C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe',
        r'C:\Program Files\PotPlayer\PotPlayerMini64.exe',
        r'C:\Program Files\VideoLAN\VLC\vlc.exe',
        r'C:\Program Files (x86)\VideoLAN\VLC\vlc.exe',
        r'C:\Program Files\MPC-HC\mpc-hc64.exe',
    )
    PLAYER_NAMES = ('PotPlayerMini64.exe', 'PotPlayerMini.exe', 'vlc.exe', 'mpv.exe')
else:
    PLAYER_HINTS = ()
    PLAYER_NAMES = ('mpv', 'vlc', 'smplayer')


# 每部影片之间的间隔，避免把数据源当接口刷
DEFAULT_SLEEP = 3.0

# 视频扩展名，cleanup/gallery/menu 共用，新增格式只需改这一处
VIDEO_EXTS = ('.mp4', '.avi', '.mkv', '.wmv', '.ts', '.mov', '.m4v', '.rmvb', '.iso', '.mpg')


def _read():
    cfg = configparser.ConfigParser()
    if SETTINGS_FILE.is_file():
        try:
            cfg.read(SETTINGS_FILE, encoding='utf-8-sig')
        except Exception:
            pass
    if not cfg.has_section('路径'):
        cfg.add_section('路径')
    return cfg


def detect_player():
    """先找常见安装位置，再找 PATH 里的可执行文件"""
    for path in PLAYER_HINTS:
        if os.path.isfile(path):
            return path
    for name in PLAYER_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return ''


def load():
    """返回当前配置。缺失项以空值返回，由界面引导补全。"""
    cfg = _read()
    get = lambda k: cfg.get('路径', k, fallback='').strip()

    library = get('影片库目录')
    source = get('待整理目录')
    player = get('播放器')

    return {
        'library': library,
        'source': source or (str(Path(library) / '待整理') if library else ''),
        'player': player,
        'sleep': _sleep(cfg),
        'configured': bool(library),
        # 是否已询问过加入 PATH，避免每次启动重复打扰
        'path_asked': cfg.get('状态', '已询问PATH', fallback='').strip(),
    }


def _sleep(cfg):
    """写错了不该让整个程序起不来，按默认值走"""
    try:
        return max(0.0, cfg.getfloat('刮削', '间隔秒数', fallback=DEFAULT_SLEEP))
    except ValueError:
        return DEFAULT_SLEEP


def save(library=None, source=None, player=None, path_asked=None):
    """写入配置。传 None 的项保持原值"""
    cfg = _read()
    if library is not None:
        cfg.set('路径', '影片库目录', library)
    if source is not None:
        cfg.set('路径', '待整理目录', source)
    if player is not None:
        cfg.set('路径', '播放器', player)
    if path_asked is not None:
        if not cfg.has_section('状态'):
            cfg.add_section('状态')
        cfg.set('状态', '已询问PATH', path_asked)

    # 装成命令行工具时配置在 ~/.config/kuraya 之类的位置，首次运行时并不存在
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as fp:
        fp.write('# 由程序自动生成，也可手动编辑\n')
        cfg.write(fp)

    return load()


class LibraryMissing(Exception):
    """配置指向的影片库不存在"""


def ensure_dirs(library, source, create_library=False):
    """
    准备好影片库与待整理目录。

    影片库默认不自动创建：路径写错、盘符变化或移动硬盘未连接时，
    静默建一个空目录会让人误以为收藏丢失，必须明确报错。
    仅在用户刚亲自选定目录时（create_library=True）才允许创建。
    """
    lib = Path(library).expanduser()
    if not lib.is_dir():
        if not create_library:
            raise LibraryMissing(
                f'影片库目录不存在：{lib}\n'
                f'    可能是磁盘未连接、盘符变化或路径被移动。\n'
                f'    确认无误后可修改「设置.ini」中的影片库目录。')
        lib.mkdir(parents=True, exist_ok=True)

    # 待整理在影片库内，刮削后可能被清空删除，每次补建
    src = Path(source).expanduser() if source else lib / '待整理'
    src.mkdir(parents=True, exist_ok=True)
    return lib.resolve(), src.resolve()
