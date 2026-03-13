#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本说明：
- 扫描指定目录下的全部 3MF 文件，按模型自动整理到独立文件夹。
- 同模型的不同配置放入同一目录，并按配置名重命名文件。
- 完全重复的配置会集中放入根目录下的重复目录，并输出文本总结报告。

用法：
  python3 scripts/organize_local_3mf.py
  python3 scripts/organize_local_3mf.py --root D:\\path\\to\\folder
  python3 scripts/organize_local_3mf.py --root D:\\path\\to\\folder --dry-run
  python3 scripts/organize_local_3mf.py --root D:\\path\\to\\folder --mode copy
  python3 scripts/organize_local_3mf.py --root D:\\path\\to\\folder --limit 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from local_3mf_organizer import DEFAULT_ORGANIZER_CONFIG, run_local_3mf_organizer  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="整理本地 3MF 文件")
    parser.add_argument("--root", default=".", help="待整理的根目录，默认当前目录")
    parser.add_argument("--mode", choices=["move", "copy"], default=DEFAULT_ORGANIZER_CONFIG["mode"], help="整理时移动还是复制，默认 move")
    parser.add_argument("--dry-run", action="store_true", help="只分析和生成报告，不落盘")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 个文件，用于测试")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    report = run_local_3mf_organizer(
        {"root_dir": args.root, "mode": args.mode},
        root_dir=args.root,
        mode=args.mode,
        dry_run=bool(args.dry_run),
        limit=int(args.limit or 0),
    )

    print("")
    print("3MF 整理完成")
    print(f"根目录: {report['root']}")
    print(f"扫描文件: {report['scanned_files']}")
    print(f"模型数量: {report['organized_models']}")
    print(f"配置数量: {report['organized_configs']}")
    print(f"重复数量: {report['duplicate_count']}")
    print(f"失败数量: {report['failed_count']}")
    print(f"整理耗时: {report['duration_text']}")
    print(f"报告文件: {report['report_path']}")
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
