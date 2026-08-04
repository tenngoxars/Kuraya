# -*- coding: utf-8 -*-
"""
调用系统原生的文件/目录选择框。

Windows 走 PowerShell 的 Windows.Forms 对话框；macOS 走 osascript 原生面板
（NSOpenPanel，不依赖 tkinter——CI 打包的 Tk 在部分系统上初始化挂起）；
Linux 走 tkinter。选择框全部不可用时界面降级为终端手动输入路径。

直接运行本文件可做诊断： python -m kuraya.picker
"""
import os
import subprocess
import sys

# 用一个 TopMost 窗体作为宿主，避免对话框被浏览器窗口盖住。
# 必须先 Show 再 Hide，让窗体真正创建出句柄，否则 ShowDialog 会抛异常。
_PS = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms | Out-Null
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.Opacity = 0
$owner.Show()
$owner.Hide()
{dialog}
$owner.Dispose()
"""

_FOLDER = """
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = '{title}'
$d.ShowNewFolderButton = $true
if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {{
    [Console]::Out.WriteLine($d.SelectedPath)
}}
"""

_FILE = """
$d = New-Object System.Windows.Forms.OpenFileDialog
$d.Title = '{title}'
$d.Filter = '可执行文件 (*.exe)|*.exe|所有文件 (*.*)|*.*'
if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {{
    [Console]::Out.WriteLine($d.FileName)
}}
"""


def _powershell(script):
    """返回 (输出, 错误说明)。过程会打印到服务窗口，便于排查。"""
    for exe in ('powershell', 'pwsh'):
        print(f'  [选择框] 尝试用 {exe} 启动...', flush=True)
        try:
            proc = subprocess.run(
                [exe, '-NoProfile', '-STA', '-Command', script],
                capture_output=True, text=True, encoding='utf-8',
                errors='replace', timeout=300,
            )
        except FileNotFoundError:
            print(f'  [选择框] 找不到 {exe}，换下一个', flush=True)
            continue
        except subprocess.TimeoutExpired:
            return '', '选择框超时未关闭'
        except Exception as exc:
            print(f'  [选择框] 启动失败 {type(exc).__name__}: {exc}', flush=True)
            return '', f'{type(exc).__name__}: {exc}'

        out = (proc.stdout or '').strip()
        err = (proc.stderr or '').strip()
        print(f'  [选择框] 退出码={proc.returncode} '
              f'输出={out!r} 错误={err[:200]!r}', flush=True)
        if out:
            return out, ''
        return '', err
    return '', '系统中找不到 powershell'


def _osascript(kind, title):
    """macOS 原生目录/文件面板（NSOpenPanel），不依赖 tkinter——
    CI 打包的 Tk framework 在部分系统上初始化会挂起，弹不出窗口。"""
    prompt = title.replace('"', "'")
    if kind == 'folder':
        script = f'POSIX path of (choose folder with prompt "{prompt}")'
    else:
        script = f'POSIX path of (choose file with prompt "{prompt}")'
    try:
        out = subprocess.run(['osascript', '-e', script],
                             capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return '', '选择框超时未关闭'
    except (OSError, subprocess.SubprocessError) as exc:
        return '', f'{type(exc).__name__}: {exc}'
    path = out.stdout.strip()
    if out.returncode == 0 and path:
        return path, ''
    err = (out.stderr or '').strip()
    # 用户取消：osascript 退出 1 且提示 User canceled，与「未选择」同义
    if 'User canceled' in err:
        return '', ''
    return '', err or f'osascript 退出码 {out.returncode}'


def _tk(kind, title):
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = (filedialog.askdirectory(title=title) if kind == 'folder'
                else filedialog.askopenfilename(title=title))
        root.destroy()
        return path or '', ''
    except Exception as exc:
        return '', f'{type(exc).__name__}: {exc}'


def pick(kind='folder', title='请选择'):
    """弹出选择框。返回 (路径, 错误)，用户取消时两者都为空。"""
    if os.name == 'nt':
        body = (_FOLDER if kind == 'folder' else _FILE).format(title=title)
        path, err = _powershell(_PS.format(dialog=body))
        if path:
            return os.path.normpath(path), ''
        if err:
            return '', err
        return '', ''
    if sys.platform == 'darwin':
        return _osascript(kind, title)
    return _tk(kind, title)


if __name__ == '__main__':
    print('正在弹出目录选择框，请查看是否出现窗口...')
    path, err = pick('folder', '诊断测试')
    print('  选中路径:', path or '(空)')
    print('  错误信息:', err or '(无)')
