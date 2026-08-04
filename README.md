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
3. 打开片库页面：可搜索、筛选、点击封面播放

**KURAYA 不提供任何影片下载途径，只处理你已有的本地文件**。

## 安装

命令行安装：

**macOS**（仅 Apple Silicon）：

```
brew install tenngoxars/tap/kuraya
```

升级后第一次启动会比平时慢十几秒（macOS 校验新程序），之后恢复正常。

**Windows**：

```
irm https://raw.githubusercontent.com/tenngoxars/Kuraya/main/install.ps1 | iex
```

**Linux**：

```
curl -fsSL https://raw.githubusercontent.com/tenngoxars/Kuraya/main/install.sh | bash
```

## 快速开始

1. 指定影片库位置：`kuraya config --set-library <目录>`，或直接运行 `kuraya` 按提示选择
2. 把影片放进影片库下的 `待整理` 目录
3. 运行 `kuraya`，选择「刮削入库」

完成后打开影片库里的 `index.html` 即可浏览。

## 使用方式

双击运行进入菜单：

```
◈  K U R A Y A   蔵屋                                 v0.3.0
────────────────────────────────────────────────────────────
  影片库  D:\Media\Library                          100 部
  待整理  D:\Media\Library\待整理                   2 个文件
────────────────────────────────────────────────────────────
  1  刮削入库      处理待整理目录并归入片库
  2  重建页面      重新扫描片库并生成 index.html
  3  打开片库      在浏览器中查看
  4  设置          影片库位置、待整理目录、播放器
  5  更新          检查并安装新版本
  0  退出
```

也可以用命令行，便于脚本与计划任务调用：

```
kuraya                     完整流程：刮削 → 清理 → 重建页面
kuraya scrape --limit 3    只刮削前 3 部，用于试跑
kuraya rebuild             只重建片库页面
kuraya selftest            核对数据源解析规则是否仍有效
kuraya update              检查并安装新版本
kuraya config              查看配置
kuraya --dry-run           只显示将要处理的内容，不改动文件
kuraya --quiet --yes       精简输出、不等待按键，供计划任务使用
```

界面语言跟随系统：系统语言为繁体中文（港台澳）时显示繁体，其他语言显示英文，简体中文为默认。

## 支持范围

只处理**正规厂商发行的影片**（「字母-数字」固定番号，如 `XXX-000`），数据来自 javbus，单源不聚合。

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

## 从源码运行

想从源码安装（需要 Python 3.11 以上）：

```
git clone git@github.com:tenngoxars/Kuraya.git && cd Kuraya
pipx install .
```

直接跑源码：

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
