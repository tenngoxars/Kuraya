# -*- coding: utf-8 -*-
"""
首次运行引导：PATH 安装征询、目录选择分支。

    python -m unittest discover tests
"""
import unittest
from pathlib import Path
from unittest import mock

from kuraya import i18n as _i18n
_i18n._lang = _i18n.ZH_CN  # 测试断言简体中文文案（含 pick 标题），先固定语言

from kuraya import setup


class NonInteractive(unittest.TestCase):
    """
    没人在屏幕前时，两处等待都必须让路：引导要弹原生选择框等人点
    （picker 超时 300 秒），退出前的「按回车关闭」则纯属多余。
    """

    def test_load_paths_refuses_to_prompt(self):
        from kuraya.launcher import ConfigError
        with mock.patch('kuraya.console.interactive', return_value=False), \
                mock.patch('kuraya.settings.load',
                           return_value={'configured': False}), \
                mock.patch.object(setup, 'first_run_setup') as guide:
            with self.assertRaises(ConfigError) as caught:
                setup.load_paths()
        guide.assert_not_called()
        # 报错要带上等效命令，调用方才知道下一步做什么
        self.assertIn('--set-library', str(caught.exception))

    def test_load_paths_still_guides_with_tty(self):
        with mock.patch('kuraya.console.interactive', return_value=True), \
                mock.patch('kuraya.settings.load',
                           return_value={'configured': False}), \
                mock.patch.object(setup, 'first_run_setup',
                                  return_value=('/lib', '/src')) as guide:
            self.assertEqual(setup.load_paths(), ('/lib', '/src'))
        guide.assert_called_once()

    def test_wait_exit_does_not_block(self):
        with mock.patch('kuraya.console.interactive', return_value=False), \
                mock.patch('builtins.input') as prompt:
            setup.wait_exit()
        prompt.assert_not_called()


class OfferPathInstall(unittest.TestCase):
    """Windows 打包版首次运行的 PATH 征询（曾因 key 未定义而崩溃）"""

    def run_offer(self, answer='y', installed=False, path_asked=False):
        with mock.patch.object(setup.os, 'name', 'nt'), \
             mock.patch.object(setup.sys, 'frozen', True, create=True), \
             mock.patch('kuraya.pathenv.is_installed',
                        return_value=installed), \
             mock.patch('kuraya.settings.load',
                        return_value={'path_asked': path_asked}), \
             mock.patch('builtins.input', return_value=answer), \
             mock.patch('kuraya.settings.save'), \
             mock.patch('kuraya.pathenv.install',
                        return_value=(True, '')) as install:
            setup.offer_path_install()
        return install

    def test_confirm_installs(self):
        """输入 y 确认后登记 PATH"""
        install = self.run_offer('y')
        install.assert_called_once()

    def test_enter_skips(self):
        """直接回车跳过：不再追问、不安装"""
        install = self.run_offer('')
        install.assert_not_called()

    def test_non_windows_skipped(self):
        """非 Windows 不征询"""
        with mock.patch.object(setup.os, 'name', 'posix'), \
             mock.patch('kuraya.pathenv.install') as install:
            setup.offer_path_install()
        install.assert_not_called()


