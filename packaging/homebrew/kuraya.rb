# typed: strict
# frozen_string_literal: true

# Kuraya Homebrew Formula 模板 —— 让用户一行命令安装:
#
#   1. ./release.sh           构建并打包出 dist/Kuraya-<版本>-mac-arm64.zip + SHA256
#   2. 上传 zip 到 GitHub Releases（如 v0.2.0 的资产 Kuraya-0.2.0-mac-arm64.zip）
#   3. 把 URL 与 sha256 填入下方, 将本文件发布到
#      github.com/tenngoxars/homebrew-tap 仓库的 Formula/kuraya.rb
#   4. 用户安装: brew tap + brew trust tenngoxars/tap + brew install
#      （新版 brew 拒绝加载未信任的第三方 tap, 不 trust 装不上）
#
# 注意: mac 仅 Apple Silicon（GitHub 已无 Intel macOS runner），url/sha256 放顶层
# （Homebrew 不允许 on_arm 块内含 url/sha256，readall --arch=all 会失败）；
# 版本由 URL 自动推断，无需显式 version。
# 发布流水线 update-tap job（配了 TAP_TOKEN 时）自动替换 url/sha256 两行。
# FROZEN 模式下配置写在可执行文件旁, brew upgrade 会重置 设置.ini,
# 因此 formula 里不做持久化处理, 以 caveats 提示用户。
class Kuraya < Formula
  desc "影片刮削与编目工具"
  homepage "https://github.com/tenngoxars/Kuraya"

  url "https://github.com/tenngoxars/Kuraya/releases/download/v0.1.0/Kuraya-0.1.0-mac-arm64.zip"
  sha256 "4952ebf8964ac3f102dc728d01ce40f09b155e3db14a8ac52308d338541c6571"

  def install
    libexec.install Dir["*"]
    # zip 根是 Kuraya/ 目录（含可执行文件与 _internal 依赖），shim 指向可执行文件本身
    bin.write_exec_script libexec/"Kuraya"/"Kuraya"
  end

  def caveats
    <<~EOS
      配置写在程序目录旁的 设置.ini, brew upgrade 会被重置, 升级后重新设置即可。
      点击封面播放: 首次运行 kuraya 会自动把随包的 Kuraya.app 装入 ~/Applications 并注册协议。
    EOS
  end

  test do
    system "#{bin}/Kuraya", "--version"
  end
end
