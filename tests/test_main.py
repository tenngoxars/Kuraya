# -*- coding: utf-8 -*-
"""
`kuraya uninstall`：确认后移除命令入口与程序文件；
brew / 源码安装走对应提示，Windows 因运行中 exe 无法自删而提示手动。

    python -m unittest discover tests
"""
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from kuraya import __main__ as main
from kuraya import i18n as _i18n

_i18n._lang = _i18n.ZH_CN


class Uninstall(unittest.TestCase):
    """卸载流程：确认 → PATH → shim → 程序目录"""

    def run_uninstall(self, answer='y', cfg_answer='n', frozen=True,
                      win32=False, darwin=False,
                      executable='/opt/Kuraya/Kuraya'):
        with mock.patch.object(main, 'FROZEN', frozen), \
                mock.patch.object(main.sys, 'platform',
                                  'win32' if win32
                                  else ('darwin' if darwin else 'linux')), \
                mock.patch.object(main.sys, 'executable', executable), \
                mock.patch('builtins.input',
                           side_effect=[answer, cfg_answer]), \
                mock.patch('kuraya.pathenv.uninstall',
                           return_value=(True, '')), \
                mock.patch('shutil.rmtree') as rmtree:
            code = main.do_uninstall()
        return code, rmtree

    def test_confirms_and_removes(self):
        code, rmtree = self.run_uninstall()
        self.assertEqual(code, 0)
        rmtree.assert_called()          # 删除程序目录
        rmtree.assert_any_call(mock.ANY, ignore_errors=True)  # 壳 app

    def test_confirms_and_removes_config(self):
        """确认卸载并确认删除配置：配置目录一并移除"""
        code, rmtree = self.run_uninstall(cfg_answer='y')
        self.assertEqual(code, 0)
        rmtree.assert_any_call(main.settings.APP_DIR)  # 配置目录

    def test_config_kept_by_default(self):
        """配置询问默认保留：不回 y 就不删配置目录"""
        code, rmtree = self.run_uninstall()
        self.assertEqual(code, 0)
        for call in rmtree.call_args_list:
            self.assertNotEqual(call.args[0], main.settings.APP_DIR)

    def test_config_missing_not_an_error(self):
        """从未运行过（配置目录不存在）：确认删除也不误报失败"""
        with mock.patch.object(main, 'FROZEN', True), \
                mock.patch.object(main.sys, 'platform', 'linux'), \
                mock.patch.object(main.sys, 'executable', '/opt/Kuraya/Kuraya'), \
                mock.patch('builtins.input', side_effect=['y', 'y']), \
                mock.patch('kuraya.pathenv.uninstall',
                           return_value=(True, '')), \
                mock.patch.object(main.settings, 'APP_DIR',
                                  main.Path('/nonexistent/kuraya-config')), \
                mock.patch('shutil.rmtree') as rmtree:
            code = main.do_uninstall()
        self.assertEqual(code, 0)
        # 配置目录不存在：不应触发对它的删除调用
        for call in rmtree.call_args_list:
            self.assertNotEqual(call.args[0],
                                main.Path('/nonexistent/kuraya-config'))

    def test_cancel_keeps_everything(self):
        code, rmtree = self.run_uninstall(answer='n')
        self.assertEqual(code, 0)
        rmtree.assert_not_called()

    def test_brew_rejected(self):
        """Homebrew 安装由 brew 管理，不自行删除"""
        code, _ = self.run_uninstall(
            darwin=True,
            executable='/opt/homebrew/Cellar/kuraya/0.5.7/libexec/Kuraya/Kuraya')
        self.assertEqual(code, 1)

    def test_source_install_rejected(self):
        code, _ = self.run_uninstall(frozen=False)
        self.assertEqual(code, 1)

    def test_windows_manual_removal(self):
        """Windows 上运行中的 exe 无法自删，提示手动删除"""
        code, rmtree = self.run_uninstall(win32=True)
        self.assertEqual(code, 0)
        # Windows 分支不删程序目录，只可能删配置（cfg_answer 默认 n）
        rmtree.assert_not_called()


class FallbackError(unittest.TestCase):
    """未预料异常的兜底处理器能正常工作（曾因 setup 未导入而自身 NameError）"""

    def test_fallback_shows_error(self):
        with mock.patch.object(main.sys, 'argv', ['kuraya', 'rebuild']), \
             mock.patch.object(main, 'FROZEN', False), \
             mock.patch.object(main, 'resolve_paths',
                               side_effect=RuntimeError('boom')), \
             mock.patch('kuraya.protocol.ensure_shell_app'), \
             mock.patch('kuraya.protocol.ensure_registered'), \
             mock.patch('kuraya.console.enable_ansi'), \
             mock.patch('kuraya.launcher.say'), \
             mock.patch('kuraya.launcher.spin'), \
             mock.patch('kuraya.updater.show'), \
             mock.patch('kuraya.setup.show_error') as show:
            code = main.main()
        self.assertEqual(code, main.CONFIG_ERROR)
        show.assert_called_once()
        self.assertIn('boom', show.call_args.args[0])


