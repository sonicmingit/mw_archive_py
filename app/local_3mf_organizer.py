import hashlib
import json
import re
import shutil
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Dict, Iterable, List, Optional, Tuple

from archiver import sanitize_filename
from three_mf_parser import parse_3mf_to_session


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
STATE_PATH = CONFIG_DIR / "local_3mf_organizer_state.json"

ORGANIZED_DIR_NAME = "整理完成"
DUPLICATES_DIR_NAME = "重复文件"
REPORTS_DIR_NAME = "整理报告"
FAILED_DIR_NAME = "整理失败"
MANIFEST_NAME = "organize_manifest.json"
OUTPUT_DIR_NAMES = {
    ORGANIZED_DIR_NAME,
    DUPLICATES_DIR_NAME,
    REPORTS_DIR_NAME,
    FAILED_DIR_NAME,
    "_organized",
    "_duplicates",
    "_reports",
    "_failed",
}

DEFAULT_ORGANIZER_CONFIG = {
    "root_dir": "./organize",
    "mode": "move",
}


@dataclass
class ParsedItem:
    source_path: Path
    source_rel: str
    file_hash: str
    parsed: dict
    model_key: str
    model_key_source: str
    config_fingerprint: str
    config_key_source: str
    model_title: str
    config_title: str


def now_iso() -> str:
    return datetime.now().isoformat()


def format_duration_text(total_seconds: float) -> str:
    seconds = max(int(round(total_seconds or 0)), 0)
    minutes = seconds // 60
    remain_seconds = seconds % 60
    return f"{minutes}分{remain_seconds}秒"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def read_json_file(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write_json_file(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_local_3mf_organizer_config(raw_cfg: Optional[dict]) -> dict:
    raw = raw_cfg if isinstance(raw_cfg, dict) else {}
    root_dir = str(raw.get("root_dir") or DEFAULT_ORGANIZER_CONFIG["root_dir"]).strip() or DEFAULT_ORGANIZER_CONFIG["root_dir"]
    mode = str(raw.get("mode") or DEFAULT_ORGANIZER_CONFIG["mode"]).strip().lower()
    if mode not in {"move", "copy"}:
        mode = DEFAULT_ORGANIZER_CONFIG["mode"]
    return {
        "root_dir": root_dir,
        "mode": mode,
    }


def build_runtime_local_3mf_organizer_config(raw_cfg: Optional[dict]) -> dict:
    cfg = normalize_local_3mf_organizer_config(raw_cfg)
    path = Path(cfg["root_dir"])
    if not path.is_absolute():
        path = (BASE_DIR / cfg["root_dir"]).resolve()
    else:
        path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    cfg["root_dir"] = str(path)
    return cfg


def load_state() -> dict:
    ensure_config_dir()
    data = read_json_file(STATE_PATH, {})
    meta = data.get("meta") if isinstance(data, dict) else {}
    by_root = data.get("by_root") if isinstance(data, dict) else {}
    state = {
        "meta": meta if isinstance(meta, dict) else {},
        "by_root": by_root if isinstance(by_root, dict) else {},
    }
    legacy_root = str(state["meta"].get("last_root_dir") or "").strip()
    if legacy_root and legacy_root not in state["by_root"]:
        state["by_root"][legacy_root] = deepcopy(state["meta"])
    return state


def save_state(state: dict):
    ensure_config_dir()
    payload = {
        "meta": state.get("meta") if isinstance(state, dict) else {},
        "by_root": state.get("by_root") if isinstance(state, dict) else {},
    }
    write_json_file(STATE_PATH, payload)


def normalize_key_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            if chunk:
                digest.update(chunk)
    return digest.hexdigest()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_3mf_name(name: str, fallback: str) -> str:
    raw = sanitize_filename(str(name or "")).strip()
    if not raw:
        raw = fallback
    stem = raw[:-4] if raw.lower().endswith(".3mf") else raw
    stem = stem.strip() or fallback
    return f"{stem}.3mf"


def ensure_unique_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem or "file"
    suffix = dest.suffix
    index = 2
    while True:
        candidate = dest.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def derive_model_key(parsed: dict, fallback_name: str) -> Tuple[str, str]:
    metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    design_model_id = str(metadata.get("DesignModelId") or "").strip()
    if design_model_id:
        return f"design_model:{design_model_id}", "DesignModelId"
    title = normalize_key_text(parsed.get("modelTitle") or parsed.get("profileTitle") or fallback_name)
    designer = normalize_key_text(parsed.get("designer") or "")
    return f"title_designer:{title}|{designer}", "TitleDesigner"


def derive_config_fingerprint(parsed: dict, file_hash: str) -> Tuple[str, str]:
    metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    design_profile_id = str(metadata.get("DesignProfileId") or "").strip()
    if design_profile_id:
        return f"design_profile:{design_profile_id}", "DesignProfileId"
    return f"sha256:{file_hash}", "FileHash"


def build_model_folder_name(parsed: dict, source_path: Path) -> str:
    metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    design_model_id = str(metadata.get("DesignModelId") or "").strip()
    title = sanitize_filename(str(parsed.get("modelTitle") or parsed.get("profileTitle") or source_path.stem)).strip() or "model"
    designer = sanitize_filename(str(parsed.get("designer") or "")).strip()
    if design_model_id:
        if designer:
            return f"MW_{designer}_{title}"
        return f"MW_{title}"
    if designer:
        return f"Others_{designer}_{title}"
    return f"Others_{title}"


def build_config_file_name(parsed: dict, source_path: Path) -> str:
    profile_title = str(parsed.get("profileTitle") or "").strip()
    model_title = str(parsed.get("modelTitle") or "").strip()
    preferred = profile_title or model_title or ""
    normalized = preferred.replace(" ", "")
    if len(normalized) <= 1 or re.fullmatch(r"[\d._-]+", normalized or ""):
        preferred = source_path.stem
    return ensure_3mf_name(preferred or source_path.stem, "config")


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"models": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"models": {}}
    if not isinstance(data, dict):
        return {"models": {}}
    models = data.get("models")
    if not isinstance(models, dict):
        models = {}
    return {"models": models}


def save_manifest(path: Path, manifest: dict):
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def iter_candidate_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file() or path.suffix.lower() != ".3mf":
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in OUTPUT_DIR_NAMES for part in rel_parts):
            continue
        yield path


