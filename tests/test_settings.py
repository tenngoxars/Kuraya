# -*- coding: utf-8 -*-
"""
配置读写。

    python -m unittest discover tests
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kuraya import media, settings


class VideoExts(unittest.TestCase):
    """视频扩展名唯一来源（曾分叉成两份，.flv/.mpeg 被清理器漏认
    导致整目录被误删）"""

    def test_single_source_from_engine(self):
        self.assertIs(settings.VIDEO_EXTS, media.VIDEO_EXTS)
        self.assertIn('.flv', settings.VIDEO_EXTS)
        self.assertIn('.mpeg', settings.VIDEO_EXTS)


class UserConfigDir(unittest.TestCase):
    """
    命令行安装时的配置位置。三个平台的分支都在这里断言 ——
    Path 的行为跟着 os.name 走，在 Windows 上模拟不出 PosixPath，
    所以判定逻辑必须是不碰 Path 的纯函数，否则 mac 那一支只能上机才测得了
    """

    def where(self, name, environ=None, home='/Users/me'):
        got = settings.user_config_dir(name, environ or {}, home)
        return got.replace('\\', '/')

    def test_macos_default(self):
        self.assertEqual(self.where('posix'), '/Users/me/.config/kuraya')

    def test_linux_default(self):
        self.assertEqual(self.where('posix'), '/Users/me/.config/kuraya')

    def test_xdg_respected(self):
        self.assertEqual(
            self.where('posix', {'XDG_CONFIG_HOME': '/Users/me/somewhere'}),
            '/Users/me/somewhere/kuraya')

    def test_windows_uses_appdata(self):
        self.assertEqual(
            self.where('nt', {'APPDATA': 'C:/Users/me/AppData/Roaming'}),
            'C:/Users/me/AppData/Roaming/Kuraya')

    def test_windows_without_appdata(self):
        self.assertEqual(self.where('nt', home='C:/Users/me'),
                         'C:/Users/me/AppData/Roaming/Kuraya')

    def test_empty_env_var_ignored(self):
        """环境变量存在但为空串时不能当成有效路径用"""
        self.assertEqual(self.where('posix', {'XDG_CONFIG_HOME': ''}),
                         '/Users/me/.config/kuraya')


class ConfigLocation(unittest.TestCase):
    """装成命令行工具后配置在用户目录，首次运行时那个目录还不存在"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_creates_missing_parent(self):
        target = self.home / '.config' / 'kuraya' / '设置.ini'
        with mock.patch.object(settings, 'SETTINGS_FILE', target):
            settings.save(library=str(self.home))
        self.assertTrue(target.is_file())

    def test_nested_parents_created(self):
        target = self.home / 'a' / 'b' / 'c' / '设置.ini'
        with mock.patch.object(settings, 'SETTINGS_FILE', target):
            settings.save(library=str(self.home))
        self.assertTrue(target.is_file())


