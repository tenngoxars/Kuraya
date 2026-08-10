# -*- coding: utf-8 -*-
"""test_updater*.py 共享的配置隔离工具，自身不是测试文件。"""
import tempfile
from pathlib import Path
from unittest import mock

from kuraya import i18n as _i18n
_i18n._lang = _i18n.ZH_CN  # 测试断言简体中文文案，固定语言

from kuraya import settings


def patch_config():
    """把配置指向临时文件，让缓存读写走真实路径"""
    tmp = tempfile.TemporaryDirectory()
    target = Path(tmp.name) / '设置.ini'
    patcher = mock.patch.object(settings, 'SETTINGS_FILE', target)
    patcher.start()
    return tmp
