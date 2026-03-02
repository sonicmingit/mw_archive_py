#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量修复模型 meta.json 的 collectDate 字段。

用途：
- 历史数据中可能没有 collectDate，或者格式异常（非整数、<=0）
- 本脚本可按规则回填/覆盖 collectDate，便于后续稳定显示采集时间

默认行为（最安全）：
- 仅修复缺失/无效 collectDate（mode=missing）
- 采集时间来源为 meta.json 文件 mtime（source=mtime）

常用示例：
1) 预览将修改哪些文件（不写入）
   python scripts/fix_collect_date.py --dry-run

2) 实际修复缺失字段（推荐）
   python scripts/fix_collect_date.py

3) 全量覆盖所有模型的 collectDate（谨慎）
   python scripts/fix_collect_date.py --mode all

4) 用 update_time 作为来源（若可解析）
   python scripts/fix_collect_date.py --source update_time

5) 指定模型根目录
   python scripts/fix_collect_date.py --data-root D:\\path\\to\\data
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def resolve_default_data_root(repo_root: Path) -> Path:
    app_dir = repo_root / "app"
    config_path = app_dir / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            raw = str(cfg.get("download_dir") or "").strip()
            if raw:
                p = Path(raw)
                if not p.is_absolute():
                    p = (app_dir / raw).resolve()
                return p
        except Exception:
            pass
    return (app_dir / "data").resolve()


def parse_update_time_ts(value) -> int:
    if not value:
        return 0
    s = str(value).strip()
    if not s:
        return 0
    s = s.replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(s).timestamp())
    except Exception:
        return 0


def list_meta_paths(data_root: Path) -> list[Path]:
    if not data_root.exists():
        return []
    out: list[Path] = []
    for d in sorted(data_root.iterdir()):
        if not d.is_dir():
            continue
        mp = d / "meta.json"
        if mp.exists():
            out.append(mp)
    return out


def pick_collect_ts(meta: dict, meta_path: Path, source: str) -> int:
    mtime_ts = int(meta_path.stat().st_mtime)
    if source == "mtime":
        return mtime_ts
    if source == "update_time":
        ut = parse_update_time_ts(meta.get("update_time"))
        return ut or mtime_ts
    if source == "earliest":
        ut = parse_update_time_ts(meta.get("update_time"))
        return min([x for x in [ut, mtime_ts] if x > 0]) if (ut or mtime_ts) else 0
    return mtime_ts


def is_valid_collect_date(value) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return False


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="批量修复 meta.json 的 collectDate")
    parser.add_argument("--data-root", default="", help="模型根目录（默认 app/config.json 的 download_dir）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写文件")
    parser.add_argument(
        "--mode",
        choices=["missing", "all"],
        default="missing",
        help="missing=仅修复缺失/无效，all=全量覆盖",
    )
    parser.add_argument(
        "--source",
        choices=["mtime", "update_time", "earliest"],
        default="mtime",
        help="collectDate 来源",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root).resolve() if args.data_root else resolve_default_data_root(repo_root)
    print(f"[fix-collect-date] data_root={data_root}")
    print(f"[fix-collect-date] mode={args.mode}, source={args.source}, dry_run={args.dry_run}")

    meta_paths = list_meta_paths(data_root)
    if not meta_paths:
        print("[fix-collect-date] 未找到 meta.json")
        return 1

    total = 0
    changed = 0
    skipped = 0
    failed = 0

    for meta_path in meta_paths:
        total += 1
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("meta.json 不是对象")

            current_ok = is_valid_collect_date(raw.get("collectDate"))
            if args.mode == "missing" and current_ok:
                skipped += 1
                continue

            new_ts = pick_collect_ts(raw, meta_path, args.source)
            if new_ts <= 0:
                skipped += 1
                continue

            old_ts = int(raw.get("collectDate")) if current_ok else None
            if old_ts == new_ts:
                skipped += 1
                continue

            raw["collectDate"] = int(new_ts)
            if args.dry_run:
                print(f"[dry-run] {meta_path.parent.name}: {old_ts} -> {new_ts}")
            else:
                meta_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[ok] {meta_path.parent.name}: {old_ts} -> {new_ts}")
            changed += 1
        except Exception as e:
            failed += 1
            print(f"[fail] {meta_path}: {e}")

    print(
        f"[fix-collect-date] done: total={total}, changed={changed}, "
        f"skipped={skipped}, failed={failed}"
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

