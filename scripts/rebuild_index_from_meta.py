#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
根据已有 meta.json 重新生成 index.html（v2 离线页）

特点：
- 不重新下载任何文件
- 不改动 images/instances/file 等目录内容
- 默认保留旧版 index.html（v1.0）为 index_v1.0.html，再写入新版 index.html
- 默认增量重建：仅当 meta 或前端模板/css/js 更新后才重建，速度更快

用法示例：
1) 仅预览将处理哪些目录（不写文件）
   python scripts/rebuild_index_from_meta.py --dry-run

2) 实际执行：保留旧版 index，再生成新版 index.html
   python scripts/rebuild_index_from_meta.py

3) 指定模型根目录（例如你有自定义 data 目录）
   python scripts/rebuild_index_from_meta.py --data-root D:\\path\\to\\data

4) 额外生成 index.html.bak 备份（可选）
   python scripts/rebuild_index_from_meta.py --backup

5) 强制全量重建（忽略时间戳比较）
   python scripts/rebuild_index_from_meta.py --force

执行后目录常见结果：
- index_v1.0.html  （原 1.0 页面，首次执行时从 index.html 改名得到）
- index.html       （新生成 2.0 页面）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def escape_json_for_inline_script(json_text: str) -> str:
    if not json_text:
        return "{}"
    return (
        json_text
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_index_html(meta: dict, app_dir: Path) -> str:
    template_path = app_dir / "templates" / "model.html"
    variables_css_path = app_dir / "static" / "css" / "variables.css"
    components_css_path = app_dir / "static" / "css" / "components.css"
    model_css_path = app_dir / "static" / "css" / "model.css"
    model_js_path = app_dir / "static" / "js" / "model.js"

    html = template_path.read_text(encoding="utf-8")
    variables_css = variables_css_path.read_text(encoding="utf-8")
    components_css = components_css_path.read_text(encoding="utf-8")
    model_css = model_css_path.read_text(encoding="utf-8")
    model_js = model_js_path.read_text(encoding="utf-8")

    # 离线归档页移除外部依赖（favicon/static、FontAwesome CDN）
    html = re.sub(
        r'<link[^>]*rel=["\']icon["\'][^>]*>\s*',
        "",
        html,
        flags=re.I,
    )
    html = re.sub(
        r'<link[^>]*href=["\']https?://[^"\']*font-awesome[^"\']*["\'][^>]*>\s*',
        "",
        html,
        flags=re.I,
    )

    model_css = re.sub(
        r"@import\s+url\(['\"]?/static/css/(?:variables|components)\.css[^)]*\)\s*;?",
        "",
        model_css,
        flags=re.I,
    )

    variables_inline = f"<style>\n{variables_css}\n</style>"
    model_inline = f"<style>\n{components_css}\n{model_css}\n</style>"

    html, var_count = re.subn(
        r'<link[^>]*href=["\']/static/css/variables\.css[^"\']*["\'][^>]*>',
        lambda _: variables_inline,
        html,
        count=1,
        flags=re.I,
    )
    if var_count == 0:
        html, _ = re.subn(r"</head>", lambda _: variables_inline + "\n</head>", html, count=1, flags=re.I)

    html, model_count = re.subn(
        r'<link[^>]*href=["\']/static/css/model\.css[^"\']*["\'][^>]*>',
        lambda _: model_inline,
        html,
        count=1,
        flags=re.I,
    )
    if model_count == 0:
        html, _ = re.subn(r"</head>", lambda _: model_inline + "\n</head>", html, count=1, flags=re.I)

    meta_json_str = escape_json_for_inline_script(json.dumps(meta, ensure_ascii=False))
    injection_script = f"\n<script>\nwindow.__OFFLINE_META__ = {meta_json_str};\n</script>\n"
    js_replacement = f"{injection_script}<script>\n{model_js}\n</script>"

    html, js_count = re.subn(
        r'<script[^>]*src=["\']/static/js/model\.js[^"\']*["\'][^>]*>\s*</script>',
        lambda _: js_replacement,
        html,
        count=1,
        flags=re.I,
    )
    if js_count == 0:
        html, body_count = re.subn(
            r"</body>",
            lambda _: f"{js_replacement}\n</body>",
            html,
            count=1,
            flags=re.I,
        )
        if body_count == 0:
            html += js_replacement

    return html


def get_frontend_asset_paths(app_dir: Path) -> list[Path]:
    return [
        app_dir / "templates" / "model.html",
        app_dir / "static" / "css" / "variables.css",
        app_dir / "static" / "css" / "components.css",
        app_dir / "static" / "css" / "model.css",
        app_dir / "static" / "js" / "model.js",
    ]


def compute_latest_source_mtime(meta_path: Path, frontend_assets: list[Path]) -> float:
    latest = meta_path.stat().st_mtime
    for p in frontend_assets:
        if p.exists():
            latest = max(latest, p.stat().st_mtime)
    return latest


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


def collect_meta_paths(data_root: Path) -> list[Path]:
    meta_paths = []
    if not data_root.exists():
        return meta_paths
    for d in sorted(data_root.iterdir()):
        if not d.is_dir():
            continue
        meta = d / "meta.json"
        if meta.exists():
            meta_paths.append(meta)
    return meta_paths


def list_dir_files(dir_path: Path, image_only: bool = False) -> list[str]:
    if not dir_path.exists():
        return []
    files = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        if p.name.startswith(".") or p.name.startswith("_"):
            continue
        if image_only and not re.search(r"\.(jpg|jpeg|png|gif|webp|bmp)$", p.name, re.I):
            continue
        files.append(p.name)
    return sorted(files)


def write_local_indexes(model_dir: Path):
    attach_dir = model_dir / "file"
    printed_dir = model_dir / "printed"
    for d, image_only in [(attach_dir, False), (printed_dir, True)]:
        if not d.exists():
            continue
        payload = {
            "files": list_dir_files(d, image_only=image_only),
            "updated_at": datetime.now().isoformat(),
        }
        (d / "_index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_collect_date(meta: dict, fallback_ts: int) -> dict:
    out = dict(meta or {})
    try:
        ts = int(out.get("collectDate"))
    except Exception:
        ts = 0
    if ts <= 0:
        out["collectDate"] = int(fallback_ts)
    else:
        out["collectDate"] = ts
    return out


def inject_offline_files(meta: dict, model_dir: Path) -> dict:
    fallback_ts = int((model_dir / "meta.json").stat().st_mtime)
    out = ensure_collect_date(meta or {}, fallback_ts)
    out["offlineFiles"] = {
        "attachments": list_dir_files(model_dir / "file", image_only=False),
        "printed": list_dir_files(model_dir / "printed", image_only=True),
    }
    return out


def looks_like_v2_index(content: str) -> bool:
    if not content:
        return False
    return (
        "window.__OFFLINE_META__" in content
        or "/static/js/model.js" in content
        or "id=\"loadingState\"" in content
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    app_dir = repo_root / "app"

    parser = argparse.ArgumentParser(description="根据已有 meta.json 批量重建 v2 index.html")
    parser.add_argument(
        "--data-root",
        default="",
        help="模型根目录（默认读取 app/config.json 的 download_dir，若无则 app/data）",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印将处理的目录，不写文件")
    parser.add_argument("--backup", action="store_true", help="覆盖前备份 index.html -> index.html.bak")
    parser.add_argument("--force", action="store_true", help="强制全量重建，忽略时间戳比较")
    args = parser.parse_args()

    data_root = Path(args.data_root).resolve() if args.data_root else resolve_default_data_root(repo_root)
    print(f"[rebuild-index] data_root={data_root}")

    if not app_dir.exists():
        print(f"[rebuild-index] ERROR: app 目录不存在: {app_dir}")
        return 2
    frontend_assets = get_frontend_asset_paths(app_dir)
    missing_assets = [str(p) for p in frontend_assets if not p.exists()]
    if missing_assets:
        print("[rebuild-index] ERROR: 缺少前端资源文件：")
        for p in missing_assets:
            print(f"  - {p}")
        return 2

    meta_paths = collect_meta_paths(data_root)
    if not meta_paths:
        print("[rebuild-index] 未找到任何 meta.json")
        return 1

    ok_count = 0
    fail_count = 0
    for meta_path in meta_paths:
        model_dir = meta_path.parent
        index_path = model_dir / "index.html"
        v1_index_path = model_dir / "index_v1.0.html"
        try:
            meta_raw = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = inject_offline_files(meta_raw, model_dir)
            meta_changed = meta != meta_raw

            old_content = ""
            if index_path.exists():
                old_content = index_path.read_text(encoding="utf-8", errors="ignore")
            should_migrate_v1 = index_path.exists() and not v1_index_path.exists() and not looks_like_v2_index(old_content)

            latest_src_mtime = compute_latest_source_mtime(meta_path, frontend_assets)
            is_up_to_date = (
                index_path.exists()
                and index_path.stat().st_mtime >= latest_src_mtime
            )
            if not args.force and not should_migrate_v1 and is_up_to_date and not meta_changed:
                if not args.dry_run:
                    write_local_indexes(model_dir)
                print(f"[skip-up-to-date] {index_path}")
                ok_count += 1
                continue

            html = build_index_html(meta, app_dir)
            if args.dry_run:
                if should_migrate_v1:
                    print(f"[dry-run] move {index_path.name} -> {v1_index_path.name} @ {model_dir}")
                print(f"[dry-run] write {index_path}")
            else:
                if meta_changed:
                    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                if should_migrate_v1:
                    index_path.rename(v1_index_path)
                    print(f"[keep-v1] {v1_index_path}")

                if args.backup and index_path.exists():
                    bak = model_dir / "index.html.bak"
                    bak.write_text(index_path.read_text(encoding="utf-8"), encoding="utf-8")
                index_path.write_text(html, encoding="utf-8")
                write_local_indexes(model_dir)
                print(f"[ok] {index_path}")
            ok_count += 1
        except Exception as e:
            fail_count += 1
            print(f"[fail] {index_path}: {e}")

    print(f"[rebuild-index] done: ok={ok_count}, fail={fail_count}")
    return 0 if fail_count == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
