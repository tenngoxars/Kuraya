#!/usr/bin/env bash
# 构建并打包发布用 zip, 附带 SHA256。产物: dist/Kuraya-<版本>-mac-<架构>.zip
# 与 release.bat 流程对齐。用法: ./release.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "  [1/3] Building"
./build.sh || exit 1
if [ ! -x "dist/Kuraya/Kuraya" ]; then
    echo "  [ERROR] Build produced no executable."
    exit 1
fi

echo "  [2/3] Packing"
VER=$(sed -n "s/.*__version__ = '\([^']*\)'.*/\1/p" kuraya/__init__.py)
[ -n "$VER" ] || { echo "  [ERROR] 无法从 kuraya/__init__.py 读取版本号"; exit 1; }
case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux) OS=linux ;;
  *) echo "  [ERROR] 不支持的平台: $(uname -s)"; exit 1 ;;
esac
ARCH=$(uname -m)
ZIP="Kuraya-${VER}-${OS}-${ARCH}.zip"
rm -f "dist/$ZIP"
# mac 产物带 Kuraya.app（点击封面播放用），Linux/Windows 没有
if [ -d dist/Kuraya.app ]; then
    (cd dist && zip -rq "$ZIP" Kuraya Kuraya.app)
else
    (cd dist && zip -rq "$ZIP" Kuraya)
fi

echo "  [3/3] Hashing"
shasum -a 256 "dist/$ZIP" | tee dist/SHA256.txt

echo
echo "  Package : dist/$ZIP"
echo "  上传 zip 作为 GitHub Release 资产,"
echo "  再把 URL 与哈希填入 packaging/homebrew/kuraya.rb 后发布 tap。"
