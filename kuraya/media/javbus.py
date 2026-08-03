# -*- coding: utf-8 -*-
"""
数据源：javbus。

只有这一个源，因此不设基类、不做注册表、不做多源轮询，接缝就是 fetch() 的签名本身。
站点改版时改的是顶部的 XPATH，跑 `kuraya selftest` 可核对解析是否失效。
"""
import re
from urllib.parse import urljoin, urlparse

from lxml import etree

from . import http
from .model import Movie

BASE = 'https://www.javbus.com/'

HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
              'image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7',
    'Referer': BASE,
    'Upgrade-Insecure-Requests': '1',
}

COOKIES = {'existmag': 'all'}

XPATH = {
    'number':   '//span[contains(text(),"識別碼:")]/../span[2]/text()',
    'title':    '//div[@class="container"]/h3/text()',
    'release':  '//span[contains(text(),"發行日期:")]/../text()',
    'runtime':  '//span[contains(text(),"長度:")]/../text()',
    'studio':   '//span[contains(text(),"製作商:")]/../a/text()',
    'label':    '//span[contains(text(),"發行商:")]/../a/text()',
    'series':   '//span[contains(text(),"系列:")]/../a/text()',
    'director': '//span[contains(text(),"導演:")]/../a/text()',
    'tags':     '//span[@class="genre"]/label/a/text()',
    'actors':   '//div[@id="avatar-waterfall"]/a/span/text()',
    'cover':    '//a[@class="bigImage"]/@href',
}

_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
_MINUTES = re.compile(r'\d+')
_NUMBER_PARTS = re.compile(r'^([A-Za-z]+)-?(\d+)$')

_DMM_DIGITAL = 'https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/{cid}/{cid}pl.jpg'
_DMM_MONO = 'https://pics.dmm.co.jp/mono/movie/adult/{cid}/{cid}pl.jpg'
_DMM_HEADERS = {'Referer': 'https://www.dmm.co.jp/'}

_PLACEHOLDER = 10000


def fetch(number: str) -> Movie | None:
    """
    查询一个番号，查不到返回 None。

    网络本身出问题时由 http 层抛 Unavailable，与「这部没有」是两回事。
    """
    html = http.get(urljoin(BASE, number), headers=HEADERS, cookies=COOKIES)
    if not html:
        return None

    tree = etree.HTML(html)
    if tree is None:
        return None

    title = _title(tree, number)
    if not title:
        return None

    return Movie(
        number=_one(tree, 'number') or number.upper(),
        title=title,
        cover_url=cover_url(number, _one(tree, 'cover')),
        actors=_all(tree, 'actors'),
        tags=_all(tree, 'tags'),
        release=_match(_DATE, _join(tree, 'release')),
        runtime=_match(_MINUTES, _join(tree, 'runtime')),
        studio=_one(tree, 'studio'),
        label=_one(tree, 'label'),
        series=_one(tree, 'series'),
        director=_one(tree, 'director'),
    )


def cover_url(number: str, javbus_cover: str) -> str:
    """
    挑一张封面。DMM 母版比 javbus 自存封面清晰得多，两套目录逐个探测取最大者，
    全都无效则退回 javbus。体积是分辨率的代理指标。
    """
    best, best_size = '', 0
    for url in _dmm_candidates(number):
        size = http.head_size(url, headers=_DMM_HEADERS)
        if size > best_size:
            best, best_size = url, size

    if best_size >= _PLACEHOLDER:
        return best
    return urljoin(BASE, javbus_cover) if javbus_cover else ''


def image_headers(url: str) -> dict:
    """
    取封面图要带的请求头。两个图床都验来路：DMM 认 dmm.co.jp，
    javbus 自存的图不带完整浏览器头会被 Cloudflare 挡下。
    """
    if 'dmm.co.jp' in urlparse(url).netloc:
        return _DMM_HEADERS
    return HEADERS


def _dmm_candidates(number: str) -> list[str]:
    """
    cid 与番号之间是固定换算，两套目录各有各的写法：

        XXX-000  →  digital  xxx00000
                 →  mono     1xxx0
                 →  mono     1xxx00000
    """
    matched = _NUMBER_PARTS.match(number)
    if not matched:
        return []
    letters = matched.group(1).lower()
    digits = matched.group(2)
    padded = digits.zfill(5)
    bare = str(int(digits))

    return [
        _DMM_DIGITAL.format(cid=f'{letters}{padded}'),
        _DMM_MONO.format(cid=f'1{letters}{bare}'),
        _DMM_MONO.format(cid=f'1{letters}{padded}'),
    ]


def _one(tree, key: str) -> str:
    for text in tree.xpath(XPATH[key]):
        text = text.strip()
        if text:
            return text
    return ''


def _all(tree, key: str) -> tuple[str, ...]:
    seen = []
    for text in tree.xpath(XPATH[key]):
        text = text.strip()
        if text and text not in seen:
            seen.append(text)
    return tuple(seen)


def _join(tree, key: str) -> str:
    """值与标签同在一个节点下，取值散落在多个文本节点里，合起来再正则"""
    return ' '.join(text.strip() for text in tree.xpath(XPATH[key]))


def _match(pattern, text: str) -> str:
    found = pattern.search(text)
    return found.group(0) if found else ''


def _title(tree, number: str) -> str:
    """页面标题开头重复一遍番号，去掉它"""
    raw = _one(tree, 'title')
    if not raw:
        return ''
    stripped = raw
    for prefix in (number.upper(), number.lower(), number):
        if stripped.upper().startswith(prefix.upper()):
            stripped = stripped[len(prefix):]
            break
    return stripped.strip(' -　') or raw.strip()


# 自测用的番号必须是真实存在且不会下架的，换成占位番号就永远查不到、自测失去意义。
# 这四个分别覆盖 DMM digital、DMM mono、javbus 回退三条封面分支
_PROBES = ('ABF-372', 'SSIS-826', 'START-257', 'MIDE-123')


def selftest() -> int:
    """
    用一组固定番号实跑，字段缺失即说明 xpath 已失效。返回失败数。

    入口是 `kuraya selftest`，不要用 `python -m kuraya.media.javbus` ——
    本模块已被 media/__init__ 导入，再以 -m 执行会加载出第二份，runpy 会就此告警。
    """
    failed = 0
    for number in _PROBES:
        try:
            movie = fetch(number)
        except http.Unavailable as exc:
            print(f'  {number}  网络不可用：{exc}')
            failed += 1
            continue

        if movie is None:
            print(f'  {number}  未找到')
            failed += 1
            continue

        missing = [name for name in ('title', 'release', 'runtime', 'studio', 'cover_url')
                   if not getattr(movie, name)]
        if not movie.actors:
            missing.append('actors')
        if not movie.tags:
            missing.append('tags')

        mark = '✕' if missing else '✓'
        print(f'  {mark} {movie.number}  {movie.title[:32]}')
        print(f'      {movie.release}  {movie.runtime}分  {movie.studio}  '
              f'{"、".join(movie.actors[:3])}')
        print(f'      {movie.cover_url}')
        if missing:
            print(f'      缺字段：{", ".join(missing)}')
            failed += 1
    return failed
