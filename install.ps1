# Kuraya 一键安装脚本 (Windows PowerShell 5.1+ / 7)。
# 从 GitHub Releases 拉取最新版, 装到 %LOCALAPPDATA%\Programs\Kuraya,
# 并把该目录加入用户 PATH, 之后任意终端输入 kuraya 即可。
# 用法:
#   irm https://raw.githubusercontent.com/tenngoxars/Kuraya/main/install.ps1 | iex
$ErrorActionPreference = 'Stop'

$Repo = 'tenngoxars/Kuraya'
$Dest = Join-Path $env:LOCALAPPDATA 'Programs\Kuraya'

Write-Host '  获取最新版本...'
$Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" `
    -Headers @{ 'User-Agent' = 'kuraya-installer' }
$Ver = $Release.tag_name
$Url = "https://github.com/$Repo/releases/download/$Ver/Kuraya-$($Ver.TrimStart('v'))-win-x64.zip"
Write-Host "  下载 $Url"

$Tmp = Join-Path $env:TEMP "kuraya-$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $Tmp | Out-Null
try {
    $Zip = Join-Path $Tmp 'kuraya.zip'
    Invoke-WebRequest -Uri $Url -OutFile $Zip

    Write-Host "  安装到 $Dest"
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
    Write-Host '  已把 Kuraya 加入用户 PATH, 请新开一个终端。'
}

Write-Host '  完成! 新终端里运行 kuraya --version 验证。'
