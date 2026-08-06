# -*- coding: utf-8 -*-
"""
视频格式等跨层常量。叶子模块（零依赖）：settings 与 media 各自引用，
避免 settings 为取一个常量而拖入整个刮削引擎（requests/PIL/lxml）。
新增视频格式只改这一处。
"""
VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.wmv', '.ts', '.mov',
              '.m4v', '.rmvb', '.iso', '.mpg', '.mpeg', '.flv')
