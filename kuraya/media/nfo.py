# -*- coding: utf-8 -*-
"""
生成 movie.nfo 的文本。纯函数，不写盘。

字段集固定，取不到值就是空元素，nfo 的形状与数据源当次的齐全程度无关。
标签语义遵循 Kodi / Emby 的 movie.nfo 公开规范。
"""
from .model import Assets, Edition, Movie

HEADER = '<?xml version="1.0" encoding="UTF-8" ?>'

RATING = 'JP-18+'

_CDATA_FIELDS = frozenset({
    'title', 'originaltitle', 'sorttitle', 'set', 'studio', 'maker',
    'label', 'director', 'outline', 'plot', 'name', 'tag', 'genre',
})

_ILLEGAL = {c: None for c in range(0x20) if c not in (0x09, 0x0A, 0x0D)}


def render(movie: Movie, edition: Edition, assets: Assets) -> str:
    """渲染一部影片的 nfo 全文。番号用 movie.number，不带版本标记"""
    title = _title(movie)
    tags = edition.extra_tags + movie.tags

    lines = [HEADER, '<movie>']
    add = lambda tag, text: lines.append(_element(tag, text))

    add('title', title)
    add('originaltitle', title)
    add('sorttitle', title)
    add('customrating', RATING)
    add('mpaa', RATING)
    add('set', movie.series)
    add('studio', movie.studio)
    add('year', movie.year)
    add('outline', _plot(movie))
    add('plot', _plot(movie))
    add('runtime', movie.runtime)
    add('poster', assets.poster)
    add('thumb', assets.thumb)
    add('fanart', assets.fanart)

    for actor in movie.actors:
        lines.append('  <actor>')
        lines.append(_element('name', actor, indent=4))
        lines.append('  </actor>')

    add('maker', movie.studio)
    add('label', movie.label)
    add('director', movie.director)

    for tag in tags:
        add('tag', tag)
    for tag in tags:
        add('genre', tag)

    add('num', movie.number)
    add('premiered', movie.release)
    add('releasedate', movie.release)
    add('release', movie.release)

    lines.append('</movie>')
    return '\n'.join(lines) + '\n'


def _title(movie: Movie) -> str:
    """标题前缀番号，媒体库里按标题排序时同一厂商的作品才挨在一起"""
    if not movie.title:
        return movie.number
    return f'{movie.number}-{movie.title}'


def _plot(movie: Movie) -> str:
    if not movie.outline:
        return ''
    return f'{movie.number}#{movie.outline}'


def _element(tag: str, text: str, indent: int = 2) -> str:
    body = _clean(text)
    if tag in _CDATA_FIELDS:
        body = f'<![CDATA[{_escape_cdata(body)}]]>'
    else:
        body = _escape(body)
    return f'{" " * indent}<{tag}>{body}</{tag}>'


def _clean(text: str) -> str:
    """混进一个控制字符就会让整份 nfo 无法解析，影片在片库里凭空消失"""
    return str(text or '').translate(_ILLEGAL).strip()


def _escape(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _escape_cdata(text: str) -> str:
    return text.replace(']]>', ']]]]><![CDATA[>')
