# -*- coding: utf-8 -*-
"""
多语言支持：界面文案跟随系统语言，支持简体中文（原文）、繁体中文、英文。

用法：tr('简体中文原文', 参数=值) 返回当前语言文案；
所有用户可见文案的 f-string 一律改写为 tr() 调用，
颜色等装饰代码留在调用处拼接，不进入翻译表。
"""
import locale
import os
import sys

from . import i18n_en, i18n_zh_tw

ZH_CN, ZH_TW, EN = 'zh-CN', 'zh-TW', 'en'

# 繁体中文的地区标记，Python 与网页共用（gallery 生成页面时注入 JS）
TRADITIONAL_CODES = ('zh-tw', 'zh-hk', 'zh-mo', 'zh-hant')

_TABLES = {ZH_TW: i18n_zh_tw.TABLE, EN: i18n_en.TABLE}
_lang = None


def detect_lang():
    """按系统语言返回 zh-CN / zh-TW / en。KURAYA_LANG 环境变量优先"""
    override = os.environ.get('KURAYA_LANG', '').strip().lower()
    if override in ('zh-cn', 'zh_cn', 'zh-hans', 'zh'):
        return ZH_CN
    if override in ('zh-tw', 'zh_tw', 'zh-hk', 'zh-hant'):
        return ZH_TW
    if override in ('en', 'en-us', 'en_us'):
        return EN
    code = None
    if os.name == 'nt':
        try:
            import ctypes
            uilang = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            code = locale.windows_locale.get(uilang)
        except Exception:
            pass
    if not code:
        code = (os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES')
                or os.environ.get('LANG'))
    if not code:
        try:
            code = locale.getdefaultlocale()[0]
        except Exception:
            pass
    if not code:
        return EN
    code = str(code).lower().replace('_', '-')
    if code.startswith('zh'):
        # 去掉 .UTF-8 之类编码后缀；港台澳与显式繁体标记走繁体，其余中文走简体
        base = code.split('.')[0]
        return ZH_TW if base.startswith(TRADITIONAL_CODES) else ZH_CN
    return EN


def current():
    """当前语言，进程内缓存。设置里选定的语言优先于系统检测"""
    global _lang
    if _lang is None:
        from . import settings
        configured = settings.load().get('language', '').strip().lower()
        _lang = _CONFIG_LANGS.get(configured) or detect_lang()
    return _lang


def refresh():
    """清空语言缓存。设置里切换语言后调用，让后续文案立即生效"""
    global _lang
    _lang = None


# 设置里可选的语言（空串 = 跟随系统）
_CONFIG_LANGS = {'zh-cn': ZH_CN, 'zh-tw': ZH_TW, 'zh-hk': ZH_TW, 'en': EN}


def tr(text, **kw):
    """按当前语言取文案；无译回退原文。占位符用 str.format 风格"""
    table = _TABLES.get(current(), {})
    out = table.get(text, text)
    return out.format(**kw) if kw else out