def parse_item(path: Path, reports_dir: Path, root: Path) -> ParsedItem:
    file_hash = sha256_file(path)
    file_bytes = path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="organize_3mf_", dir=str(reports_dir)) as temp_dir:
        parsed = parse_3mf_to_session(file_bytes, path.name, Path(temp_dir), 1)
    model_key, model_key_source = derive_model_key(parsed, path.stem)
    config_fingerprint, config_key_source = derive_config_fingerprint(parsed, file_hash)
    model_title = str(parsed.get("modelTitle") or parsed.get("profileTitle") or path.stem).strip() or path.stem
    config_title = str(parsed.get("profileTitle") or parsed.get("modelTitle") or path.stem).strip() or path.stem
    return ParsedItem(
        source_path=path,
        source_rel=str(path.relative_to(root)),
        file_hash=file_hash,
        parsed=parsed,
        model_key=model_key,
        model_key_source=model_key_source,
        config_fingerprint=config_fingerprint,
        config_key_source=config_key_source,
        model_title=model_title,
        config_title=config_title,
    )


def move_or_copy_file(source: Path, dest: Path, mode: str):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if mode == "copy":
        shutil.copy2(source, dest)
    else:
        shutil.move(str(source), str(dest))


def create_record(manifest: dict, item: ParsedItem, organized_dir: Path) -> dict:
    models = manifest.setdefault("models", {})
    record = models.get(item.model_key)
    if isinstance(record, dict):
        return record

    folder_name = build_model_folder_name(item.parsed, item.source_path)
    model_dir = ensure_unique_path(organized_dir / folder_name)
    record = {
        "folder_name": model_dir.name,
        "model_title": item.model_title,
        "model_key_source": item.model_key_source,
        "configs": {},
    }
    models[item.model_key] = record
    return record


