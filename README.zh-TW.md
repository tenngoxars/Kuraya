<div align="center">

# ◈ KURAYA 蔵屋

**JAV 影片刮削與編目工具**

把散亂的 JAV 影片檔案整理成帶封面與中繼資料的有序收藏，並生成可離線瀏覽的片庫頁面。

**官網：[kuraya.app](https://kuraya.app)**

[简体中文](README.md) | 繁體中文 | [English](README.en.md)

</div>

---

## 這是什麼

一個 JAV 影片本地整理工具。你把下載好的影片放進一個目錄，它會：

1. 從檔案名稱辨識番號，連網取得中繼資料與封面
2. 依 `演員名/番號` 歸檔，生成 nfo 與海報
3. 開啟片庫頁面：可搜尋、篩選、點擊封面播放

**KURAYA 不提供任何影片下載途徑，只處理你已有的本地檔案**。

## 安裝

**推薦命令列安裝**（裝好後在終端輸入 `kuraya` 即可執行）：

- macOS

```
brew tap tenngoxars/tap
brew trust tenngoxars/tap
brew install tenngoxars/tap/kuraya
```

> 新版 Homebrew 會拒絕載入未信任的第三方 tap，`brew trust` 這步不能省（舊版沒有該命令，略過直接安裝即可）。

- Windows

```
irm https://kuraya.app/install.ps1 | iex
```

- Linux

```
curl -fsSL https://kuraya.app/install.sh | bash
```

**升級**：執行 `kuraya update` 自動檢查並安裝新版本（Homebrew 安裝的會自動呼叫 `brew upgrade kuraya`）。

也可以從 [Releases](https://github.com/tenngoxars/Kuraya/releases) 下載對應平台 zip **解壓即用**（免安裝）：Windows 雙擊 `Kuraya\Kuraya.exe`；macOS 雙擊 `Kuraya/Kuraya`（首次開啟右鍵→開啟）；Linux 執行 `Kuraya/Kuraya`。

## 快速開始

1. 指定影片庫位置：`kuraya config --set-library <目錄>`，或直接執行 `kuraya` 依提示選擇
2. 把影片放進影片庫下的 `待整理` 目錄
3. 執行 `kuraya`，選擇「刮削入庫」

完成後開啟影片庫裡的 `index.html` 即可瀏覽。

## 使用方式

雙擊執行進入選單：

```
◈  K U R A Y A   蔵屋                                 v0.3.0
────────────────────────────────────────────────────────────
  影片庫  D:\Media\Library                          100 部
  待整理  D:\Media\Library\待整理                   2 個檔案
────────────────────────────────────────────────────────────
  1  刮削入庫      處理待整理目錄並歸入片庫
  2  重建頁面      重新掃描片庫並生成 index.html
  3  開啟片庫      在瀏覽器中查看
  4  設定          影片庫位置、待整理目錄、播放器
  5  更新          檢查並安裝新版本
  0  退出
```

也可以用命令列，便於腳本與排程工作呼叫：

```
kuraya                     完整流程：刮削 → 清理 → 重建頁面
kuraya scrape --limit 3    只刮削前 3 部，用於試跑
kuraya rebuild             只重建片庫頁面
kuraya selftest            核對資料來源解析規則是否仍有效
kuraya update              檢查並安裝新版本
kuraya config              查看設定
kuraya --dry-run           只顯示將要處理的內容，不改動檔案
kuraya --quiet --yes       精簡輸出、不等待按鍵，供排程工作使用
```

介面語言跟隨系統（簡體中文、繁體中文、英文），也可在「設定 → 語言」裡手動切換；命令列可用 `KURAYA_LANG=zh-CN|zh-TW|en` 臨時指定。

## 支援範圍

只處理**正規廠商發行的 JAV 影片**（「字母-數字」固定番號，如 `XXX-000`），資料來自 javbus，單源不聚合。

以下類型**不在支援範圍內，也不計畫支援**：

| 類型 | 例 |
|---|---|
| 素人 / 企劃系 | SIRO、200GANA |
| 個人投稿 | FC2、Heyzo |
| 無碼 | Carib、1Pondo、10musume |
| 無固定番號 | 自製、合集、剪輯 |

這類檔案放進待整理目錄會原樣留下，不做改動。

刮不到先跑 `kuraya selftest`，能分清是站點改版還是番號本身不在收錄範圍。

同樣不做：線上播放、影片下載、字幕匹配、中繼資料翻譯。

## 從原始碼執行

想從原始碼安裝（需要 Python 3.11 以上）：

```
git clone git@github.com:tenngoxars/Kuraya.git && cd Kuraya
pipx install .
```

直接跑原始碼：

```
pip install -r requirements.txt
python -m kuraya
```

跑測試：

```
python -m unittest discover tests
```

自行打包：

| 平台 | 命令 | 產物 |
|---|---|---|
| Windows | `build.bat` / `release.bat` | `dist\Kuraya\` / 發布 zip |
| macOS / Linux | `./build.sh` / `./release.sh` | `dist/Kuraya/` / 發布 zip |

發布走 GitHub tag（`v*`）：流水線自動建置三平台包（mac 僅 Apple Silicon）、建 Release
並同步更新 homebrew tap 公式。

打包使用 PyInstaller 的 onedir 模式。部分防毒軟體對 PyInstaller 產物存在誤報，這是該工具的普遍現象，可加入白名單。

## 授權

以 **MIT** 發布，完整授權條款見 [LICENSE](LICENSE)。

## 聲明

本工具僅用於整理使用者已合法持有的本地影片檔案，不提供、不索引、不分發任何影片內容。

使用者應遵守所在地區的法律法規，並自行承擔使用過程中產生的一切責任。請勿散播整理前後的檔案及由本工具生成的中繼資料。
