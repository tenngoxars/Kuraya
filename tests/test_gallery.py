# -*- coding: utf-8 -*-
"""
片库页面生成产物契约：分批渲染所需的结构必须存在于生成的 index.html。
直接调用 gallery 函数（与生产路径一致），不走裸脚本子进程。

    python -m unittest discover tests
"""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from kuraya import gallery

NFO = """<?xml version="1.0" encoding="UTF-8" ?>
<movie>
  <title>TEST-001-测试作品</title>
  <num>TEST-001</num>
  <studio>STUDIO-X</studio>
  <premiered>2025-01-01</premiered>
  <runtime>120</runtime>
  <poster>TEST-001-poster.jpg</poster>
  <actor><name>测试演员</name></actor>
</movie>
"""


def build_page():
    """在临时目录造最小影片库并生成页面，返回 index.html 文本"""
    with tempfile.TemporaryDirectory() as tmp:
        cdir = Path(tmp) / '测试演员' / 'TEST-001'
        cdir.mkdir(parents=True)
        (cdir / 'TEST-001.nfo').write_text(NFO, encoding='utf-8')
        (cdir / 'TEST-001-poster.jpg').write_bytes(b'')
        (cdir / 'TEST-001.mp4').write_bytes(b'')
        with redirect_stdout(io.StringIO()):
            code = gallery.main([tmp])
        assert code == 0
        return (Path(tmp) / 'index.html').read_text(encoding='utf-8')


class GalleryContract(unittest.TestCase):
    """分批渲染依赖的产物结构：sentinel 哨兵与首屏批量常量"""

    def test_page_contains_sentinel_and_page_size(self):
        """页面必须含 #sentinel（滚动追加的观察目标）与 PAGE=60 首屏常量，
        缺失会让大库分批渲染静默失效"""
        html = build_page()
        self.assertIn('id="sentinel"', html)
        self.assertIn('const PAGE = 60', html)


if __name__ == '__main__':
    unittest.main()
