#!/usr/bin/env bash
# macOS / Linux 构建脚本。产物: dist/Kuraya/Kuraya
# 与 build.bat 流程对齐: 环境检查 → spec 自检 → 装依赖 → 构建
# 用法: ./build.sh          (PYTHON=/path/to/python3 可指定解释器, 默认 python3)
set -euo pipefail
cd "$(dirname "$0")"

# 两个临时目录统一由 EXIT trap 清理，任何一步失败都不残留
TMP=""
TMPA=""
cleanup() {
    [ -n "$TMP" ] && rm -rf "$TMP"
    [ -n "$TMPA" ] && rm -rf "$TMPA"
}
trap cleanup EXIT

PY="${PYTHON:-python3}"
VER_OK=$("$PY" -c 'import sys; print(1 if sys.version_info >= (3, 11) else 0)' 2>/dev/null || echo 0)

echo
echo "  [1/6] Checking environment"
if ! command -v "$PY" >/dev/null 2>&1 || [ "$VER_OK" != 1 ]; then
    echo "  [ERROR] Python >= 3.11 required, got $($PY --version 2>&1)."
    echo "          Set PYTHON=/path/to/python3.13 when your default is older."
    exit 1
fi
# mac/Linux 的目录选择框依赖 tkinter；缺它打包出的产物没有选择框
# （只能手动输入路径）。Homebrew/pyenv 编译的 Python 常缺这一项。
if ! "$PY" -c 'import tkinter' >/dev/null 2>&1; then
    echo "  [WARN] 当前 Python 缺少 tkinter，产物将没有目录选择框。"
    echo "         可用 PYTHON=/usr/bin/python3 等带 tkinter 的解释器重新构建。"
fi

echo "  [2/6] Preparing app icon"
if [ "$(uname)" = Darwin ] && [ ! -f kuraya/web/favicon.icns ]; then
    TMP=$(mktemp -d)
    ICONSET="$TMP/kuraya.iconset"
    mkdir -p "$ICONSET"
    for S in 16 32 128 256 512; do
        sips -z "$S" "$S" kuraya/web/apple-touch-icon.png \
            --out "$ICONSET/icon_${S}x${S}.png" >/dev/null
        D=$((S * 2))
        sips -z "$D" "$D" kuraya/web/apple-touch-icon.png \
            --out "$ICONSET/icon_${S}x${S}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o kuraya/web/favicon.icns
    echo "      generated kuraya/web/favicon.icns"
else
    echo "      (skip)"
fi

echo "  [3/6] Verifying spec hiddenimports"
"$PY" packaging/check_spec.py

echo "  [4/6] Installing build dependencies"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q pyinstaller -r requirements.txt

echo "  [5/6] Building"
rm -rf build dist
"$PY" -m PyInstaller --clean --noconfirm kuraya.spec

if [ "$(uname)" = Darwin ]; then
    echo "  [6/6] Building URL scheme shell app"
    TMPA=$(mktemp -d)
    osacompile -o "$TMPA/Kuraya.app" packaging/scheme_handler.applescript
    # 声明 kuraya: scheme，浏览器点击封面时系统才会唤起本 app
    /usr/libexec/PlistBuddy \
        -c "Add :CFBundleIdentifier string io.kuraya.shell" \
        -c "Set :CFBundleName Kuraya" \
        -c "Add :CFBundleURLTypes array" \
        -c "Add :CFBundleURLTypes:0 dict" \
        -c "Add :CFBundleURLTypes:0:CFBundleURLName string kuraya" \
        -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" \
        -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string kuraya" \
        "$TMPA/Kuraya.app/Contents/Info.plist"
    codesign --force -s - "$TMPA/Kuraya.app"
    cp -R "$TMPA/Kuraya.app" dist/Kuraya.app
    echo "      dist/Kuraya.app (点击封面播放用)"
fi

echo
echo "  Done. Output: dist/Kuraya/Kuraya"
echo "  Distribute the whole \"dist/Kuraya\" folder."
