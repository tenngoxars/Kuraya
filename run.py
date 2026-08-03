# -*- coding: utf-8 -*-
"""打包入口。PyInstaller 需要一个真实脚本文件作为起点，不能直接用 -m 包。"""
import sys

from kuraya.__main__ import main

if __name__ == '__main__':
    sys.exit(main())
