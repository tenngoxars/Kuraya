<div align="center">

# ◈ KURAYA 蔵屋

**影片刮削与编目工具**

把散乱的影片文件整理成带封面和元数据的有序收藏，并生成可离线浏览的片库页面。

</div>

---

## 这是什么

一个本地文件整理工具。你把下载好的影片放进一个目录，它会：

1. 从文件名识别番号，联网获取元数据与封面
2. 按 `演员名/番号` 归档，生成 nfo 与海报
3. 重建片库页面 —— 一个可以直接双击打开的 HTML，带搜索、筛选、点封面播放

不提供任何影片下载途径，只处理你已有的本地文件。

## 安装

源码安装需要 Python 3.11 以上：

```
git clone git@github.com:tenngoxars/Kuraya.git && cd Kuraya
pipx install .      # 没有 pipx 则 pip install .
```

免安装的二进制（一行）：

| 平台 | 安装方式 |
|---|---|
| macOS（Apple Silicon） | `brew install tenngoxars/tap/kuraya` |
| Windows | `irm https://raw.githubusercontent.com/tenngoxars/Kuraya/main/install.ps1 \| iex` |
| Linux | `curl -fsSL https://raw.githubusercontent.com/tenngoxars/Kuraya/main/install.sh \| bash` |

macOS 仅提供 Apple Silicon（M1 及以上）包——GitHub 已退役 Intel macOS 构建机。

一键脚本把程序装到 `~/.local/opt/kuraya` 并生成 `kuraya` 命令；若 `~/.local/bin`
不在 PATH，脚本会给出提示，也可用 `KURAYA_UPDATE_RC=1` 让脚本自动写入 shell 配置。

配置文件的位置随安装方式而定：

| 安装方式 | `设置.ini` 位置 |
|---|---|
| 命令行安装（macOS / Linux） | `~/.config/kuraya/` |
| 命令行安装（Windows） | `%APPDATA%\Kuraya\` |
| 二进制安装（brew / 一键脚本 / Kuraya.exe） | 可执行文件旁边（brew 升级会重置） |
| 源码目录里直接跑 | 仓库根目录 |

## 快速开始

1. 指定影片库位置：`kuraya config --set-library <目录>`，或直接运行 `kuraya` 按提示选择
2. 把影片放进影片库下的 `待整理` 目录
3. 运行 `kuraya`，选择「刮削入库」

完成后打开影片库里的 `index.html` 即可浏览。

## 使用方式

双击运行进入菜单：

```
◈  K U R A Y A   蔵屋                                 v0.1.0
────────────────────────────────────────────────────────────
  影片库  D:\Media\Library                          100 部
  待整理  D:\Media\Library\待整理                   2 个文件
────────────────────────────────────────────────────────────
  1  刮削入库      处理待整理目录并归入片库
  2  重建页面      重新扫描片库并生成 index.html
  3  打开片库      在浏览器中查看
  4  设置          影片库位置、待整理目录、播放器
  0  退出
```

也可以用命令行，便于脚本与计划任务调用：

```
kuraya                     完整流程：刮削 → 清理 → 重建页面
kuraya scrape --limit 3    只刮削前 3 部，用于试跑
kuraya rebuild             只重建片库页面
kuraya selftest            核对数据源解析规则是否仍有效
kuraya config              查看配置
kuraya --dry-run           只显示将要处理的内容，不改动文件
kuraya --quiet --yes       精简输出、不等待按键，供计划任务使用
```

退出码：`0` 成功 · `1` 部分失败 · `2` 配置错误。

## 配置

菜单「设置」可改影片库、待整理目录与播放器；其余选项直接编辑 `设置.ini`
（位置见上文「安装」，格式见 [设置.example.ini](设置.example.ini)）：

| 小节 | 项 | 说明 |
|---|---|---|
| `[刮削]` | `间隔秒数` | 每部之间的请求间隔，默认 3。填 0 不等待，但可能被数据源限流 |

## 文件命名

程序从文件名中提取番号，站点前缀、方括号段与画质编码标记会被忽略，
以下后缀识别为版本标记后按原版番号查询：

| 后缀 | 含义 |
|---|---|
| `-C` `ch` | 中文字幕 |
| `-UC` `-U` | 无码流出 |
| `-4K` | 高清版本 |
| `-CD1` `-CD2` | 多集分卷 |

例如 `example.com@XXX-000-C.mp4` 会被识别为 `XXX-000`，归档后：

```
影片库/<演员名>/XXX-000/
  XXX-000-C.mp4        影片本体，保留版本标记
  XXX-000-C.nfo        元数据，与影片本体成对
  XXX-000-C-poster.jpg 竖版海报
  XXX-000-C-fanart.jpg 横版封面
  XXX-000-C-thumb.jpg
  XXX-000-C.srt        原目录有同名字幕则一并搬入