class MigrateLegacyConfig(unittest.TestCase):
    """旧版打包把配置放可执行文件旁（升级即丢），新版本发现后搬进用户目录"""

    def test_moves_legacy_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / 'app' / '设置.ini'
            legacy.parent.mkdir()
            legacy.write_text('[路径]\n影片库目录 = /Users/x/Movies\n',
                              encoding='utf-8')
            target = root / 'config' / '设置.ini'
            with mock.patch.object(settings, 'FROZEN', True), \
                    mock.patch.object(settings.sys, 'executable',
                                      str(root / 'app' / 'Kuraya')), \
                    mock.patch.object(settings, 'SETTINGS_FILE', target):
                settings._migrate_legacy_config()
            self.assertTrue(target.is_file())
            self.assertFalse(legacy.exists())
            self.assertIn('Movies', target.read_text(encoding='utf-8'))

    def test_keeps_legacy_when_user_config_exists(self):
        """用户目录已有配置时不动旧文件，避免覆盖新设置"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / 'app' / '设置.ini'
            legacy.parent.mkdir()
            legacy.write_text('旧配置', encoding='utf-8')
            target = root / 'config' / '设置.ini'
            target.parent.mkdir()
            target.write_text('新配置', encoding='utf-8')
            with mock.patch.object(settings, 'FROZEN', True), \
                    mock.patch.object(settings.sys, 'executable',
                                      str(root / 'app' / 'Kuraya')), \
                    mock.patch.object(settings, 'SETTINGS_FILE', target):
                settings._migrate_legacy_config()
            self.assertTrue(legacy.exists())
            self.assertEqual(target.read_text(encoding='utf-8'), '新配置')


class Sleep(unittest.TestCase):
    """只能在设置.ini 里改的一项，界面上没有入口"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / '设置.ini'
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(settings, 'SETTINGS_FILE', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, text):
        self.path.write_text(text, encoding='utf-8')

    def test_default_when_absent(self):
        self.write('[路径]\n影片库目录 = D:\\lib\n')
        self.assertEqual(settings.load()['sleep'], settings.DEFAULT_SLEEP)

    def test_read_from_ini(self):
        self.write('[路径]\n影片库目录 = D:\\lib\n\n[刮削]\n间隔秒数 = 0.5\n')
        self.assertEqual(settings.load()['sleep'], 0.5)

    def test_zero_allowed(self):
        self.write('[路径]\n影片库目录 = D:\\lib\n\n[刮削]\n间隔秒数 = 0\n')
        self.assertEqual(settings.load()['sleep'], 0)

    def test_negative_clamped(self):
        self.write('[路径]\n影片库目录 = D:\\lib\n\n[刮削]\n间隔秒数 = -5\n')
        self.assertEqual(settings.load()['sleep'], 0)

    def test_garbage_falls_back(self):
        """填错了不该让整个程序起不来"""
        self.write('[路径]\n影片库目录 = D:\\lib\n\n[刮削]\n间隔秒数 = 慢一点\n')
        self.assertEqual(settings.load()['sleep'], settings.DEFAULT_SLEEP)

    def test_survives_save(self):
        """界面改播放器时会整份重写文件，不能把手写的小节冲掉"""
        self.write('[路径]\n影片库目录 = D:\\lib\n\n[刮削]\n间隔秒数 = 7\n')
        settings.save(player='D:\\player.exe')
        self.assertEqual(settings.load()['sleep'], 7)
        self.assertEqual(settings.load()['player'], 'D:\\player.exe')


class UpdateState(unittest.TestCase):
    """更新检查的缓存读写，与「已询问PATH」同在「状态」段"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / '设置.ini'
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(settings, 'SETTINGS_FILE', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_when_absent(self):
        self.assertEqual(settings.update_state(), {'checked': '', 'latest': ''})

    def test_save_and_read(self):
        settings.save_update_state('1700000000', '0.3.0')
        self.assertEqual(settings.update_state(),
                         {'checked': '1700000000', 'latest': '0.3.0'})

    def test_survives_other_save(self):
        """界面改设置会整份重写文件，不能把更新缓存冲掉"""
        settings.save_update_state('1700000000', '0.3.0')
        settings.save(player='D:\\player.exe')
        self.assertEqual(settings.update_state()['latest'], '0.3.0')


class Language(unittest.TestCase):
    """界面语言配置：空串跟随系统，其余为语言代码"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / '设置.ini'
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(settings, 'SETTINGS_FILE', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_is_empty(self):
        self.assertEqual(settings.load()['language'], '')

    def test_save_and_read(self):
        settings.save(language='zh-TW')
        self.assertEqual(settings.load()['language'], 'zh-TW')

    def test_clear_restores_follow_system(self):
        settings.save(language='en')
        settings.save(language='')
        self.assertEqual(settings.load()['language'], '')

    def test_survives_other_saves(self):
        settings.save(language='zh-CN')
        settings.save(player='D:\\player.exe')
        self.assertEqual(settings.load()['language'], 'zh-CN')


if __name__ == '__main__':
    unittest.main()
