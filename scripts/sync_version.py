#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
脚本说明：
- 读取仓库根目录 version.yml，作为唯一版本源。
- 将版本号同步到项目内多个目标文件，避免手工改漏。
- 当前同步目标：
  1) plugin/tampermonkey/mw_quick_archive.user.js 的 @version
  2) plugin/chrome_extension/mw_quick_archive_ext/manifest.json 的 version
  3) README.md 的“当前版本”首行
- 设计为可重复执行：若目标文件已是最新版本，则不会写入。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "version.yml"


def load_version_cfg(path: Path) -> Dict[str, str]:
    # 这里使用“轻量解析”而不是引入 YAML 依赖，
    # 目的是让脚本在最小环境下也能直接运行。
    cfg: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        # 跳过空行与注释行
        if not line or line.startswith("#"):
            continue
        # 非 key:value 格式直接跳过
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        # 去除可能的单/双引号包裹
        cfg[key.strip()] = value.strip().strip("'\"")

    # 强校验必需字段，确保后续替换逻辑有完整输入
    required = ["project_version", "tampermonkey_version", "chrome_extension_version"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise RuntimeError(f"version.yml 缺少字段: {', '.join(missing)}")
    return cfg


def update_tampermonkey(path: Path, version: str) -> bool:
    # 替换油猴元信息中的 @version 行
    content = path.read_text(encoding="utf-8")
    updated = re.sub(r"(?m)^//\s*@version\s+.+$", f"// @version      {version}", content)
    if updated == content:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def update_manifest(path: Path, version: str) -> bool:
    # 直接读写 JSON，避免字符串替换误伤其他字段
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") == version:
        return False
    data["version"] = version
    # 统一输出格式，保证 diff 稳定可读
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def update_readme(path: Path, project_version: str) -> bool:
    content = path.read_text(encoding="utf-8")
    # 仅替换“当前版本”第一条版本行，不影响历史日志列表
    updated = re.sub(
        r"(?m)^- `v[0-9]+\.[0-9]+(?:\.[0-9]+)?`（[0-9]{4}-[0-9]{2}-[0-9]{2}）$",
        f"- `v{project_version}`（待发布）",
        content,
        count=1,
    )
    if updated == content:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    # 1) 读取统一版本配置
    cfg = load_version_cfg(VERSION_FILE)
    changed: List[str] = []

    # 2) 定义同步目标（文件路径、处理函数、目标版本）
    targets = [
        ("plugin/tampermonkey/mw_quick_archive.user.js", update_tampermonkey, cfg["tampermonkey_version"]),
        ("plugin/chrome_extension/mw_quick_archive_ext/manifest.json", update_manifest, cfg["chrome_extension_version"]),
        ("README.md", update_readme, cfg["project_version"]),
    ]

    # 3) 执行同步，并记录发生变更的文件
    for rel, fn, version in targets:
        abs_path = REPO_ROOT / rel
        if fn(abs_path, version):
            changed.append(rel)

    # 4) 输出结果，便于 release 脚本与人工检查
    if changed:
        print("Updated:")
        for item in changed:
            print(f"- {item}")
    else:
        print("No changes needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