def write_report(path: Path, summary: dict, details: List[dict]):
    lines: List[str] = []
    lines.append("3MF 整理报告")
    lines.append("=" * 40)
    lines.append(f"生成时间: {summary['generated_at']}")
    lines.append(f"根目录: {summary['root']}")
    lines.append(f"执行模式: {summary['mode']}")
    lines.append(f"预览模式: {'是' if summary['dry_run'] else '否'}")
    lines.append(f"扫描文件数: {summary['scanned_files']}")
    lines.append(f"整理模型数: {summary['organized_models']}")
    lines.append(f"整理配置数: {summary['organized_configs']}")
    lines.append(f"重复数量: {summary['duplicate_count']}")
    lines.append(f"失败数量: {summary['failed_count']}")
    lines.append(f"整理耗时: {summary['duration_text']}")
    lines.append("")

    model_groups = summary.get("models") or []
    if model_groups:
        lines.append("模型汇总")
        lines.append("-" * 40)
        for group in model_groups:
            lines.append(f"[{group['folder_name']}] {group['model_title']}")
            lines.append(f"  配置数: {group['config_count']}")
            lines.append(f"  配置列表: {', '.join(group['config_names'])}")
        lines.append("")

    duplicate_rows = [row for row in details if row.get("action") == "duplicate"]
    if duplicate_rows:
        lines.append("重复文件")
        lines.append("-" * 40)
        for row in duplicate_rows:
            lines.append(f"- {row['source']} -> {row['dest']}")
        lines.append("")

    failed_rows = [row for row in details if row.get("action") == "failed"]
    if failed_rows:
        lines.append("失败文件")
        lines.append("-" * 40)
        for row in failed_rows:
            lines.append(f"- {row['source']}: {row['message']}")
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def update_state_meta(state: dict, report: dict):
    meta = state.get("meta") if isinstance(state.get("meta"), dict) else {}
    by_root = state.get("by_root") if isinstance(state.get("by_root"), dict) else {}
    meta["last_run_at"] = str(report.get("generated_at") or now_iso())
    meta["last_root_dir"] = str(report.get("root") or "")
    meta["last_mode"] = str(report.get("mode") or "")
    meta["last_dry_run"] = bool(report.get("dry_run"))
    meta["last_scanned_files"] = int(report.get("scanned_files") or 0)
    meta["last_organized_models"] = int(report.get("organized_models") or 0)
    meta["last_organized_configs"] = int(report.get("organized_configs") or 0)
    meta["last_duplicate_count"] = int(report.get("duplicate_count") or 0)
    meta["last_failed_count"] = int(report.get("failed_count") or 0)
    meta["last_duration_seconds"] = float(report.get("duration_seconds") or 0)
    meta["last_duration_text"] = str(report.get("duration_text") or "")
    meta["last_report_path"] = str(report.get("report_path") or "")
    state["meta"] = meta
    root_key = str(report.get("root") or "").strip()
    if root_key:
        by_root[root_key] = deepcopy(meta)
    state["by_root"] = by_root


def select_state_for_root(state: dict, root_dir: str) -> dict:
    root_key = str(root_dir or "").strip()
    by_root = state.get("by_root") if isinstance(state.get("by_root"), dict) else {}
    if root_key and isinstance(by_root.get(root_key), dict):
        return by_root[root_key]
    return {}