class FirstRunSetup(unittest.TestCase):
    """目录引导分支：默认从零开始，选 1 时先选已有影片目录再选影片库"""

    def run_setup(self, answers, picks, isdir=True):
        """answers: input() 依次返回；picks: picker.pick 依次返回 (path, err)"""
        save = mock.Mock(side_effect=lambda **kw: {
            'library': kw.get('library', ''),
            'source': kw.get('source', ''),
        })
        ensure = mock.Mock(side_effect=lambda lib, src, create_library=False: (
            Path(lib),
            Path(src) if src else Path(lib) / '待整理'))
        with mock.patch('builtins.input', side_effect=answers), \
             mock.patch.object(setup.picker, 'pick', side_effect=picks) as pick, \
             mock.patch.object(setup.settings, 'detect_player',
                               return_value=''), \
             mock.patch.object(setup.settings, 'save', save), \
             mock.patch.object(setup.settings, 'ensure_dirs', ensure), \
             mock.patch.object(setup.os.path, 'isdir', return_value=isdir), \
             mock.patch.object(setup, 'offer_path_install'):
            result = setup.first_run_setup()
        return result, save, ensure, pick

    def test_enter_defaults_to_scratch(self):
        """回车默认从零开始：只选影片库，待整理留空走默认"""
        result, save, ensure, pick = self.run_setup([''], [('/lib', '')])
        self.assertEqual(result, (Path('/lib'), Path('/lib/待整理')))
        save.assert_called_once_with(library='/lib', source='', player='')
        ensure.assert_called_once()
        self.assertTrue(ensure.call_args.kwargs['create_library'])
        # 判别性：从零开始只弹一次框（旧代码无分支，这里锁定新契约）
        pick.assert_called_once_with('folder', '选择影片库目录')

    def test_explicit_two_uses_scratch(self):
        """显式输入 2 与回车等价：从零开始"""
        result, save, ensure, pick = self.run_setup(['2'], [('/lib', '')])
        self.assertEqual(result, (Path('/lib'), Path('/lib/待整理')))
        save.assert_called_once_with(library='/lib', source='', player='')
        pick.assert_called_once_with('folder', '选择影片库目录')

    def test_existing_asks_source_then_library(self):
        """选 1：先选已有影片目录（待整理），再选影片库"""
        result, save, ensure, pick = self.run_setup(
            ['1'], [('/film', ''), ('/lib', '')])
        self.assertEqual(result, (Path('/lib'), Path('/film')))
        save.assert_called_once_with(library='/lib', source='/film', player='')
        # 判别性：选 1 必须先弹已有影片目录框，再弹影片库框
        self.assertEqual(
            [c.args[1] for c in pick.call_args_list],
            ['选择已有影片的目录', '选择影片库目录'])

    def test_cancel_first_pick_returns_none(self):
        """选 1 后在第一个选择框取消：不写配置、不再弹第二个框"""
        result, save, ensure, pick = self.run_setup(['1'], [('', '')])
        self.assertIsNone(result)
        save.assert_not_called()
        pick.assert_called_once()   # 取消后不应继续弹影片库框

    def test_eof_falls_back_to_scratch(self):
        """非 TTY（EOF）按没有影片处理，走默认分支"""
        save = mock.Mock(side_effect=lambda **kw: {
            'library': kw.get('library', ''),
            'source': kw.get('source', ''),
        })
        with mock.patch('builtins.input',
                        side_effect=EOFError), \
             mock.patch.object(setup.picker, 'pick',
                               return_value=('/lib', '')) as pick, \
             mock.patch.object(setup.settings, 'detect_player',
                               return_value=''), \
             mock.patch.object(setup.settings, 'save', save), \
             mock.patch.object(
                 setup.settings, 'ensure_dirs',
                 side_effect=lambda lib, src, create_library=False: (
                     Path(lib),
                     Path(src) if src else Path(lib) / '待整理')), \
             mock.patch.object(setup, 'offer_path_install'):
            result = setup.first_run_setup()
        self.assertEqual(result, (Path('/lib'), Path('/lib/待整理')))
        save.assert_called_once_with(library='/lib', source='', player='')
        # 判别性：EOF 回退后只弹一次框，与从零开始一致
        pick.assert_called_once_with('folder', '选择影片库目录')

    def test_pick_error_falls_back_to_manual_input(self):
        """选择框不可用时降级为终端手动输入"""
        result, save, ensure, pick = self.run_setup(['', '/manual/lib'],
                                                    [('', 'no tkinter')])
        self.assertEqual(result, (Path('/manual/lib'),
                                  Path('/manual/lib/待整理')))
        save.assert_called_once_with(library='/manual/lib', source='',
                                     player='')

    def test_manual_input_missing_dir_rejected(self):
        """手动输入不存在的目录：提示后返回空，不写配置"""
        result, save, ensure, pick = self.run_setup(['', '/nope'],
                                                    [('', 'no tkinter')],
                                                    isdir=False)
        self.assertIsNone(result)
        save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
