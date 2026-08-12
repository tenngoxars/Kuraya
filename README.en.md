<div align="center">

# ◈ KURAYA 蔵屋

**JAV movie scraper & cataloger**

Turn scattered JAV movie files into an organized collection with covers and metadata, browsable offline.

**Website: [kuraya.app](https://kuraya.app)**

[简体中文](README.md) | [繁體中文](README.zh-TW.md) | English

</div>

---

## What it is

A local organizer for JAV movies. Drop your downloaded movies into a folder and it will:

1. Recognize the code from the filename and fetch metadata and covers online
2. File them under `Actor\Code`, generating nfo and posters
3. Build a library page: searchable, filterable, click covers to play

**KURAYA does not provide any way to download movies — it only processes files you already own.**

## Install

**Recommended: command line install** (run `kuraya` from any terminal afterwards):

- macOS

```
brew tap tenngoxars/tap
brew trust tenngoxars/tap
brew install tenngoxars/tap/kuraya
```

> Recent Homebrew refuses to load formulae from untrusted third-party taps, so `brew trust` is required (older versions lack the command — just skip it and install).

- Windows

```
irm https://kuraya.app/install.ps1 | iex
```

- Linux

```
curl -fsSL https://kuraya.app/install.sh | bash
```

**Upgrade**: run `kuraya update` to check for and install the new version (Homebrew installs automatically delegate to `brew upgrade kuraya`).

You can also download the zip for your platform from [Releases](https://github.com/tenngoxars/Kuraya/releases) and run it directly (no install): Windows double-click `Kuraya\Kuraya.exe`; macOS double-click `Kuraya/Kuraya` (right-click → Open the first time); Linux run `Kuraya/Kuraya`.

## Quick start

1. Set the library location: `kuraya config --set-library <path>`, or run `kuraya` and follow the prompts
2. Put movies into the `待整理` folder inside your library
3. Run `kuraya` and choose "Scrape & archive"

Open `index.html` in your library to browse.

## Usage

Double-click to enter the menu:

```
◈  K U R A Y A   蔵屋                                 v0.3.0
────────────────────────────────────────────────────────────
  Library  D:\Media\Library                          100 movies
  Pending  D:\Media\Library\待整理                   2 files
────────────────────────────────────────────────────────────
  1  Scrape & archive  Process the pending folder and archive into the library
  2  Rebuild page      Rescan the library and regenerate index.html
  3  Open library      View in browser
  4  Settings          Library, pending folder, player
  5  Update            Check for and install the new version
  0  Quit
```

Or use the command line, for scripts and scheduled tasks:

```
kuraya                      full flow: scrape → clean → rebuild page
kuraya scrape --limit 3     scrape only the first 3 items, for a trial run
kuraya rebuild              rebuild the library page only
kuraya selftest             check whether the data-source parsing rules still work
kuraya update               check for and install the new version
kuraya config               view or modify the configuration
kuraya --dry-run            only show what would be done; don't modify files
kuraya --quiet --yes        minimal output, no key press at the end (for scheduled tasks)
```

The interface language follows your system (Simplified Chinese, Traditional Chinese, English) and can be switched manually under Settings → Language; the CLI also accepts `KURAYA_LANG=zh-CN|zh-TW|en` for a one-off override.

## Supported scope

Only **JAV movies from official studios** (fixed `letters-digits` codes like `XXX-000`), sourced from javbus, single source without aggregation.

The following are **not supported and not planned**:

| Type | Examples |
|---|---|
| Amateur / studio-independent | SIRO, 200GANA |
| Individual uploads | FC2, Heyzo |
| Uncensored | Carib, 1Pondo, 10musume |
| No fixed code | Self-made, compilations, edits |

Such files are left untouched in the pending folder.

If scraping fails, run `kuraya selftest` first to tell whether the site changed or the code simply isn't covered.

Also not included: online playback, movie downloading, subtitle matching, metadata translation.

## Running from source

From source (requires Python 3.11+):

```
git clone git@github.com:tenngoxars/Kuraya.git && cd Kuraya
pipx install .
```

Or run directly:

```
pip install -r requirements.txt
python -m kuraya
```

Run the tests:

```
python -m unittest discover tests
```

Build your own packages:

| Platform | Command | Output |
|---|---|---|
| Windows | `build.bat` / `release.bat` | `dist\Kuraya\` / release zip |
| macOS / Linux | `./build.sh` / `./release.sh` | `dist/Kuraya/` / release zip |

Releases are driven by GitHub tags (`v*`): the pipeline builds all three platform packages (mac: Apple Silicon only), creates the Release and updates the Homebrew tap formula.

Packaging uses PyInstaller's onedir mode. Some antivirus software false-positives PyInstaller builds — a common issue with this tool; add it to your allowlist.

## License

Released under the **MIT** license; see [LICENSE](LICENSE) for details.

## Disclaimer

This tool only organizes local movie files the user legally owns. It does not provide, index, or distribute any movie content.

Users are responsible for complying with local laws and regulations. Please do not redistribute files or the metadata this tool generates.
