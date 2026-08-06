# -*- coding: utf-8 -*-
"""
install.ps1 的静态回归检查。

`irm https://kuraya.app/install.ps1 | iex` 在 Windows PowerShell 5.1
（无 charset 时按 ISO-8859-1 解码）与 7 下都必须能解析运行，因此该文件
不能依赖 BOM 或编码环境，也不能在哈希字面量里用带连字符的裸键
（`path-added` 会被解析为 `path -added`，报 MissingEqualsInHashLiteral）。

    python -m unittest discover tests
"""
import re
import unittest
from pathlib import Path

PS1 = Path(__file__).parent.parent / 'install.ps1'
# 哈希字面量条目行：`    key  = '...'`，键不允许出现未加引号的连字符
HASH_ENTRY = re.compile(r'^ {4}[A-Za-z][A-Za-z0-9-]* +=')


class InstallPs1(unittest.TestCase):
    """安装脚本必须能被任意编码环境下的 PowerShell 解析"""

    def test_utf8_without_bom(self):
        """无 UTF-8 BOM：BOM 在 irm|iex 链路下会被解码成命令名前缀"""
        data = PS1.read_bytes()
        self.assertFalse(data.startswith(b'\xef\xbb\xbf'),
                         'install.ps1 不得带 UTF-8 BOM')

    def test_hash_keys_with_hyphen_are_quoted(self):
        """哈希字面量中带连字符的键必须加引号（path-added 曾致解析失败）"""
        for lineno, line in enumerate(PS1.read_text(encoding='utf-8').splitlines(), 1):
            if not HASH_ENTRY.match(line):
                continue
            key = line.strip().split('=', 1)[0].strip()
            self.assertFalse('-' in key,
                             f'第 {lineno} 行哈希键 {key!r} 含连字符但未加引号')

    def test_quote_balance(self):
        """每行单引号成对，避免编码解码差异下字符串提前闭合"""
        for lineno, line in enumerate(PS1.read_text(encoding='utf-8').splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith('#'):
                continue
            self.assertEqual(line.count("'") % 2, 0,
                             f'第 {lineno} 行单引号数量为奇数')


if __name__ == '__main__':
    unittest.main()
