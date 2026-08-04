# -*- coding: utf-8 -*-
"""
多语言支持：语言检测、文案翻译、翻译表与源码调用的完整性。

    python -m unittest discover tests
"""
import ast
import unittest
from pathlib import Path
from unittest import mock

from kuraya import i18n, i18n_en, i18n_zh_tw
from kuraya.i18n import EN, ZH_CN, ZH_TW, tr


class DetectLang(unittest.TestCase):
    """跟随系统语言：POSIX 看环境变量，Windows 看 UI 语言"""

    def detect(self, environ, locale=None):
        with mock.patch.dict(i18n.os.environ, environ, clear=True), \
                mock.patch.object(i18n.os, 'name', 'posix'), \
                mock.patch.object(i18n.locale, 'getdefaultlocale',
                                  return_value=locale):
            return i18n.detect_lang()

    def test_simplified_chinese(self):
        self.assertEqual(self.detect({'LANG': 'zh_CN.UTF-8'}), ZH_CN)

    def test_traditional_chinese(self):
        self.assertEqual(self.detect({'LC_ALL': 'zh_TW.UTF-8'}), ZH_TW)

    def test_hong_kong_counts_as_traditional(self):
        self.assertEqual(self.detect({'LANG': 'zh_HK.UTF-8'}), ZH_TW)

    def test_hant_marker_counts_as_traditional(self):
        self.assertEqual(self.detect({'LANG': 'zh-Hant_TW'}), ZH_TW)

    def test_singapore_chinese_stays_simplified(self):
        self.assertEqual(self.detect({'LANG': 'zh_SG.UTF-8'}), ZH_CN)

    def test_english(self):
        self.assertEqual(self.detect({'LANG': 'en_US.UTF-8'}), EN)

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(self.detect({'LANG': 'fr_FR.UTF-8'}), EN)

    def test_no_env_falls_back_to_locale(self):
        self.assertEqual(self.detect({}, locale=('zh_TW', 'UTF-8')), ZH_TW)

    def test_no_env_no_locale_falls_back_to_english(self):
        self.assertEqual(self.detect({}, locale=(None, None)), EN)

    def test_lc_all_takes_precedence(self):
        self.assertEqual(
            self.detect({'LC_ALL': 'zh_TW', 'LANG': 'en_US'}), ZH_TW)

    def test_windows_uses_ui_language(self):
        """Windows 走 GetUserDefaultUILanguage，0x0404 是 zh-TW"""
        with mock.patch.object(i18n.os, 'name', 'nt'):
            ctypes = mock.MagicMock()
            ctypes.windll.kernel32.GetUserDefaultUILanguage.return_value = 0x0404
            with mock.patch.dict('sys.modules', {'ctypes': ctypes}):
                with mock.patch.dict(i18n.os.environ, {}, clear=True):
                    self.assertEqual(i18n.detect_lang(), ZH_TW)

    def test_traditional_codes_all_map_to_traditional(self):
        """TRADITIONAL_CODES 是网页注入的同一份判定表，每个值都必须命中繁体"""
        for code in i18n.TRADITIONAL_CODES:
            with self.subTest(code=code):
                self.assertEqual(self.detect({'LANG': code.upper() + '.UTF-8'}),
                                 ZH_TW)

    def test_kkuraya_lang_overrides_system(self):
        """KURAYA_LANG 环境变量优先于系统检测"""
        for override, expected in (('zh-CN', ZH_CN), ('zh_TW', ZH_TW),
                                   ('zh-HK', ZH_TW), ('en', EN),
                                   ('en_US', EN)):
            with self.subTest(override=override):
                self.assertEqual(
                    self.detect({'LANG': 'en_US.UTF-8',
                                 'KURAYA_LANG': override}), expected)

    def test_unknown_override_ignored(self):
        self.assertEqual(self.detect({'LANG': 'zh_TW.UTF-8',
                                      'KURAYA_LANG': 'fr'}), ZH_TW)