def run_local_3mf_organizer(
    runtime_cfg: dict,
    root_dir: Optional[str] = None,
    mode: Optional[str] = None,
    dry_run: bool = False,
    limit: int = 0,
) -> dict:
    merged_cfg = dict(runtime_cfg or {})
    if root_dir is not None:
        merged_cfg["root_dir"] = root_dir
    if mode is not None:
        merged_cfg["mode"] = mode
    organizer_cfg = build_runtime_local_3mf_organizer_config(merged_cfg)
    start_time = perf_counter()

    root = Path(organizer_cfg["root_dir"]).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"根目录不存在或不是目录: {root}")

    mode_value = str(organizer_cfg["mode"] or "move").strip().lower()
    if mode_value not in {"move", "copy"}:
        mode_value = "move"

    organized_dir = ensure_dir(root / ORGANIZED_DIR_NAME)
    duplicates_dir = ensure_dir(root / DUPLICATES_DIR_NAME)
    reports_dir = ensure_dir(root / REPORTS_DIR_NAME)
    failed_dir = ensure_dir(root / FAILED_DIR_NAME)
    manifest_path = reports_dir / MANIFEST_NAME
    manifest = load_manifest(manifest_path)

    candidates = list(iter_candidate_files(root))
    if limit and int(limit) > 0:
        candidates = candidates[: int(limit)]

    details: List[dict] = []
    model_stats: Dict[str, dict] = {}
    organized_configs = 0
    duplicate_count = 0
    failed_count = 0

    for path in candidates:
        try:
            item = parse_item(path, reports_dir, root)
        except Exception as exc:
            failed_count += 1
            failed_dest = ensure_unique_path(failed_dir / ensure_3mf_name(path.name, path.stem or "failed"))
            details.append(
                {
                    "action": "failed",
                    "source": str(path.relative_to(root)),
                    "dest": str(failed_dest.relative_to(root)),
                    "message": str(exc),
                }
            )
            if not dry_run:
                move_or_copy_file(path, failed_dest, mode_value)
            continue

        record = create_record(manifest, item, organized_dir)
        configs = record.setdefault("configs", {})
        model_dir = organized_dir / record["folder_name"]

        if item.config_fingerprint in configs:
            duplicate_count += 1
            duplicate_dest = ensure_unique_path(duplicates_dir / ensure_3mf_name(path.name, path.stem or "duplicate"))
            details.append(
                {
                    "action": "duplicate",
                    "source": item.source_rel,
                    "dest": str(duplicate_dest.relative_to(root)),
                    "model_key": item.model_key,
                    "config_fingerprint": item.config_fingerprint,
                }
            )
            if not dry_run:
                move_or_copy_file(path, duplicate_dest, mode_value)
            continue

        dest_name = build_config_file_name(item.parsed, path)
        dest_path = ensure_unique_path(model_dir / dest_name)
        details.append(
            {
                "action": "organized",
                "source": item.source_rel,
                "dest": str(dest_path.relative_to(root)),
                "model_key": item.model_key,
                "config_fingerprint": item.config_fingerprint,
            }
        )

        if not dry_run:
            move_or_copy_file(path, dest_path, mode_value)

        configs[item.config_fingerprint] = {
            "file_name": dest_path.name,
            "config_title": item.config_title,
            "file_hash": item.file_hash,
            "config_key_source": item.config_key_source,
            "updated_at": now_iso(),
        }
        organized_configs += 1

        stat = model_stats.setdefault(
            item.model_key,
            {
                "folder_name": record["folder_name"],
                "model_title": record.get("model_title") or item.model_title,
                "config_names": [],
            },
        )
        stat["config_names"].append(dest_path.name)

    if not dry_run:
        save_manifest(manifest_path, manifest)

    model_summaries = []
    for row in sorted(model_stats.values(), key=lambda item: item["folder_name"].lower()):
        names = sorted(row["config_names"], key=str.lower)
        model_summaries.append(
            {
                "folder_name": row["folder_name"],
                "model_title": row["model_title"],
                "config_count": len(names),
                "config_names": names,
            }
        )

    report = {
        "generated_at": now_iso(),
        "root": str(root),
        "mode": mode_value,
        "dry_run": bool(dry_run),
        "scanned_files": len(candidates),
        "organized_models": len(model_summaries),
        "organized_configs": organized_configs,
        "duplicate_count": duplicate_count,
        "failed_count": failed_count,
        "models": model_summaries,
        "details": details,
        "duration_seconds": max(perf_counter() - start_time, 0.0),
    }
    report["duration_text"] = format_duration_text(report["duration_seconds"])
    report_name = "organize_report_preview.txt" if dry_run else f"organize_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path = reports_dir / report_name
    write_report(report_path, report, details)
    report["report_path"] = str(report_path)
    report["runtime_root_dir"] = str(root)

    state = load_state()
    update_state_meta(state, report)
    save_state(state)
    return report
