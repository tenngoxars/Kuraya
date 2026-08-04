#!/usr/bin/env bash
# Kuraya 一键安装脚本(Linux 主用, macOS 也可用)。
# 从 GitHub Releases 拉取最新版, 装到 ~/.local/opt/kuraya/, 提供 kuraya 命令。
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/tenngoxars/Kuraya/main/install.sh | bash
set -euo pipefail

REPO=tenngoxars/Kuraya
BIN_DIR="${KURAYA_BIN_DIR:-$HOME/.local/bin}"
# 程序本体放 opt 而非 bin: mac 文件系统大小写不敏感,
# bin/Kuraya 目录与 bin/kuraya 命令 shim 会撞名
DEST="${KURAYA_DIR:-$HOME/.local/opt/kuraya}"

case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux) OS=linux ;;
  *) echo "  不支持的平台: $(uname -s)"; exit 1 ;;
esac
case "$(uname -m)" in
  arm64 | aarch64) ARCH=arm64 ;;
  x86_64 | amd64) ARCH=x86_64 ;;
  *) echo "  不支持的架构: $(uname -m)"; exit 1 ;;
esac

echo "  获取最新版本..."
VER=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | sed -n 's/.*"tag_name": "\([^"]*\)".*/\1/p')
[ -n "$VER" ] || { echo "  获取版本失败, 请检查网络"; exit 1; }

URL="https://github.com/$REPO/releases/download/$VER/Kuraya-${VER#v}-${OS}-${ARCH}.zip"
echo "  下载 $URL"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$URL" -o "$TMP/kuraya.zip"

echo "  安装到 $DEST"
rm -rf "$DEST"
# 程序目录与 shim 目录都要存在（旧版本或新机器上 ~/.local/opt 可能没有）
mkdir -p "$BIN_DIR" "$(dirname "$DEST")"
unzip -q "$TMP/kuraya.zip" -d "$TMP/x"
mv "$TMP/x/Kuraya" "$DEST"
# 壳 app 与程序目录同级放置，程序首次运行会自动装入 ~/Applications
if [ -d "$TMP/x/Kuraya.app" ]; then
    rm -rf "$(dirname "$DEST")/Kuraya.app"
    mv "$TMP/x/Kuraya.app" "$(dirname "$DEST")/Kuraya.app"
fi

# 包装脚本, 与 Homebrew formula 同款做法, 避免符号链接带来的定位问题
cat > "$BIN_DIR/kuraya" <<EOF
#!/bin/sh
exec "$DEST/Kuraya" "\$@"
EOF
chmod +x "$BIN_DIR/kuraya"

# 点击封面播放: mac 上由程序首次运行自装 Kuraya.app; Linux 注册 xdg handler
if [ "$OS" = linux ]; then
    mkdir -p "$HOME/.local/share/applications"
    cat > "$HOME/.local/share/applications/kuraya-handler.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Kuraya
Exec=$DEST/Kuraya --play %u
MimeType=x-scheme-handler/kuraya
NoDisplay=true
EOF
    xdg-mime default kuraya-handler.desktop x-scheme-handler/kuraya 2>/dev/null || true
    echo "  已注册 kuraya: 协议, 片库页面可点击封面播放"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    if [ "${KURAYA_UPDATE_RC:-0}" = "1" ]; then
      RC=""
      case "${SHELL:-}" in
        *zsh) RC="$HOME/.zshrc" ;;
        *bash) RC="$HOME/.bashrc" ;;
      esac
      if [ -n "$RC" ] && [ -f "$RC" ]; then
        printf '\nexport PATH="%s:$PATH"\n' "$BIN_DIR" >> "$RC"
        echo "  已把 $BIN_DIR 写入 $RC"
      else
        echo "  未找到 shell 配置文件，请手动把 $BIN_DIR 加入 PATH"
      fi
    else
      echo "  把 $BIN_DIR 加入 PATH 后即可使用 kuraya 命令:"
      echo "    export PATH=\"$BIN_DIR:\$PATH\""
      echo "  (可把上面这行加进 ~/.bashrc 或 ~/.zshrc 永久生效；"
      echo "   或用 KURAYA_UPDATE_RC=1 重装脚本自动写入)"
    fi
    ;;
esac
echo "  完成! 运行 kuraya --version 验证。"
