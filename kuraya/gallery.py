# -*- coding: utf-8 -*-
"""
扫描影片库中已生成的 nfo/封面文件，生成静态 HTML 画廊页面。
只引用本地已存在的文件，不抓取/不生成任何图片内容。

用法: python gallery.py <影片库目录>
"""
import os
import sys
import xml.etree.ElementTree as ET
from urllib.parse import quote
import json
from datetime import datetime, timedelta

if len(sys.argv) < 2:
    raise SystemExit('用法: python gallery.py <影片库目录>')
BASE = os.path.abspath(sys.argv[1])
if not os.path.isdir(BASE):
    raise SystemExit(f'影片库目录不存在: {BASE}')

# 非演员目录，扫描时跳过
SKIP = {"待整理", "Kuraya", "kuraya"}
VIDEO_EXTS = (".mp4", ".avi", ".mkv", ".wmv", ".ts", ".mov", ".m4v", ".rmvb")

def rel_url(*parts):
    return "/".join(quote(p) for p in parts)

def abs_path(*parts):
    # 播放用的绝对路径。Windows 上交给 kuraya: 协议，
    # 其他平台页面里只能展示出来供复制，格式按本机来
    path = os.path.join(BASE, *parts)
    return path.replace("/", "\\") if os.name == "nt" else path

items = []
now = datetime.now()

for actress in sorted(os.listdir(BASE)):
    if actress in SKIP:
        continue
    adir = os.path.join(BASE, actress)
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
        studio = gt("studio")
        premiered = gt("premiered") or gt("year")
        runtime = gt("runtime")
        poster = gt("poster", f"{code}-poster.jpg")
        actors = [a.findtext("name", "").strip() for a in root.findall("actor")]
        actors = [a for a in actors if a]
        actor_str = "、".join(actors) if actors else actress

        # 多集影片（-CD1/-CD2 命名）优先取 CD1 作为封面点击播放的入口
        vids = sorted(f for f in os.listdir(cdir) if os.path.splitext(f)[1].lower() in VIDEO_EXTS)
        video_file = next((f for f in vids if "-cd1" in f.lower()), None) or (vids[0] if vids else None)
        if not video_file:
            continue
        video_mtime = os.path.getmtime(os.path.join(cdir, video_file))

        poster_path = os.path.join(cdir, poster)
        if not os.path.isfile(poster_path):
            cand = [f for f in os.listdir(cdir) if f.lower().endswith("-poster.jpg")]
            poster = cand[0] if cand else None

        is_new = video_mtime and (now - datetime.fromtimestamp(video_mtime)) < timedelta(days=7)

        items.append({
            "actress_folder": actress,
            "code": num,
            "studio": studio,
            "date": premiered,
            "runtime": runtime,
            "actors": actor_str,
            "poster_url": rel_url(actress, code, poster) if poster else "",
            "video_path": abs_path(actress, code, video_file),
            "added_ts": video_mtime or 0,
            "is_new": is_new,
        })

# 多人共演的番号可能在好几个女优文件夹里都有nfo，按番号去重，网页里只显示一张卡片
seen_codes = set()
deduped = []
for it in items:
    if it["code"] in seen_codes:
        continue
    seen_codes.add(it["code"])
    deduped.append(it)
items = deduped

print(f"共收录 {len(items)} 部")
# 默认按发行日期新到旧排序（无日期的排最后）
items.sort(key=lambda x: (x["date"] or "0000-00-00"), reverse=True)

# 界面模板与数据分离：模板随包走，数据在此注入，输出为单文件页面
try:
    from kuraya.settings import WEB_DIR
except ImportError:
    # 直接以脚本方式运行时包不在搜索路径上，按本文件位置推算
    WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')


def read_web(name):
    with open(os.path.join(WEB_DIR, name), encoding="utf-8") as fp:
        return fp.read()


# 点封面播放靠 kuraya: 协议，而注册协议要写注册表，只有 Windows 有。
# 其他平台生成的页面改为复制路径，不能留一个点了没反应的封面
play_mode = "protocol" if os.name == "nt" else "copy"

html = read_web("index.html")
html = html.replace("{{STYLE}}", read_web("style.css").rstrip("\n"))
html = html.replace("{{SCRIPT}}", read_web("app.js").rstrip("\n"))
html = html.replace("{{COUNT}}", str(len(items)))
html = html.replace("{{PLAY_MODE}}", play_mode)
html = html.replace("{{DATA_JSON}}", json.dumps(items, ensure_ascii=False))

out_path = os.path.join(BASE, "index.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)
print("已生成", out_path, "大小", os.path.getsize(out_path), "字节")
