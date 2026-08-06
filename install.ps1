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
    'path-added'  = '  已把 Kuraya 加入用户 PATH, 请新开一个终端。'
    done        = '  完成! 新终端里运行 kuraya --version 验证。'
  }
  'zh-TW' = @{
    fetching    = '  取得最新版本...'
    choosing    = '  選擇安裝目錄（取消則用預設路徑）'
    'will-install' = '  將安裝到 {0}'
    downloading = '  下載 {0}'
    installing  = '  安裝到 {0}'
    'path-added'  = '  已把 Kuraya 加入使用者 PATH，請新開一個終端。'
    done        = '  完成！在新終端裡執行 kuraya --version 驗證。'
  }
  'en' = @{
    fetching    = '  Fetching latest version...'
    choosing    = '  Choose the install folder (Cancel uses the default)'
    'will-install' = '  Will install to {0}'
    downloading = '  Downloading {0}'
    installing  = '  Installing to {0}'
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
    if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }
    Expand-Archive -Path $Zip -DestinationPath $Tmp
    Move-Item (Join-Path $Tmp 'Kuraya') $Dest
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
