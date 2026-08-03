# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置。

用 onedir 而非单文件：单文件模式每次运行都会把内容解压到临时目录，
界面模板要按路径读取，临时目录会让这些路径在运行间变化，且拖慢启动。
"""

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
    excludes=['tkinter', 'matplotlib', 'numpy', 'pytest'],
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
    icon='kuraya/web/favicon.ico',
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
