# -*- coding: utf-8 -*-
"""
从文件名提取番号与版本标记。

纯函数，不碰磁盘、不读配置：给一个文件名，要么返回 FileId，要么返回 None。

立场是白名单 —— 只接受正规厂商发行的「字母 + 数字」形态，形如 XXX-000、YYYY-1234。
不是这个形状的一律返回 None，调用方原样留下文件、不做任何改动。素人、FC2、无码、
无固定番号本就不在支持范围内，因此不需要为它们各自准备一条专用抽取规则。

这里只判形态，不判范围：SIRO-4567、HEYZO-3021 与正规番号形状一致，会被正常识别，
再由数据源那边查不到而失败。范围由数据源天然划定，不在此重复一遍。

规格与用例表见 .agentdocs/spec/引擎行为规格.md 第二节。
"""
import re

from .model import Edition, FileId

# 扩展名。只剥离最后一段，XXX-000.1080p.x265.mp4 里的中间段留给下面的规则处理
_EXTENSION = re.compile(r'\.[A-Za-z0-9]{1,5}$')

# 下载站粘在文件名最前的来源标记，形如 example.com@ 或 a-b.example@
_SITE_PREFIX = re.compile(r'^[\w.\-]{2,}@')

# 方括号段：字幕组、发布组、分类标记
_BRACKET = re.compile(r'\[[^\]]*\]')

# 画质与编码标记。只在独立成段时剥离，否则会啃掉番号内部的字母
_QUALITY = re.compile(
    r'(?<![A-Za-z0-9])'
    r'(?:fhd|uhd|hd|sd|2160p|1080p|720p|480p|x264|x265|h264|h265|hevc|aac|web|dl)'
    r'(?![A-Za-z0-9])',
    re.I)

# 分卷。要求前面有分隔符，否则 CDX-123 这类标签会被当成分卷
_PART = re.compile(r'[-_.\s]cd\s*(\d{1,2})', re.I)

# 4K 标记。只看文件名不看完整路径 —— 影片库若位于 D:\4K影片\ 下，
# 按路径判定会让库里每一部都被打上 4k 标签
_4K = re.compile(r'(?<![A-Za-z0-9])4k(?![A-Za-z0-9])', re.I)

# 尾部版本标记，按序逐个剥离，可叠加。-UC 必须排在 -U 前面
_LEAK_UC = re.compile(r'[-_.]uc$', re.I)
_LEAK_U = re.compile(r'[-_.]u$', re.I)
_SUB_SEP = re.compile(r'[-_.]ch?$', re.I)       # -C / -CH
_SUB_TAIL = re.compile(r'(?<=\d)ch$', re.I)     # XXX000ch

# 中文字幕的文字线索
_SUB_WORDS = ('中文', '字幕')

# 番号本体：字母 2-7 位 + 数字 2-5 位，中间的连字符可有可无
_NUMBER = re.compile(r'^([A-Za-z]{2,7})-?(\d{2,5})$')

_SEPARATORS = '-_. '


def parse(filename: str) -> FileId | None:
    """
    识别文件名中的番号。识别不出返回 None。

    只接受文件名，不接受路径 —— 判定必须与文件所在位置无关。
    """
    if not filename:
        return None

    text = _EXTENSION.sub('', filename)
    if not text:
        return None

    # 中日文只可能出现在说明性文字里，取完线索后整体清掉，剩下的才是候选番号
    chinese_sub = any(word in text for word in _SUB_WORDS)
    text = ''.join(ch if ch.isascii() else ' ' for ch in text)

    text = _SITE_PREFIX.sub('', text, count=1)
    text = _BRACKET.sub(' ', text)
    text = _QUALITY.sub(' ', text)

    text, hd4k = _take_4k(text)
    text, part = _take_part(text)

    for token in text.split():
        token, sub, leaked, mark = _take_flags(token)
        matched = _NUMBER.match(token)
        if not matched:
            continue
        letters, digits = matched.group(1), matched.group(2)
        return FileId(
            number=f'{letters.upper()}-{digits}',
            edition=Edition(
                part=part,
                chinese_sub=chinese_sub or sub,
                leaked=leaked,
                leak_mark=mark,
                hd4k=hd4k,
            ),
        )
    return None


def _take_4k(text: str) -> tuple[str, bool]:
    if not _4K.search(text):
        return text, False
    return _4K.sub(' ', text), True


def _take_part(text: str) -> tuple[str, int]:
    matched = _PART.search(text)
    if not matched:
        return text, 0
    return _PART.sub(' ', text, count=1), int(matched.group(1))


def _take_flags(token: str) -> tuple[str, bool, bool, str]:
    """
    逐个剥离尾部的版本标记，直到没得剥为止 —— 标记可以叠加（-UC-C）。

    返回剩余部分与三个标记。流出标记原样保留（-UC 或 -U），
    归档时沿用文件名里实际出现的那一种。
    """
    chinese_sub = False
    leaked = False
    mark = ''

    while True:
        token = token.strip(_SEPARATORS)
        if not token:
            break
        if _LEAK_UC.search(token):
            token = _LEAK_UC.sub('', token)
            leaked, mark = True, mark or '-UC'
        elif _LEAK_U.search(token):
            token = _LEAK_U.sub('', token)
            leaked, mark = True, mark or '-U'
        elif _SUB_TAIL.search(token):
            token = _SUB_TAIL.sub('', token)
            chinese_sub = True
        elif _SUB_SEP.search(token):
            token = _SUB_SEP.sub('', token)
            chinese_sub = True
        else:
            break

    return token, chinese_sub, leaked, mark
