# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置。

用 onedir 而非单文件：单文件模式每次运行都会把内容解压到临时目录，
界面模板要按路径读取，临时目录会让这些路径在运行间变化，且拖慢启动。
"""
import sys

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 界面模板与图标：gallery 生成页面时按路径读取。
        # 位置必须与 settings.WEB_DIR 一致，即包内的 kuraya/web
        ('kuraya/web', 'kuraya/web'),
        # 配置模板：首次运行时供用户参考
        ('设置.example.ini', '.'),
    ],
    # 刮削引擎已是正常的包，PyInstaller 能静态分析，无需在此声明。
    # 剩下的只有靠字符串引用、静态分析看不见的两个模块。
    hiddenimports=[
        'kuraya.gallery',
        'kuraya.cleanup',
    ],
    hookspath=[],
    runtime_hooks=[],
    # 目录选择框：Windows 走 PowerShell 对话框，不需要 tkinter（带上徒增体积）；
    # mac/Linux 走 tkinter，必须打进包，这里只对 Windows 排除
    excludes=['matplotlib', 'numpy', 'pytest'] + (['tkinter'] if sys.platform == 'win32' else []),
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Kuraya',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX 压缩会显著提高杀软误报率
    console=True,           # 进度界面需要控制台
    disable_windowed_traceback=False,
    # mac 的 EXE 图标要求 .icns（build.sh 会从 png 生成），Windows 用 .ico
    icon='kuraya/web/favicon.icns' if sys.platform == 'darwin'
    else 'kuraya/web/favicon.ico',
    # Windows 版本资源（exe 属性里的版本信息）；其他平台忽略
    version='packaging/version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Kuraya',
)