```

`-4K` 不进文件名，只作为 nfo 里的一个标签。多集分卷各自带 `-CD1` `-CD2`，共用同一套图片。

## 播放

点封面即可用本机播放器打开：Windows 首次运行自动注册 `kuraya:` 协议（被安全软件
拦截时执行 `kuraya register` 后重建页面重试）；macOS 首次运行自动把随包的壳 app
（Kuraya.app）装入 `~/Applications` 并注册协议；Linux 由安装脚本注册协议处理器。
协议不可用时点封面降级为复制路径，也可 `kuraya play <路径>` 播放。

播放器在「设置」中指定，留空用系统默认。

## 支持范围

只处理**正规厂商发行的有码影片**（「字母-数字」固定番号，如 `XXX-000`），数据来自 javbus，单源不聚合。

以下类型**不在支持范围内，也不计划支持**：

| 类型 | 例 |
|---|---|
| 素人 / 企划系 | SIRO、200GANA |
| 个人投稿 | FC2、Heyzo |
| 无码 | Carib、1Pondo、10musume |
| 无固定番号 | 自制、合集、剪辑 |

这类文件放进待整理目录会原样留下，不做改动。

刮不到先跑 `kuraya selftest`，能分清是站点改版还是番号本身不在收录范围。

同样不做：在线播放、影片下载、字幕匹配、元数据翻译。

## 已知限制

- **演员名为繁体中文**，不做繁简转换（永久限制）
- **站点改版会导致刮削失效**，届时更新 `kuraya/media/javbus.py` 顶部的解析规则
- `-UC` / `-C` 等版本刮到的是原版元数据，数据源通常没有对应条目
- **点封面播放依赖协议注册**：Windows 自动注册；macOS 需壳 app、Linux 需协议处理器（安装命令自动完成），缺失时降级为复制路径，可用 `kuraya play` 播放

## 从源码运行

```
pip install -r requirements.txt
python -m kuraya
```

跑测试：

```
python -m unittest discover tests
```

自行打包：

| 平台 | 命令 | 产物 |
|---|---|---|
| Windows | `build.bat` / `release.bat` | `dist\Kuraya\` / 发布 zip |
| macOS / Linux | `./build.sh` / `./release.sh` | `dist/Kuraya/` / 发布 zip |

发布走 GitHub tag（`v*`）：流水线自动构建三平台包（mac 仅 Apple Silicon）、建 Release
并同步更新 homebrew tap 公式。

打包使用 PyInstaller 的 onedir 模式。部分杀毒软件对 PyInstaller 产物存在误报，这是该工具的普遍现象，可加入白名单。

## 许可

以 **MIT** 发布，完整许可证见 [LICENSE](LICENSE)。

## 声明

本工具仅用于整理用户已合法持有的本地影片文件，不提供、不索引、不分发任何影片内容。

使用者应遵守所在地区的法律法规，并自行承担使用过程中产生的一切责任。请勿传播整理前后的文件及由本工具生成的元数据。