class Translate(unittest.TestCase):
    """tr() 查表、回退与参数注入"""

    def setUp(self):
        patcher = mock.patch.object(i18n, '_lang', ZH_CN)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_zh_cn_returns_original(self):
        self.assertEqual(tr('刮削入库'), '刮削入库')

    def test_zh_tw_lookup(self):
        with mock.patch.object(i18n, '_lang', ZH_TW):
            self.assertEqual(tr('刮削入库'), '刮削入庫')

    def test_en_lookup(self):
        with mock.patch.object(i18n, '_lang', EN):
            self.assertEqual(tr('刮削入库'), 'Scrape & archive')

    def test_missing_key_falls_back_to_original(self):
        with mock.patch.object(i18n, '_lang', EN):
            self.assertEqual(tr('未收录的文案'), '未收录的文案')

    def test_format_args_injected(self):
        with mock.patch.object(i18n, '_lang', EN):
            self.assertEqual(tr('库内共 {total} 部', total=12),
                             '12 titles in the library')

    def test_placeholders_kept_in_zh_tw(self):
        with mock.patch.object(i18n, '_lang', ZH_TW):
            self.assertEqual(tr('库内共 {total} 部', total=12), '庫內共 12 部')

    def test_lookup_is_exact_including_spaces(self):
        """带前导空格的文案是独立 key，译文保持与 key 相同的缩进"""
        with mock.patch.object(i18n, '_lang', EN):
            self.assertEqual(tr('  已取消'), '  Cancelled')


class TableIntegrity(unittest.TestCase):
    """翻译表必须覆盖源码里所有 tr() 字面量，漏一条就是界面漏翻一条"""

    def source_keys(self):
        keys = set()
        root = Path(__file__).resolve().parent.parent / 'kuraya'
        for f in root.rglob('*.py'):
            tree = ast.parse(f.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == 'tr' and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    keys.add(node.args[0].value)
        from kuraya import TAGLINE  # 经变量传入 tr()，AST 收集不到
        keys.add(TAGLINE)
        return keys

    def test_tables_cover_all_source_keys(self):
        keys = self.source_keys()
        self.assertEqual(sorted(keys - set(i18n_zh_tw.TABLE)), [])
        self.assertEqual(sorted(keys - set(i18n_en.TABLE)), [])

    def test_tables_share_same_keys(self):
        self.assertEqual(set(i18n_zh_tw.TABLE), set(i18n_en.TABLE))

    def test_no_empty_translations(self):
        empty = [k for k in i18n_zh_tw.TABLE if not i18n_zh_tw.TABLE[k]]
        empty += [k for k in i18n_en.TABLE if not i18n_en.TABLE[k]]
        self.assertEqual(empty, [])

    def test_translations_are_different_from_original(self):
        """整表与原文完全相同说明没翻（个别刻意保留的词除外）"""
        unchanged = [k for k, v in i18n_en.TABLE.items() if v == k]
        self.assertLess(len(unchanged), 30)


class ConfiguredLanguage(unittest.TestCase):
    """设置里选定的语言优先于系统检测，refresh 后立即生效"""

    def setUp(self):
        # patch 退出时自动恢复 _lang 原值，避免 refresh 污染其他断言中文的测试
        self.lang = mock.patch.object(i18n, '_lang', None).start()
        self.addCleanup(mock.patch.stopall)

    def current(self, language):
        i18n.refresh()
        with mock.patch('kuraya.settings.load',
                        return_value={'language': language}):
            return i18n.current()

    def test_config_overrides_system(self):
        self.assertEqual(self.current('zh-TW'), ZH_TW)
        self.assertEqual(self.current('en'), EN)
        self.assertEqual(self.current('zh-CN'), ZH_CN)

    def test_empty_config_falls_back_to_system(self):
        with mock.patch.object(i18n, 'detect_lang', return_value=EN):
            self.assertEqual(self.current(''), EN)

    def test_refresh_clears_cache(self):
        with mock.patch('kuraya.settings.load',
                        return_value={'language': 'zh-CN'}):
            self.assertEqual(i18n.current(), ZH_CN)
            with mock.patch('kuraya.settings.load',
                            return_value={'language': 'en'}):
                i18n.refresh()
                self.assertEqual(i18n.current(), EN)


if __name__ == '__main__':
    unittest.main()
