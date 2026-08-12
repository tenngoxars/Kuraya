# Kuraya 一键安装脚本 (Windows PowerShell 5.1+ / 7)。
# 从 GitHub Releases 拉取最新版, 默认装到 %LOCALAPPDATA%\Programs\Kuraya
# （运行时会弹出目录选择框，也可用环境变量 KURAYA_DIR 指定路径），
# 并把该目录加入用户 PATH, 之后任意终端输入 kuraya 即可。
# 用法:
#   irm https://kuraya.app/install.ps1 | iex
$ErrorActionPreference = 'Stop'

# 界面语言：跟随系统（简体中文 / 繁體中文 / English）
$Lang = 'zh-CN'
$Ui = [System.Globalization.CultureInfo]::CurrentUICulture.Name.ToLower()
if ($Ui -like 'zh-cn*' -or $Ui -like 'zh-sg*') { $Lang = 'zh-CN' }
elseif ($Ui -like 'zh-tw*' -or $Ui -like 'zh-hk*' -or $Ui -like 'zh-mo*') { $Lang = 'zh-TW' }
else { $Lang = 'en' }

$Msg = @{
  'zh-CN' = @{
    fetching    = '  获取最新版本...'
    choosing    = '  选择安装目录（取消则用默认路径）'
    'will-install' = '  将安装到 {0}'
    downloading = '  下载 {0}'
    installing  = '  安装到 {0}'
    'in-use'    = "  安装目录被占用: {0}`n  {1}`n  请退出正在运行的 Kuraya（以及停在该目录里的资源管理器窗口）后重试。原有安装未改动。"
    'path-added'  = '  已把 Kuraya 加入用户 PATH, 请新开一个终端。'
    done        = '  完成! 新终端里运行 kuraya --version 验证。'
  }
  'zh-TW' = @{
    fetching    = '  取得最新版本...'
    choosing    = '  選擇安裝目錄（取消則用預設路徑）'
    'will-install' = '  將安裝到 {0}'
    downloading = '  下載 {0}'
    installing  = '  安裝到 {0}'
    'in-use'    = "  安裝目錄被占用: {0}`n  {1}`n  請結束正在執行的 Kuraya（以及停在該目錄裡的檔案總管視窗）後重試。原有安裝未變動。"
    'path-added'  = '  已把 Kuraya 加入使用者 PATH，請新開一個終端。'
    done        = '  完成！在新終端裡執行 kuraya --version 驗證。'
  }
  'en' = @{
    fetching    = '  Fetching latest version...'
    choosing    = '  Choose the install folder (Cancel uses the default)'
    'will-install' = '  Will install to {0}'
    downloading = '  Downloading {0}'
    installing  = '  Installing to {0}'
    'in-use'    = "  Install folder is in use: {0}`n  {1}`n  Close the running Kuraya (and any Explorer window sitting in that folder), then retry. Your existing install is untouched."
    'path-added'  = '  Added Kuraya to your user PATH — open a new terminal.'
    done        = '  Done! Run kuraya --version in a new terminal to verify.'
  }
}
function Get-Msg([string]$Key, $Arg) {
  $S = $Msg[$Lang][$Key]
  if ($null -ne $Arg) { $S = $S -f $Arg }
  return $S
}

$Repo = 'tenngoxars/Kuraya'
$DefaultDest = Join-Path $env:LOCALAPPDATA 'Programs\Kuraya'
$Dest = $DefaultDest
# 指定了 KURAYA_DIR 则直接用（脚本化场景）；否则弹目录选择框，
# 取消或弹不出（远程会话/无桌面）时退回默认路径
if ($env:KURAYA_DIR) {
    $Dest = $env:KURAYA_DIR
} else {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = (Get-Msg 'choosing')
        $dialog.SelectedPath = $DefaultDest
        if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK `
                -and $dialog.SelectedPath) {
            $Dest = $dialog.SelectedPath.TrimEnd('\')
        }
    } catch {
        # 弹不出选择框的环境直接装默认路径
    }
}
Write-Host (Get-Msg 'will-install' $Dest)

Write-Host (Get-Msg 'fetching')
$Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" `
    -Headers @{ 'User-Agent' = 'kuraya-installer' }
$Ver = $Release.tag_name
$Url = "https://github.com/$Repo/releases/download/$Ver/Kuraya-$($Ver.TrimStart('v'))-win-x64.zip"
Write-Host (Get-Msg 'downloading' $Url)

$Tmp = Join-Path $env:TEMP "kuraya-$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $Tmp | Out-Null
try {
    $Zip = Join-Path $Tmp 'kuraya.zip'
    Invoke-WebRequest -Uri $Url -OutFile $Zip

    Write-Host (Get-Msg 'installing' $Dest)
    # 先解压再动现有安装: 新文件没就位之前不碰旧目录
    Expand-Archive -Path $Zip -DestinationPath $Tmp
    $New = Join-Path $Tmp 'Kuraya'
    if (Test-Path $Dest) {
        # 不能用 Remove-Item 直接删: 运行中的 exe 和已加载的 DLL 删不掉,
        # 其余文件却已经删光, 接着 Move-Item 又因 $Dest 还在而失败 ——
        # 安装目录就此残废。改名则要么整体成功要么整体失败, 失败时原样不动。
        $Old = "$Dest.old"
        if (Test-Path $Old) { Remove-Item $Old -Recurse -Force -ErrorAction SilentlyContinue }
        try {
            Rename-Item -LiteralPath $Dest -NewName (Split-Path $Old -Leaf) -ErrorAction Stop
        } catch {
            # 带上 PowerShell 的原话: 占用之外还可能是权限/ACL, 只给猜测会把人带偏
            Write-Host (Get-Msg 'in-use' @($Dest, $_.Exception.Message))
            exit 1
        }
        try {
            Move-Item -LiteralPath $New -Destination $Dest -ErrorAction Stop
        } catch {
            # 新目录没就位, 把旧的换回去, 不留半残状态
            Rename-Item -LiteralPath $Old -NewName (Split-Path $Dest -Leaf) -ErrorAction SilentlyContinue
            throw
        }
        Remove-Item $Old -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Move-Item -LiteralPath $New -Destination $Dest
    }
} finally {
    Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# 加入用户 PATH(新开的终端生效)
$Path = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($Path -split ';') -notcontains $Dest) {
    [Environment]::SetEnvironmentVariable('Path', "$Path;$Dest", 'User')
    Write-Host (Get-Msg 'path-added')
}

Write-Host (Get-Msg 'done')
