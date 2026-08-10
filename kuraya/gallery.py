# -*- coding: utf-8 -*-
"""
扫描影片库中已生成的 nfo/封面文件，生成静态 HTML 画廊页面。
只引用本地已存在的文件，不抓取/不生成任何图片内容。

用法: python gallery.py <影片库目录>
"""
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

# 多语言：裸脚本运行时包不在搜索路径，tr 回退原文、判定表用同值
try:
    from kuraya.i18n import TRADITIONAL_CODES, tr
except ImportError:
    def tr(text, **kw):
        return text.format(**kw) if kw else text
    TRADITIONAL_CODES = ('zh-tw', 'zh-hk', 'zh-mo', 'zh-hant')

# 视频扩展名（与 settings 共用一份，这里保证裸脚本运行也能用）
try:
    from kuraya.settings import VIDEO_EXTS
except ImportError:
    # 直接以脚本方式运行时包不在搜索路径，按同值回退
    VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.wmv', '.ts', '.mov',
                  '.m4v', '.rmvb', '.iso', '.mpg', '.mpeg', '.flv')  # 与 formats.py 同值

# 界面模板随包走；裸脚本运行时按本文件位置推算
try:
    from kuraya.settings import WEB_DIR
except ImportError:
    WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')

# 点封面播放靠 kuraya: 协议，平台是否可用由 protocol.play_mode 判断；
# 不可用时页面降级为复制路径，不留点了没反应的封面
try:
    from kuraya.protocol import play_mode as _resolve_play_mode
    play_mode = _resolve_play_mode()
except ImportError:
    # 裸脚本运行（python gallery.py <目录>）时包不在搜索路径，降级复制
    play_mode = 'copy'

# 非演员目录，扫描时跳过
SKIP = {"待整理", "Kuraya", "kuraya"}


def read_web(name):
    with open(os.path.join(WEB_DIR, name), encoding="utf-8") as fp:
        return fp.read()


def collect(base):
    """扫描库目录收集影片数据，按番号去重并按发行日期新到旧排序"""
    base = os.path.abspath(base)
    items = []

    for actress in sorted(os.listdir(base)):
        if actress in SKIP:
            continue
        adir = os.path.join(base, actress)
        if not os.path.isdir(adir):
            continue
        for code in sorted(os.listdir(adir)):
            cdir = os.path.join(adir, code)
            if not os.path.isdir(cdir):
                continue
            nfo_path = os.path.join(cdir, f"{code}.nfo")
            if not os.path.isfile(nfo_path):
                # 多集(-CD1)或特殊后缀(-4k等)命名的nfo兜底匹配
                cand = [f for f in os.listdir(cdir)
                        if f.lower().endswith(".nfo") and f.upper().startswith(code.upper())]
                cand.sort(key=lambda f: ("cd1" not in f.lower(), f))
                nfo_path = os.path.join(cdir, cand[0]) if cand else None
            if not nfo_path or not os.path.isfile(nfo_path):
                continue
            try:
                root = ET.parse(nfo_path).getroot()
            except Exception:
                continue

            def gt(tag, default=""):
                el = root.find(tag)
                return el.text.strip() if el is not None and el.text else default

            num = gt("num", code)
            label = gt("label")
            director = gt("director")
            premiered = gt("premiered") or gt("year")
            runtime = gt("runtime")
            poster = gt("poster", f"{code}-poster.jpg")
            actors = [a.findtext("name", "").strip() for a in root.findall("actor")]
            actors = [a for a in actors if a]
            actor_str = "、".join(actors) if actors else actress

            # 多集影片（-CD1/-CD2 命名）优先取 CD1 作为封面点击播放的入口
            vids = sorted(f for f in os.listdir(cdir)
                          if os.path.splitext(f)[1].lower() in VIDEO_EXTS)
            video_file = next((f for f in vids if "-cd1" in f.lower()), None) \
                or (vids[0] if vids else None)
            if not video_file:
                continue
            video_mtime = os.path.getmtime(os.path.join(cdir, video_file))

            poster_path = os.path.join(cdir, poster)
            if not os.path.isfile(poster_path):
                cand = [f for f in os.listdir(cdir) if f.lower().endswith("-poster.jpg")]
                poster = cand[0] if cand else None

            items.append({
                "actress_folder": actress,
                "code": num,
                "label": label,
                "director": director,
                "date": premiered,
                "runtime": runtime,
                "actors": actor_str,
                "added_ts": video_mtime or 0,
                # 路径交给 pack/页面按基址现拼，这里不重复计算
                "_dir": code,
                "_video": video_file,
                "_poster": poster or "",
            })

    # 多人共演的番号可能在好几个女优文件夹里都有nfo，按番号去重，
    # 网页里只显示一张卡片
    seen_codes = set()
    deduped = []
    for it in items:
        if it["code"] in seen_codes:
            continue
        seen_codes.add(it["code"])
        deduped.append(it)

    # 默认按发行日期新到旧排序（无日期的排最后）
    deduped.sort(key=lambda x: (x["date"] or "0000-00-00"), reverse=True)
    return deduped


