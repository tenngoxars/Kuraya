# Kuraya 一键安装脚本 (Windows PowerShell 5.1+ / 7)。
# 从 GitHub Releases 拉取最新版, 装到 %LOCALAPPDATA%\Programs\Kuraya,
# 并把该目录加入用户 PATH, 之后任意终端输入 kuraya 即可。
# 用法:
#   irm https://raw.githubusercontent.com/tenngoxars/Kuraya/main/install.ps1 | iex
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
    downloading = '  下载 {0}'
    installing  = '  安装到 {0}'
    path-added  = '  已把 Kuraya 加入用户 PATH, 请新开一个终端。'
    done        = '  完成! 新终端里运行 kuraya --version 验证。'
  }
  'zh-TW' = @{
    fetching    = '  取得最新版本...'
    downloading = '  下載 {0}'
    installing  = '  安裝到 {0}'
    path-added  = '  已把 Kuraya 加入使用者 PATH，請新開一個終端。'
    done        = '  完成！在新終端裡執行 kuraya --version 驗證。'
  }
  'en' = @{
    fetching    = '  Fetching latest version...'
    downloading = '  Downloading {0}'
    installing  = '  Installing to {0}'
    path-added  = '  Added Kuraya to your user PATH — open a new terminal.'
    done        = '  Done! Run kuraya --version in a new terminal to verify.'
  }
}
function Get-Msg([string]$Key, $Arg) {
  $S = $Msg[$Lang][$Key]
  if ($null -ne $Arg) { $S = $S -f $Arg }
  return $S
}

$Repo = 'tenngoxars/Kuraya'
$Dest = Join-Path $env:LOCALAPPDATA 'Programs\Kuraya'

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
