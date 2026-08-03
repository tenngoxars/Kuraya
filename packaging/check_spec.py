# -*- coding: utf-8 -*-
"""打包前自检：确认靠字符串引用的模块都写进了 spec 的 hiddenimports。

`runpy.run_module('kuraya.gallery')` 这类调用里，模块名只以字符串形式出现，
PyInstaller 的静态分析看不见它。遗漏时构建照样成功，却会在用户点到那一步时
报 No module named —— 源码直接运行完全正常，因此必须在构建前拦住。

退出码：0 通过，1 有遗漏。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / 'kuraya'
SPEC = ROOT / 'kuraya.spec'

RUN_MODULE = re.compile(r"run_module\(\s*'([\w.]+)'")


def referenced_by_name():
    found = set()
    for path in PACKAGE.rglob('*.py'):
        if '__pycache__' in path.parts:
            continue
        found.update(RUN_MODULE.findall(path.read_text(encoding='utf-8')))
    return found


def spec_hiddenimports():
    text = SPEC.read_text(encoding='utf-8')
    body = text.split('hiddenimports=[', 1)[1].split(']', 1)[0]
    names = set()
    for line in body.splitlines():
        line = line.split('#', 1)[0]
        names.update(re.findall(r"'([A-Za-z_][\w.]*)'", line))
    return names


def main():
    if not SPEC.is_file():
        print(f'  [ERROR] spec not found: {SPEC}')
        return 1

    need = referenced_by_name()
    missing = sorted(need - spec_hiddenimports())
    if missing:
        print('  [ERROR] kuraya.spec hiddenimports is missing modules that are')
        print('          only referenced by name. The build would succeed but')
        print('          fail at runtime. Add these to hiddenimports:')
        for name in missing:
            print(f'            {name}')
        return 1

    print(f'  hiddenimports covers all {len(need)} string-referenced modules.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