PACK_FIELDS = ["folder", "code", "dir", "label", "director", "date",
               "runtime", "actors", "poster", "video", "added"]


def pack(items):
    """
    列式打包：字段名只写一次，行是纯数组。

    array-of-objects 每条都重复一遍键名，几千部时光键名就占几十万字节；
    影片库基址也在每条 video_path 里重复一遍。改成列式并把基址提到外面，
    实测省七成。相对路径不在这里做百分号编码——一个中日文字符会膨胀成
    九个字符，交给页面用 encodeURIComponent 现算。
    """
    rows = []
    for it in items:
        folder = it["actress_folder"]
        col = {
            "folder": folder,
            "code": it["code"],
            "dir": "" if it["_dir"] == it["code"] else it["_dir"],
            "label": it["label"],
            "director": it["director"],
            "date": it["date"],
            "runtime": it["runtime"],
            "actors": "" if it["actors"] == folder else it["actors"],
            "poster": it["_poster"],
            "video": it["_video"],
            "added": int(it["added_ts"]),
        }
        rows.append([col[f] for f in PACK_FIELDS])
    return rows


def script_json(obj):
    """
    注入 <script> 的 JSON 必须把 < 转义掉。番号/发行商/演员来自第三方数据源，
    其中一个含 </script> 就会提前闭合脚本块——前端脚本被截断，整页只剩空白，
    而且不报任何错。只转 < 就够：脚本块靠 </ 与 <!-- 才能被打断，
    单独的 > 和 & 在脚本内容里没有语法意义。
    \\u003c 在 JSON 与 JS 字符串里都还原成 <，值本身不变。
    """
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def render(base, items):
    """界面模板与数据分离：模板随包走，数据在此注入，输出为单文件页面"""
    html = read_web("index.html")
    html = html.replace("{{STYLE}}", read_web("style.css").rstrip("\n"))
    # 注入顺序：i18n.js（t/UI_LANG 定义）→ state.js（无 DOM 状态函数）→
    # delete.js（删除弹窗与恢复流程）→ app.js（数据解包+渲染）→
    # filters.js（筛选交互，依赖前两者）
    script = "\n".join(read_web(n) for n in
                         ("i18n.js", "state.js", "delete.js", "app.js",
                          "filters.js"))
    script = script.replace("{{TRADITIONAL_CODES}}",
                            json.dumps(TRADITIONAL_CODES))
    script = script.replace("{{PACK_FIELDS}}", script_json(PACK_FIELDS))
    script = script.replace("{{LIB_BASE}}", script_json(
        base.replace("/", "\\") if os.name == "nt" else base))
    script = script.replace("{{PATH_SEP}}",
                            script_json("\\" if os.name == "nt" else "/"))
    html = html.replace("{{SCRIPT}}", script.rstrip("\n"))
    html = html.replace("{{COUNT}}", str(len(items)))
    html = html.replace("{{PLAY_MODE}}", play_mode)
    return html.replace("{{DATA_JSON}}", script_json(pack(items)))


def write_page_atomic(path, html):
    """完整写入临时文件后替换页面，避免浏览器读到半份 HTML。"""
    path = os.fspath(path)
    fd, temp = tempfile.mkstemp(
        prefix=f'.{os.path.basename(path)}.', suffix='.tmp',
        dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(html)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 1:
        print(tr('用法: python gallery.py <影片库目录>'))
        return 2
    base = os.path.abspath(args[0])
    if not os.path.isdir(base):
        print(tr('影片库目录不存在: {base}', base=base))
        return 1

    items = collect(base)
    print(tr('共收录 {n} 部', n=len(items)))
    # 稳定标记供父进程解析（子进程输出会随语言变化，机器接口必须固定）
    print(f'gallery-collected={len(items)}')

    html = render(base, items)
    out_path = os.path.join(base, "index.html")
    write_page_atomic(out_path, html)
    print(tr('已生成 {path}，大小 {size} 字节',
             path=out_path, size=os.path.getsize(out_path)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