class BareCommand(unittest.TestCase):
    """
    裸 `kuraya`：屏幕前有人才进菜单，没人就直接跑完整流程。

    菜单靠按键驱动，管道与定时任务里读到 EOF 便退出，
    结果是一部片子没动却返回 0——调用方无从察觉。
    """

    def run_bare(self, interactive):
        stats = {'done': 1, 'failed': 0, 'found': 1}
        with mock.patch.object(main.sys, 'argv', ['kuraya']), \
                mock.patch('kuraya.console.interactive',
                           return_value=interactive), \
                mock.patch('kuraya.protocol.ensure_shell_app'), \
                mock.patch('kuraya.protocol.ensure_registered'), \
                mock.patch('kuraya.menu.run', return_value=0) as menu_run, \
                mock.patch.object(main, 'FROZEN', False), \
                mock.patch.object(main, 'resolve_paths',
                                  return_value=('/lib', '/src')), \
                mock.patch('kuraya.console.enable_ansi'), \
                mock.patch('kuraya.launcher.say'), \
                mock.patch('kuraya.launcher.spin'), \
                mock.patch('kuraya.updater.show'), \
                mock.patch('kuraya.launcher.cmd_all',
                           return_value=(stats, False)) as cmd_all:
            code = main.main()
        return code, menu_run, cmd_all

    def test_without_tty_runs_full_flow(self):
        code, menu_run, cmd_all = self.run_bare(interactive=False)
        menu_run.assert_not_called()
        cmd_all.assert_called_once()
        self.assertEqual(code, main.OK)

    def test_with_tty_opens_menu(self):
        _, menu_run, cmd_all = self.run_bare(interactive=True)
        menu_run.assert_called_once()
        cmd_all.assert_not_called()


class DeleteRequest(unittest.TestCase):
    """协议删除成功后必须重建静态片库，失败不能误重建。"""

    def test_protocol_play_entry_routes_delete_request(self):
        with mock.patch.object(main, 'do_delete', return_value=0) as delete:
            code = main.do_play('kuraya:delete:%2Ftmp%2Flibrary%2F%E6%BC%94%E5%91%98%2FABC-001')
        self.assertEqual(code, 0)
        delete.assert_called_once_with('/tmp/library/演员/ABC-001')

    def test_delete_rebuilds_after_moving_to_trash(self):
        with mock.patch.object(main.settings, 'load', return_value={
                'library': '/tmp/library'}), \
                mock.patch('kuraya.trash.movie_dir', return_value=main.Path('/tmp/library/演员/ABC-001')) as valid, \
                mock.patch('kuraya.trash.move_to_trash', return_value=True) as move, \
                mock.patch('kuraya.gallery.main', return_value=0) as rebuild:
            code = main.do_delete('/tmp/library/演员/ABC-001')
        self.assertEqual(code, 0)
        valid.assert_called_once_with('/tmp/library/演员/ABC-001', '/tmp/library')
        move.assert_called_once_with(main.Path('/tmp/library/演员/ABC-001'))
        rebuild.assert_called_once_with([str(main.Path('/tmp/library').resolve())])

    def test_delete_failure_does_not_rebuild(self):
        with mock.patch.object(main.settings, 'load', return_value={
                'library': '/tmp/library'}), \
                mock.patch('kuraya.trash.movie_dir', return_value=None), \
                mock.patch('kuraya.trash.move_to_trash') as move, \
                mock.patch('kuraya.gallery.main') as rebuild:
            code = main.do_delete('/tmp/outside')
        self.assertEqual(code, 1)
        rebuild.assert_not_called()
        move.assert_not_called()

    def test_delete_idempotent_when_movie_already_trashed(self):
        """上次删除成功但重建失败后，再删同一部直接重建页面（幂等）。

        判别性：旧逻辑 movie_dir 返回 None 直接失败，恢复的卡片再删
        永远失败，形成死循环
        """
        with mock.patch.object(main.settings, 'load', return_value={
                'library': '/tmp/library'}), \
                mock.patch('kuraya.trash.movie_dir', return_value=None), \
                mock.patch('kuraya.trash.movie_path',
                           return_value=main.Path('/tmp/library/演员/ABC-001')), \
                mock.patch('kuraya.trash.move_to_trash') as move, \
                mock.patch('kuraya.gallery.main', return_value=0) as rebuild:
            code = main.do_delete('/tmp/library/演员/ABC-001')
        self.assertEqual(code, 0)
        move.assert_not_called()
        rebuild.assert_called_once_with(
            [str(main.Path('/tmp/library').resolve())])

    def test_delete_rebuilds_a_real_page_after_trashing_movie(self):
        """协议入口完成真实的移入与页面重建后，旧影片不再出现在页面。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / 'library'
            movie = library / '演员甲' / 'ABC-001'
            movie.mkdir(parents=True)
            (movie / 'ABC-001.nfo').write_text(
                '<movie><num>ABC-001</num><actor><name>演员甲</name></actor>'
                '</movie>', encoding='utf-8')
            (movie / 'ABC-001.mp4').write_bytes(b'video')
            trash_dir = root / 'trash'
            trash_dir.mkdir()

            def move_to_test_trash(path):
                shutil.move(str(path), str(trash_dir / path.name))
                return True

            with mock.patch.object(main.settings, 'load', return_value={
                    'library': str(library)}), \
                    mock.patch('kuraya.trash.move_to_trash',
                                side_effect=move_to_test_trash), \
                    redirect_stdout(io.StringIO()):
                code = main.do_delete(str(movie))

            self.assertEqual(code, 0)
            self.assertFalse(movie.exists())
            self.assertNotIn('"ABC-001"',
                             (library / 'index.html').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
