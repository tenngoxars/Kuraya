#!/usr/bin/env python3
"""校验发布 tag 与代码内版本号一致，供 CI 四个构建 job 复用。

用法: python packaging/check_tag.py <tag>   # 如 v0.2.0
校验 kuraya/__init__.py 与 packaging/version_info.txt 都与 tag 一致，
避免发布产物与源码版本错位。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def version_from_init() -> str | None:
    text = (ROOT / 'kuraya/__init__.py').read_text(encoding='utf-8')
    m = re.search(r"__version__\s*=\s*'([^']+)'", text)
    return m.group(1) if m else None


def version_from_version_info() -> str | None:
    text = (ROOT / 'packaging/version_info.txt').read_text(encoding='utf-8')
    m = re.search(r'filevers\s*=\s*\(\s*(\d+),\s*(\d+),\s*(\d+)', text)
    return '.'.join(m.groups()) if m else None


def main() -> int:
    if len(sys.argv) != 2:
        print('用法: python packaging/check_tag.py <tag>', file=sys.stderr)
        return 2
    tag = sys.argv[1]
    if not tag.startswith('v'):
        print(f'tag {tag} 应为 v<版本> 形式', file=sys.stderr)
        return 1
    expected = tag[1:]
    ok = True
    for name, value in [('kuraya/__init__.py', version_from_init()),
                        ('packaging/version_info.txt', version_from_version_info())]:
        if value != expected:
            print(f'{name} 版本 {value} 与 tag {tag} 不一致', file=sys.stderr)
            ok = False
    if ok:
        print(f'tag {tag} 与版本一致')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
