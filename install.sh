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
  *) msg unsupported-platform "$(uname -s)"; exit 1 ;;
esac
case "$(uname -m)" in
  arm64 | aarch64) ARCH=arm64 ;;
  x86_64 | amd64) ARCH=x86_64 ;;
  *) msg unsupported-arch "$(uname -m)"; exit 1 ;;
esac

# 界面语言：跟随系统（简体中文 / 繁體中文 / English）。
# mac 自带 bash 3.2 不支持关联数组，用 case 函数输出对应语言的消息
MSG_LANG=zh_CN
case "${LC_ALL:-${LANG:-}}" in
  zh_CN*|zh_SG*|zh-Hans*) MSG_LANG=zh_CN ;;
  zh_TW*|zh_HK*|zh_MO*|zh-Hant*) MSG_LANG=zh_TW ;;
  *) MSG_LANG=en ;;
esac

msg() {
  local key="$1"; shift
  case "$key:$MSG_LANG" in
    unsupported-platform:zh_CN) echo "  不支持的平台: $1";;
    unsupported-platform:zh_TW) echo "  不支援的平台: $1";;
    unsupported-platform:*) echo "  Unsupported platform: $1";;
    unsupported-arch:zh_CN) echo "  不支持的架构: $1";;
    unsupported-arch:zh_TW) echo "  不支援的架構: $1";;
    unsupported-arch:*) echo "  Unsupported architecture: $1";;
    fetching:zh_CN) echo "  获取最新版本...";;
    fetching:zh_TW) echo "  取得最新版本...";;
    fetching:*) echo "  Fetching latest version...";;
    fetch-failed:zh_CN) echo "  获取版本失败, 请检查网络";;
    fetch-failed:zh_TW) echo "  取得版本失敗，請檢查網路";;
    fetch-failed:*) echo "  Failed to get the version — check your network";;
    downloading:zh_CN) echo "  下载 $1";;
    downloading:zh_TW) echo "  下載 $1";;
    downloading:*) echo "  Downloading $1";;
    installing:zh_CN) echo "  安装到 $1";;
    installing:zh_TW) echo "  安裝到 $1";;
    installing:*) echo "  Installing to $1";;
    protocol-registered:zh_CN) echo "  已注册 kuraya: 协议, 片库页面可点击封面播放";;
    protocol-registered:zh_TW) echo "  已註冊 kuraya: 協定，片庫頁面可點擊封面播放";;
    protocol-registered:*) echo "  Registered the kuraya: protocol — click covers to play";;
    path-write:zh_CN) echo "  已把 $1 写入 $2";;
    path-write:zh_TW) echo "  已把 $1 寫入 $2";;
    path-write:*) echo "  Wrote $1 to $2";;
    rc-not-found:zh_CN) echo "  未找到 shell 配置文件，请手动把 $1 加入 PATH";;
    rc-not-found:zh_TW) echo "  找不到 shell 設定檔，請手動把 $1 加入 PATH";;
    rc-not-found:*) echo "  No shell config found — add $1 to PATH manually";;
    path-hint:zh_CN) echo "  把 $1 加入 PATH 后即可使用 kuraya 命令:";;
    path-hint:zh_TW) echo "  把 $1 加入 PATH 後即可使用 kuraya 指令:";;
    path-hint:*) echo "  Add $1 to your PATH to use the kuraya command:";;
    path-rc:zh_CN) echo "  (可把上面这行加进 ~/.bashrc 或 ~/.zshrc 永久生效；";;
    path-rc:zh_TW) echo "  (可把上面這行加進 ~/.bashrc 或 ~/.zshrc 永久生效；";;
    path-rc:*) echo "  (Add that line to ~/.bashrc or ~/.zshrc to keep it;";;
    path-rc2:zh_CN) echo "   或用 KURAYA_UPDATE_RC=1 重装脚本自动写入)";;
    path-rc2:zh_TW) echo "   或用 KURAYA_UPDATE_RC=1 重裝腳本自動寫入)";;
    path-rc2:*) echo "   or rerun with KURAYA_UPDATE_RC=1 to write it automatically)";;
    done-msg:zh_CN) echo "  完成! 运行 kuraya --version 验证。";;
    done-msg:zh_TW) echo "  完成！執行 kuraya --version 驗證。";;
    done-msg:*) echo "  Done! Run kuraya --version to verify.";;
  esac
}
msg fetching
VER=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | sed -n 's/.*"tag_name": "\([^"]*\)".*/\1/p')
[ -n "$VER" ] || { msg fetch-failed; exit 1; }

URL="https://github.com/$REPO/releases/download/$VER/Kuraya-${VER#v}-${OS}-${ARCH}.zip"
msg downloading "$URL"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$URL" -o "$TMP/kuraya.zip"

msg installing "$DEST"
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
    msg protocol-registered
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
        msg path-write "$BIN_DIR" "$RC"
      else
        msg rc-not-found "$BIN_DIR"
      fi
    else
      msg path-hint "$BIN_DIR"
      echo "    export PATH=\"$BIN_DIR:\$PATH\""
      msg path-rc
      msg path-rc2
    fi
    ;;
esac
msg done-msg
