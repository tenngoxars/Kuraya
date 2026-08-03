# -*- coding: utf-8 -*-
"""
引擎里流转的数据形状。

番号识别的结果、数据源返回的元数据、产出的图片、给界面的进度事件，全部在此定型。
各模块之间只传这些类型，不传裸 dict —— 无类型的字典穿过整条流水线时，每一站都得
先确认键在不在、值是不是空串，这类校验代码会占掉相当一部分篇幅。

规格见 .agentdocs/spec/引擎行为规格.md
"""
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


# ---------- 配置 ----------

@dataclass(frozen=True)
class Settings:
    """
    引擎跑一批需要知道的全部信息。作为参数逐层传入，不做单例、不做全局。

    由 kuraya/settings.py 从「设置.ini」读出后构造。
    失败的影片一律留在原地，因此没有「失败搬去哪里」这一项。
    """
    library: Path
    source: Path
    sleep: float = 3.0
    limit: int = 0
    dry_run: bool = False


# ---------- 版本特征 ----------

@dataclass(frozen=True)
class Edition:
    """
    影片的版本特征，全部由文件名判定，决定归档后的文件名标记与 nfo 里的额外标签。

    part 为 0 表示不分卷。leak_mark 保留文件名里实际出现的那一种（-UC 或 -U），
    归档时原样沿用，不做归一。
    """
    part: int = 0
    chinese_sub: bool = False
    leaked: bool = False
    leak_mark: str = ''
    hd4k: bool = False

    @property
    def suffix(self) -> str:
        """
        影片本体与 nfo 的名字里跟在番号后面的标记，顺序固定：分卷 → 中字 → 流出。

        4K 不进文件名，只作为 nfo 标签 —— 它描述的是画质而非版本，
        同一部影片的 4K 版与普通版不应被当成两个条目。
        """
        out = ''
        if self.part:
            out += f'-CD{self.part}'
        if self.chinese_sub:
            out += '-C'
        if self.leaked:
            out += self.leak_mark or '-UC'
        return out

    @property
    def image_suffix(self) -> str:
        """图片名用的标记。分卷共用一套图，因此去掉 -CDn。"""
        return Edition(
            chinese_sub=self.chinese_sub,
            leaked=self.leaked,
            leak_mark=self.leak_mark,
        ).suffix

    @property
    def extra_tags(self) -> tuple[str, ...]:
        """写进 nfo 的额外标签，排在数据源给的类别之前。"""
        tags = []
        if self.chinese_sub:
            tags.append('中文字幕')
        if self.hd4k:
            tags.append('4k')
        return tuple(tags)


@dataclass(frozen=True)
class FileId:
    """番号识别的结果。识别不出时调用方拿到的是 None，不是空 FileId。"""
    number: str
    edition: Edition

    def stem(self) -> str:
        """归档后影片与 nfo 的文件名主干"""
        return self.number + self.edition.suffix

    def image_stem(self) -> str:
        """归档后三张图的文件名主干"""
        return self.number + self.edition.image_suffix


# ---------- 元数据 ----------

ANONYMOUS = '佚名'

# 目录名里不能出现的字符，出现即剔除
_ILLEGAL = str.maketrans('', '', '\\/:*?"<>|')


@dataclass(frozen=True)
class Movie:
    """
    数据源返回的一部影片。字段集由 nfo 契约决定，不多存数据源上用不到的东西。

    number 与 title 之外的字段都允许为空 —— javbus 的条目并不总是齐全，
    缺字段不构成失败。
    """
    number: str
    title: str
    cover_url: str
    actors: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    release: str = ''
    runtime: str = ''
    studio: str = ''
    label: str = ''
    series: str = ''
    director: str = ''
    outline: str = ''

    @property
    def year(self) -> str:
        """发行年份，取自 release 的前四位"""
        return self.release[:4] if len(self.release) >= 4 else ''

    @property
    def folder_actor(self) -> str:
        """
        归档目录名。多演员取第一个，未标注则填占位名 —— 否则会归到空目录名下，
        路径拼接会把它当成绝对路径的根。
        """
        name = self.actors[0] if self.actors else ANONYMOUS
        cleaned = name.translate(_ILLEGAL).strip().strip('.')
        return cleaned or ANONYMOUS


@dataclass(frozen=True)
class Assets:
    """归档目录下三张图的文件名，写进 nfo 的也是这三个相对名"""
    poster: str
    fanart: str
    thumb: str


# ---------- 进度事件 ----------

class Stage(Enum):
    """转轮上显示的当前动作"""
    METADATA = auto()
    COVER = auto()
    CROP = auto()
    ARCHIVE = auto()


class FailReason(Enum):
    """
    失败原因。用枚举而非自由文本：界面据此决定配色与措辞，
    引擎不掺和呈现。

    NETWORK 与 NOT_FOUND 分开：前者下次重跑就好，后者是不在支持范围内，
    重跑多少次都一样。合成一个的话，用户没法判断该不该再试。
    """
    NO_NUMBER = auto()
    NOT_FOUND = auto()
    NETWORK = auto()
    COVER_FAILED = auto()
    ARCHIVE_FAILED = auto()


@dataclass(frozen=True)
class Found:
    count: int


@dataclass(frozen=True)
class Started:
    number: str
    index: int


@dataclass(frozen=True)
class Fetched:
    """元数据到手。在抓取成功那一刻发出，界面把它排在哪一行是界面的事"""
    movie: Movie


@dataclass(frozen=True)
class Probing:
    stage: Stage


@dataclass(frozen=True)
class CoverReady:
    size_kb: int


@dataclass(frozen=True)
class PosterReady:
    pass


@dataclass(frozen=True)
class Stored:
    path: Path
    elapsed: float


@dataclass(frozen=True)
class Failed:
    number: str
    reason: FailReason


Event = (Found | Started | Fetched | Probing | CoverReady
         | PosterReady | Stored | Failed)
