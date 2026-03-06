import hashlib
import json
import logging
import re
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Optional, Tuple

from archiver import build_index_html, sanitize_filename
from local_model_utils import build_local_model_dir, ensure_manual_counter_file
from three_mf_parser import parse_3mf_to_session


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
LOGS_DIR = BASE_DIR / "logs"
TMP_DIR = BASE_DIR / "tmp" / "batch_import"
STATE_PATH = CONFIG_DIR / "local_batch_import_state.json"
REPORT_DIR = LOGS_DIR / "batch_import"
IMAGE_EXT_RE = re.compile(r"\.(jpg|jpeg|png|gif|webp|bmp)$", re.IGNORECASE)


@dataclass
class ParsedBatchItem:
    file_path: Path
    session_dir: Path
    parsed: dict
    file_hash: str
    signature: dict


def ensure_runtime_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat()


def format_duration_text(total_seconds: int) -> str:
    seconds = max(int(total_seconds or 0), 0)
    minutes = seconds // 60
    remain_seconds = seconds % 60
    return f"{minutes}分{remain_seconds}秒"


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


def normalize_batch_import_config(raw_cfg: Optional[dict]) -> dict:
    raw = raw_cfg if isinstance(raw_cfg, dict) else {}
    watch_dirs = raw.get("watch_dirs")
    if not isinstance(watch_dirs, list) or not watch_dirs:
        watch_dirs = ["./watch"]
    normalized_dirs = []
    for item in watch_dirs:
        text = str(item or "").strip()
        if text:
            normalized_dirs.append(text)
    if not normalized_dirs:
        normalized_dirs = ["./watch"]
    try:
        interval = max(int(raw.get("scan_interval_seconds") or 300), 30)
    except Exception:
        interval = 300
    try:
        workers = int(raw.get("max_parse_workers") or 2)
    except Exception:
        workers = 2
    workers = min(max(workers, 1), 4)
    duplicate_policy = str(raw.get("duplicate_policy") or "skip").strip().lower()
    if duplicate_policy not in {"skip"}:
        duplicate_policy = "skip"
    return {
        "enabled": bool(raw.get("enabled", False)),
        "watch_dirs": normalized_dirs,
        "scan_interval_seconds": interval,
        "max_parse_workers": workers,
        "notify_on_finish": bool(raw.get("notify_on_finish", True)),
        "duplicate_policy": duplicate_policy,
        "processed_dir_name": str(raw.get("processed_dir_name") or "_imported").strip() or "_imported",
        "failed_dir_name": str(raw.get("failed_dir_name") or "_failed").strip() or "_failed",
    }


def build_runtime_batch_import_config(raw_cfg: Optional[dict]) -> dict:
    cfg = normalize_batch_import_config(raw_cfg)
    resolved_dirs = []
    for item in cfg["watch_dirs"]:
        path = Path(item)
        if not path.is_absolute():
            path = (BASE_DIR / item).resolve()
        else:
            path = path.resolve()
        path.mkdir(parents=True, exist_ok=True)
        resolved_dirs.append(str(path))
    cfg["watch_dirs"] = resolved_dirs
    return cfg


def load_state() -> dict:
    ensure_runtime_dirs()
    data = read_json_file(STATE_PATH, {})
    files = data.get("files") if isinstance(data, dict) else {}
    meta = data.get("meta") if isinstance(data, dict) else {}
    return {
        "files": files if isinstance(files, dict) else {},
        "meta": meta if isinstance(meta, dict) else {},
    }


def save_state(state: dict):
    ensure_runtime_dirs()
    payload = {
        "files": state.get("files") if isinstance(state, dict) else {},
        "meta": state.get("meta") if isinstance(state, dict) else {},
    }
    write_json_file(STATE_PATH, payload)


def file_signature(path: Path) -> dict:
    stat = path.stat()
    return {
        "size": int(stat.st_size),
        "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
    }


def is_same_signature(left: dict, right: dict) -> bool:
    return (
        isinstance(left, dict)
        and isinstance(right, dict)
        and int(left.get("size") or -1) == int(right.get("size") or -2)
        and int(left.get("mtime_ns") or -1) == int(right.get("mtime_ns") or -2)
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if chunk:
                digest.update(chunk)
    return digest.hexdigest()


def normalize_key_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def derive_model_key(parsed: dict, fallback_name: str) -> Tuple[str, str]:
    meta = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    design_model_id = str(meta.get("DesignModelId") or "").strip()
    if design_model_id:
        return f"design_model:{design_model_id}", "DesignModelId"
    title = normalize_key_text(parsed.get("modelTitle") or parsed.get("profileTitle") or fallback_name)
    designer = normalize_key_text(parsed.get("designer") or "")
    return f"title_designer:{title}|{designer}", "TitleDesigner"


def derive_config_fingerprint(parsed: dict, file_hash: str) -> Tuple[str, str]:
    meta = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    design_profile_id = str(meta.get("DesignProfileId") or "").strip()
    if design_profile_id:
        return f"design_profile:{design_profile_id}", "DesignProfileId"
    return f"sha256:{file_hash}", "FileHash"


def strip_html(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"<[^>]+>", "", str(value)).strip()


def pick_instance_profile_summary(parsed: dict) -> str:
    profile = str(parsed.get("profileSummaryText") or "").strip()
    model = str(parsed.get("summaryText") or "").strip()
    if not profile:
        return ""
    if not model:
        return profile
    p_norm = "".join(profile.split())
    m_norm = "".join(model.split())
    if not p_norm or not m_norm:
        return profile
    if p_norm == m_norm or p_norm in m_norm or m_norm in p_norm:
        return ""
    return profile


def ensure_unique_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem or "file"
    suffix = dest.suffix
    idx = 1
    while True:
        candidate = dest.with_name(f"{stem}_{idx}{suffix}")
        if not candidate.exists():
            return candidate
        idx += 1


def sanitize_instance_storage_name(filename: str, fallback: str = "instance") -> str:
    raw = Path(str(filename or "")).name
    raw = re.sub(r"^s\d+_", "", raw, flags=re.IGNORECASE)
    safe = sanitize_filename(raw).strip()
    if not safe:
        safe = f"{fallback}.3mf"
    if Path(safe).suffix.lower() != ".3mf":
        safe = f"{Path(safe).stem or fallback}.3mf"
    return safe


def next_instance_id(instances: List[dict]) -> int:
    max_id = 0
    for inst in instances or []:
        try:
            max_id = max(max_id, int(inst.get("id")))
        except Exception:
            continue
    return max_id + 1


def list_files_in_dir(dir_path: Path, image_only: bool = False) -> List[str]:
    if not dir_path.exists():
        return []
    files = []
    for item in dir_path.iterdir():
        if not item.is_file():
            continue
        if item.name.startswith(".") or item.name.startswith("_"):
            continue
        if image_only and not IMAGE_EXT_RE.search(item.name):
            continue
        files.append(item.name)
    return sorted(files)


def sync_offline_files_to_meta(model_dir: Path, meta: dict):
    meta["offlineFiles"] = {
        "attachments": list_files_in_dir(model_dir / "file", image_only=False),
        "printed": list_files_in_dir(model_dir / "printed", image_only=True),
    }


def make_summary_payload(text: str, html_content: str = "") -> dict:
    html_value = str(html_content or "").strip()
    text_value = str(text or "").strip()
    if html_value:
        html_value = re.sub(r"<script[\s\S]*?>[\s\S]*?</script>", "", html_value, flags=re.IGNORECASE).strip()
    if not text_value and html_value:
        text_value = " ".join(strip_html(html_value).split())
    return {
        "raw": html_value,
        "html": html_value,
        "text": text_value,
    }


def copy_session_image(session_dir: Path, image_name: str, images_dir: Path) -> str:
    src = session_dir / "images" / str(image_name or "")
    if not src.exists() or not src.is_file():
        return ""
    safe_name = sanitize_filename(src.name) or src.name
    dest = ensure_unique_path(images_dir / safe_name)
    shutil.copy2(src, dest)
    return dest.name


def copy_session_file(session_dir: Path, file_name: str, files_dir: Path) -> str:
    src = session_dir / "file" / str(file_name or "")
    if not src.exists() or not src.is_file():
        return ""
    safe_name = sanitize_filename(src.name) or src.name
    dest = ensure_unique_path(files_dir / safe_name)
    shutil.copy2(src, dest)
    return dest.name


def write_model_index(model_dir: Path, meta: dict):
    cover_name = str((meta.get("cover") or {}).get("localName") or "")
    design_names = [x.get("fileName") for x in (meta.get("designImages") or []) if isinstance(x, dict) and x.get("fileName")]
    summary_names = [x.get("fileName") for x in (meta.get("summaryImages") or []) if isinstance(x, dict) and x.get("fileName")]
    hero_file = cover_name or (design_names[0] if design_names else (summary_names[0] if summary_names else ""))
    assets = {
        "design_files": design_names,
        "hero": f"./images/{hero_file}" if hero_file else "screenshot.png",
        "avatar": None,
        "collected_date": datetime.now().strftime("%Y-%m-%d"),
        "instance_files": [],
        "base_name": meta.get("baseName") or model_dir.name,
        "hide_stats": True,
        "hide_inst_stats": True,
    }
    (model_dir / "index.html").write_text(build_index_html(meta, assets), encoding="utf-8")


def model_key_from_meta(meta: dict, dir_name: str) -> Tuple[str, str]:
    import_meta = meta.get("importMeta") if isinstance(meta.get("importMeta"), dict) else {}
    model_key = str(import_meta.get("modelKey") or "").strip()
    key_source = str(import_meta.get("keySource") or "").strip()
    if model_key:
        return model_key, key_source or "meta.importMeta"
    title = str(meta.get("title") or dir_name).strip()
    author = str((meta.get("author") or {}).get("name") or "").strip()
    return f"title_designer:{normalize_key_text(title)}|{normalize_key_text(author)}", "TitleDesignerFallback"


def load_local_model_index(download_dir: str | Path, logger: Optional[logging.Logger] = None) -> dict:
    root = Path(download_dir).resolve()
    index = {}
    if not root.exists():
        return index
    for item in root.iterdir():
        if not item.is_dir() or not item.name.startswith("LocalModel_"):
            continue
        meta_path = item / "meta.json"
        if not meta_path.exists():
            continue
        meta = read_json_file(meta_path, {})
        if not isinstance(meta, dict):
            continue
        model_key, key_source = model_key_from_meta(meta, item.name)
        instances = meta.get("instances") if isinstance(meta.get("instances"), list) else []
        fingerprints = set()
        for inst in instances:
            if not isinstance(inst, dict):
                continue
            import_meta = inst.get("importMeta") if isinstance(inst.get("importMeta"), dict) else {}
            fingerprint = str(import_meta.get("configFingerprint") or "").strip()
            if fingerprint:
                fingerprints.add(fingerprint)
        if model_key in index and logger:
            logger.warning("检测到重复本地模型 key，保留首个目录: %s -> %s", model_key, index[model_key]["dir"])
            continue
        index[model_key] = {
            "dir": item.name,
            "path": item,
            "meta": meta,
            "key_source": key_source,
            "instance_fingerprints": fingerprints,
        }
    return index


def gather_candidate_files(
    watch_dirs: List[str],
    state: dict,
    explicit_paths: Optional[List[str]] = None,
    force: bool = False,
    processed_dir_name: str = "_imported",
    failed_dir_name: str = "_failed",
) -> List[dict]:
    candidates = []
    resolved = []
    if explicit_paths:
        for item in explicit_paths:
            path = Path(str(item or "").strip())
            if not path.is_absolute():
                path = (BASE_DIR / path).resolve()
            else:
                path = path.resolve()
            resolved.append(path)
    else:
        for watch_dir in watch_dirs:
            root = Path(watch_dir).resolve()
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if is_in_ignored_dir(path, root, [processed_dir_name, failed_dir_name]):
                    continue
                if path.suffix.lower() == ".3mf":
                    resolved.append(path.resolve())

    seen = set()
    files_state = state.get("files") if isinstance(state.get("files"), dict) else {}
    for path in sorted(resolved):
        key = str(path)
        if key in seen or not path.exists() or not path.is_file():
            continue
        seen.add(key)
        signature = file_signature(path)
        prev = files_state.get(key) if isinstance(files_state.get(key), dict) else {}
        pending = force or not is_same_signature(signature, prev.get("signature") if isinstance(prev, dict) else {})
        candidates.append({
            "path": key,
            "name": path.name,
            "signature": signature,
            "previous_status": str(prev.get("last_status") or ""),
            "pending": pending,
        })
    return candidates


def resolve_watch_root(file_path: Path, watch_dirs: List[str]) -> Optional[Path]:
    target = file_path.resolve()
    for item in watch_dirs:
        root = Path(item).resolve()
        try:
            target.relative_to(root)
            return root
        except Exception:
            continue
    return None


def is_in_processed_dir(file_path: Path, watch_root: Path, processed_dir_name: str) -> bool:
    try:
        rel = file_path.resolve().relative_to(watch_root.resolve())
    except Exception:
        return False
    parts = rel.parts
    return bool(parts and parts[0] == processed_dir_name)


def cleanup_empty_parent_dirs(start_dir: Path, watch_root: Path, protected_dir_names: Optional[List[str]] = None):
    protected = {str(name or "").strip() for name in (protected_dir_names or []) if str(name or "").strip()}
    current = start_dir.resolve()
    root = watch_root.resolve()
    while True:
        if current == root:
            break
        if current.name in protected:
            break
        try:
            next(current.iterdir())
            break
        except StopIteration:
            current.rmdir()
        except Exception:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent


def move_processed_source_file(file_path: Path, watch_root: Path, processed_dir_name: str) -> Path:
    source_path = file_path.resolve()
    source_parent = source_path.parent
    rel = source_path.relative_to(watch_root.resolve())
    rel_parent = rel.parent if str(rel.parent) != "." else Path()
    target_dir = watch_root / processed_dir_name / rel_parent
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = ensure_unique_path(target_dir / file_path.name)
    shutil.move(str(source_path), str(dest))
    cleanup_empty_parent_dirs(source_parent, watch_root, protected_dir_names=[processed_dir_name, "_imported", "_failed"])
    return dest


def is_in_ignored_dir(file_path: Path, watch_root: Path, ignored_dir_names: List[str]) -> bool:
    for name in ignored_dir_names:
        if is_in_processed_dir(file_path, watch_root, name):
            return True
    return False


def scan_batch_import(runtime_cfg: dict, explicit_paths: Optional[List[str]] = None, force: bool = False) -> dict:
    ensure_runtime_dirs()
    options = build_runtime_batch_import_config((runtime_cfg or {}).get("local_batch_import"))
    state = load_state()
    candidates = gather_candidate_files(
        options["watch_dirs"],
        state,
        explicit_paths=explicit_paths,
        force=force,
        processed_dir_name=options["processed_dir_name"],
        failed_dir_name=options["failed_dir_name"],
    )
    pending = [item for item in candidates if item.get("pending")]
    return {
        "status": "ok",
        "watch_dirs": options["watch_dirs"],
        "last_scan_at": str((state.get("meta") or {}).get("last_scan_at") or ""),
        "total_files": len(candidates),
        "pending_files": len(pending),
        "candidates": candidates,
    }


def parse_candidate_file(candidate: dict) -> Tuple[Optional[ParsedBatchItem], Optional[dict]]:
    path = Path(candidate["path"]).resolve()
    session_dir = TMP_DIR / uuid.uuid4().hex
    session_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_hash = sha256_file(path)
        file_bytes = path.read_bytes()
        parsed = parse_3mf_to_session(file_bytes, path.name, session_dir, 1)
        return ParsedBatchItem(
            file_path=path,
            session_dir=session_dir,
            parsed=parsed,
            file_hash=file_hash,
            signature=candidate["signature"],
        ), None
    except Exception as e:
        shutil.rmtree(session_dir, ignore_errors=True)
        return None, {"file": str(path), "message": str(e)}


def build_instance_payload(
    session_dir: Path,
    parsed: dict,
    file_hash: str,
    config_fingerprint: str,
    fingerprint_source: str,
    next_id: int,
    images_dir: Path,
    storage_name: str,
) -> dict:
    source_name = str(parsed.get("sourceName") or storage_name).strip() or storage_name
    pics = []
    for pidx, fn in enumerate(parsed.get("profilePictureFiles") or parsed.get("designFiles") or [], start=1):
        copied = copy_session_image(session_dir, str(fn), images_dir)
        if not copied:
            continue
        pics.append({
            "index": len(pics) + 1,
            "url": "",
            "relPath": f"images/{copied}",
            "fileName": copied,
            "isRealLifePhoto": 0,
        })

    plates = []
    for pidx, plate in enumerate(parsed.get("plates") or [], start=1):
        copied_th = copy_session_image(session_dir, str(plate.get("thumbnailFile") or ""), images_dir)
        if not copied_th:
            continue
        plates.append({
            "index": int(plate.get("index") or pidx),
            "prediction": int(plate.get("prediction") or 0),
            "weight": int(plate.get("weight") or 0),
            "filaments": plate.get("filaments") if isinstance(plate.get("filaments"), list) else [],
            "thumbnailUrl": "",
            "thumbnailRelPath": f"images/{copied_th}",
            "thumbnailFile": copied_th,
        })

    parsed_meta = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    return {
        "id": next_id,
        "title": str(parsed.get("profileTitle") or parsed.get("modelTitle") or Path(storage_name).stem),
        "titleTranslated": "",
        "summary": pick_instance_profile_summary(parsed),
        "summaryTranslated": "",
        "name": storage_name,
        "fileName": storage_name,
        "sourceFileName": Path(source_name).name,
        "publishTime": str(parsed.get("creationDate") or ""),
        "downloadCount": 0,
        "printCount": 0,
        "prediction": 0,
        "weight": 0,
        "materialCnt": 0,
        "materialColorCnt": 0,
        "needAms": False,
        "plates": plates,
        "pictures": pics,
        "instanceFilaments": [],
        "downloadUrl": "",
        "apiUrl": "",
        "importMeta": {
            "configFingerprint": config_fingerprint,
            "fingerprintSource": fingerprint_source,
            "fileHash": file_hash,
            "designModelId": str(parsed_meta.get("DesignModelId") or ""),
            "designProfileId": str(parsed_meta.get("DesignProfileId") or ""),
            "importMode": "batch",
        },
    }


def create_local_model_from_parsed(
    download_dir: str | Path,
    item: ParsedBatchItem,
    model_key: str,
    key_source: str,
    config_fingerprint: str,
    fingerprint_source: str,
) -> dict:
    parsed = item.parsed
    title = str(parsed.get("modelTitle") or parsed.get("profileTitle") or item.file_path.stem).strip() or item.file_path.stem
    base_name, model_dir = build_local_model_dir(download_dir, title)
    images_dir = model_dir / "images"
    instances_dir = model_dir / "instances"
    files_dir = model_dir / "file"
    images_dir.mkdir(parents=True, exist_ok=True)
    instances_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    cover_name = ""
    design_names = []
    for draft_img in parsed.get("designFiles") or []:
        copied = copy_session_image(item.session_dir, str(draft_img), images_dir)
        if copied:
            design_names.append(copied)
    for attachment in parsed.get("attachments") or []:
        copy_session_file(item.session_dir, str(attachment), files_dir)

    draft_cover = str(parsed.get("coverFile") or "").strip()
    if draft_cover:
        copied = copy_session_image(item.session_dir, draft_cover, images_dir)
        if copied:
            cover_name = copied
    if not cover_name and design_names:
        cover_name = design_names[0]
    if cover_name and not design_names:
        design_names = [cover_name]

    source_name = Path(str(parsed.get("sourceName") or item.file_path.name)).name
    storage_name = sanitize_instance_storage_name(source_name, fallback="instance_1")
    dest_3mf = ensure_unique_path(instances_dir / storage_name)
    src_3mf = item.session_dir / "instances" / str(parsed.get("instanceFile") or "")
    shutil.copy2(src_3mf, dest_3mf)

    instance_payload = build_instance_payload(
        item.session_dir,
        parsed,
        item.file_hash,
        config_fingerprint,
        fingerprint_source,
        1,
        images_dir,
        dest_3mf.name,
    )

    summary_payload = make_summary_payload(
        str(parsed.get("summaryText") or parsed.get("profileSummaryText") or "").strip(),
        str(parsed.get("descriptionHtml") or parsed.get("profileDescriptionHtml") or "").strip(),
    )
    parsed_meta = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    meta = {
        "baseName": base_name,
        "source": "LocalModel",
        "url": "",
        "id": None,
        "slug": "",
        "title": title,
        "titleTranslated": "",
        "coverUrl": "",
        "tags": [],
        "tagsOriginal": [],
        "stats": {"likes": 0, "favorites": 0, "downloads": 0, "prints": 0, "views": 0},
        "cover": {
            "url": "",
            "localName": cover_name,
            "relPath": f"images/{cover_name}" if cover_name else "",
        },
        "author": {
            "name": str(parsed.get("designer") or "本地批量导入"),
            "url": "",
            "avatarUrl": "",
            "avatarLocal": "",
            "avatarRelPath": "",
        },
        "images": {
            "cover": cover_name,
            "design": design_names,
            "summary": [],
        },
        "designImages": [
            {"index": idx, "originalUrl": "", "relPath": f"images/{fname}", "fileName": fname}
            for idx, fname in enumerate(design_names, start=1)
        ],
        "summaryImages": [],
        "summary": summary_payload,
        "instances": [instance_payload],
        "collectDate": int(datetime.now().timestamp()),
        "update_time": now_iso(),
        "generatedAt": Path().absolute().as_posix(),
        "note": "本文件包含结构化数据与打印配置详情。",
        "importMeta": {
            "modelKey": model_key,
            "keySource": key_source,
            "importMode": "batch",
            "designModelId": str(parsed_meta.get("DesignModelId") or ""),
            "firstFileHash": item.file_hash,
            "firstSourceFile": item.file_path.name,
        },
    }
    sync_offline_files_to_meta(model_dir, meta)
    write_json_file(model_dir / "meta.json", meta)
    write_model_index(model_dir, meta)
    return {
        "base_name": base_name,
        "model_dir": model_dir,
        "meta": meta,
    }


def append_instance_to_local_model(model_path: Path, item: ParsedBatchItem, config_fingerprint: str, fingerprint_source: str) -> dict:
    meta_path = model_path / "meta.json"
    meta = read_json_file(meta_path, {})
    if not isinstance(meta, dict):
        raise RuntimeError(f"meta.json 无效: {model_path}")

    images_dir = model_path / "images"
    instances_dir = model_path / "instances"
    images_dir.mkdir(parents=True, exist_ok=True)
    instances_dir.mkdir(parents=True, exist_ok=True)
    instances = meta.get("instances")
    if not isinstance(instances, list):
        instances = []
        meta["instances"] = instances

    source_name = Path(str(item.parsed.get("sourceName") or item.file_path.name)).name
    storage_name = sanitize_instance_storage_name(source_name, fallback=f"instance_{next_instance_id(instances)}")
    dest_3mf = ensure_unique_path(instances_dir / storage_name)
    src_3mf = item.session_dir / "instances" / str(item.parsed.get("instanceFile") or "")
    shutil.copy2(src_3mf, dest_3mf)

    instance_payload = build_instance_payload(
        item.session_dir,
        item.parsed,
        item.file_hash,
        config_fingerprint,
        fingerprint_source,
        next_instance_id(instances),
        images_dir,
        dest_3mf.name,
    )
    instances.append(instance_payload)
    meta["update_time"] = now_iso()
    sync_offline_files_to_meta(model_path, meta)
    write_json_file(meta_path, meta)
    write_model_index(model_path, meta)
    return {"meta": meta, "instance": instance_payload}


def write_report(report: dict) -> str:
    ensure_runtime_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"batch_import_{ts}.json"
    write_json_file(report_path, report)
    return str(report_path)


def update_state_meta(state: dict, report: dict):
    meta = state.get("meta") if isinstance(state.get("meta"), dict) else {}
    scan_at = str(report.get("finished_at") or now_iso())
    meta["last_scan_at"] = scan_at
    meta["last_processed"] = int(report.get("processed") or 0)
    meta["last_created_models"] = int(report.get("created_models") or 0)
    meta["last_appended_instances"] = int(report.get("appended_instances") or 0)
    meta["last_skipped_duplicates"] = int(report.get("skipped_duplicates") or 0)
    meta["last_failed"] = int(report.get("failed") or 0)
    meta["last_duration_seconds"] = int(report.get("duration_seconds") or 0)
    meta["last_report_path"] = str(report.get("report_path") or "")
    meta["last_result"] = str(report.get("last_result") or "")
    meta["last_source_label"] = str(report.get("source_label") or "")
    recent_success_records = meta.get("recent_success_records") if isinstance(meta.get("recent_success_records"), list) else []
    if str(report.get("last_result") or "").strip().lower() == "processed" and int(report.get("processed") or 0) > 0:
        recent_success_records.insert(0, {
            "scan_at": scan_at,
            "source_label": str(report.get("source_label") or ""),
            "processed": int(report.get("processed") or 0),
            "created_models": int(report.get("created_models") or 0),
            "appended_instances": int(report.get("appended_instances") or 0),
            "skipped_duplicates": int(report.get("skipped_duplicates") or 0),
            "failed": int(report.get("failed") or 0),
            "duration_seconds": int(report.get("duration_seconds") or 0),
            "report_path": str(report.get("report_path") or ""),
        })
        meta["recent_success_records"] = recent_success_records[:5]
    else:
        meta["recent_success_records"] = recent_success_records[:5]
    state["meta"] = meta


def build_notify_payload(report: dict, source_label: str = "watcher") -> dict:
    summary = (
        f"新增模型 {report.get('created_models', 0)} 个，"
        f"新增配置 {report.get('appended_instances', 0)} 个，"
        f"跳过 {report.get('skipped_duplicates', 0)} 个，"
        f"失败 {report.get('failed', 0)} 个"
    )
    lines = [
        f"扫描文件: {report.get('total_candidates', 0)}",
        f"生效目录: {len(report.get('watch_dirs') or [])}",
        f"已移动源文件: {report.get('moved_files', 0)}",
        f"耗时: {format_duration_text(report.get('duration_seconds', 0))}",
    ]
    report_path = str(report.get("report_path") or "").strip()
    if report_path:
        lines.append(f"报告文件: {report_path}")
    title = "监控目录导入完成" if str(source_label or "").strip().lower() == "watcher" else "手动目录导入完成"
    return {
        "icon": "✅" if int(report.get("failed") or 0) == 0 else "⚠️",
        "title": title,
        "summary": summary,
        "lines": lines,
    }


def run_batch_import(
    runtime_cfg: dict,
    explicit_paths: Optional[List[str]] = None,
    force: bool = False,
    logger: Optional[logging.Logger] = None,
    source_label: str = "watcher",
) -> dict:
    start_time = perf_counter()
    ensure_runtime_dirs()
    options = build_runtime_batch_import_config((runtime_cfg or {}).get("local_batch_import"))
    ensure_manual_counter_file(runtime_cfg["download_dir"])

    state = load_state()
    candidates = gather_candidate_files(
        options["watch_dirs"],
        state,
        explicit_paths=explicit_paths,
        force=force,
        processed_dir_name=options["processed_dir_name"],
        failed_dir_name=options["failed_dir_name"],
    )
    pending = [item for item in candidates if item.get("pending")]
    if not pending:
        report = {
            "status": "ok",
            "watch_dirs": options["watch_dirs"],
            "total_candidates": len(candidates),
            "processed": 0,
            "created_models": 0,
            "appended_instances": 0,
            "skipped_duplicates": 0,
            "moved_files": 0,
            "failed": 0,
            "details": [],
            "last_result": "idle",
            "duration_seconds": max(int(round(perf_counter() - start_time)), 0),
            "source_label": str(source_label or "watcher"),
        }
        update_state_meta(state, report)
        save_state(state)
        return report

    parsed_items: List[ParsedBatchItem] = []
    details = []
    moved_files = 0
    with ThreadPoolExecutor(max_workers=options["max_parse_workers"]) as executor:
        future_map = {executor.submit(parse_candidate_file, item): item for item in pending}
        for future in as_completed(future_map):
            item = future_map[future]
            parsed_item, err = future.result()
            if err:
                watch_root = resolve_watch_root(Path(item["path"]), options["watch_dirs"])
                details.append({
                    "file": item["path"],
                    "action": "parse_failed",
                    "status": "failed",
                    "message": err["message"],
                })
                files_state = state.setdefault("files", {})
                files_state[item["path"]] = {
                    "signature": item["signature"],
                    "last_status": "parse_failed",
                    "last_error": err["message"],
                    "updated_at": now_iso(),
                }
                if watch_root is not None and Path(item["path"]).exists():
                    moved_to = move_processed_source_file(Path(item["path"]), watch_root, options["failed_dir_name"])
                    moved_files += 1
                    details[-1]["moved_to"] = str(moved_to)
                    files_state.pop(item["path"], None)
                continue
            parsed_items.append(parsed_item)

    model_index = load_local_model_index(runtime_cfg["download_dir"], logger=logger)
    created_models = 0
    appended_instances = 0
    skipped_duplicates = 0
    failed = 0
    files_state = state.setdefault("files", {})

    for item in sorted(parsed_items, key=lambda x: str(x.file_path).lower()):
        model_key, key_source = derive_model_key(item.parsed, item.file_path.stem)
        config_fingerprint, fingerprint_source = derive_config_fingerprint(item.parsed, item.file_hash)
        try:
            watch_root = resolve_watch_root(item.file_path, options["watch_dirs"])
            current = model_index.get(model_key)
            if current and config_fingerprint in current["instance_fingerprints"]:
                skipped_duplicates += 1
                details.append({
                    "file": str(item.file_path),
                    "action": "skip_duplicate_instance",
                    "status": "skipped",
                    "target_model": current["dir"],
                    "model_key": model_key,
                    "config_fingerprint": config_fingerprint,
                    "message": "检测到同模型同配置，已跳过",
                })
                files_state[str(item.file_path)] = {
                    "signature": item.signature,
                    "last_status": "skipped_duplicate",
                    "model_dir": current["dir"],
                    "model_key": model_key,
                    "config_fingerprint": config_fingerprint,
                    "updated_at": now_iso(),
                }
                if watch_root is not None and item.file_path.exists():
                    moved_to = move_processed_source_file(item.file_path, watch_root, options["processed_dir_name"])
                    moved_files += 1
                    details[-1]["moved_to"] = str(moved_to)
                    files_state.pop(str(item.file_path), None)
                continue

            if current:
                result = append_instance_to_local_model(current["path"], item, config_fingerprint, fingerprint_source)
                current["meta"] = result["meta"]
                current["instance_fingerprints"].add(config_fingerprint)
                appended_instances += 1
                details.append({
                    "file": str(item.file_path),
                    "action": "append_instance",
                    "status": "ok",
                    "target_model": current["dir"],
                    "model_key": model_key,
                    "config_fingerprint": config_fingerprint,
                    "message": f"已追加配置到 {current['dir']}",
                })
                files_state[str(item.file_path)] = {
                    "signature": item.signature,
                    "last_status": "append_instance",
                    "model_dir": current["dir"],
                    "model_key": model_key,
                    "config_fingerprint": config_fingerprint,
                    "updated_at": now_iso(),
                }
                if watch_root is not None and item.file_path.exists():
                    moved_to = move_processed_source_file(item.file_path, watch_root, options["processed_dir_name"])
                    moved_files += 1
                    details[-1]["moved_to"] = str(moved_to)
                    files_state.pop(str(item.file_path), None)
                continue

            created = create_local_model_from_parsed(
                runtime_cfg["download_dir"],
                item,
                model_key,
                key_source,
                config_fingerprint,
                fingerprint_source,
            )
            model_index[model_key] = {
                "dir": created["base_name"],
                "path": created["model_dir"],
                "meta": created["meta"],
                "key_source": key_source,
                "instance_fingerprints": {config_fingerprint},
            }
            created_models += 1
            details.append({
                "file": str(item.file_path),
                "action": "create_model",
                "status": "ok",
                "target_model": created["base_name"],
                "model_key": model_key,
                "config_fingerprint": config_fingerprint,
                "message": f"已新建模型 {created['base_name']}",
            })
            files_state[str(item.file_path)] = {
                "signature": item.signature,
                "last_status": "create_model",
                "model_dir": created["base_name"],
                "model_key": model_key,
                "config_fingerprint": config_fingerprint,
                "updated_at": now_iso(),
            }
            if watch_root is not None and item.file_path.exists():
                moved_to = move_processed_source_file(item.file_path, watch_root, options["processed_dir_name"])
                moved_files += 1
                details[-1]["moved_to"] = str(moved_to)
                files_state.pop(str(item.file_path), None)
        except Exception as e:
            failed += 1
            details.append({
                "file": str(item.file_path),
                "action": "import_failed",
                "status": "failed",
                "model_key": model_key,
                "config_fingerprint": config_fingerprint,
                "message": str(e),
            })
            files_state[str(item.file_path)] = {
                "signature": item.signature,
                "last_status": "import_failed",
                "last_error": str(e),
                "model_key": model_key,
                "config_fingerprint": config_fingerprint,
                "updated_at": now_iso(),
            }
            if watch_root is not None and item.file_path.exists():
                moved_to = move_processed_source_file(item.file_path, watch_root, options["failed_dir_name"])
                moved_files += 1
                details[-1]["moved_to"] = str(moved_to)
                files_state.pop(str(item.file_path), None)
        finally:
            shutil.rmtree(item.session_dir, ignore_errors=True)

    failed += sum(1 for item in details if item.get("status") == "failed" and item.get("action") == "parse_failed")

    report = {
        "status": "ok",
        "watch_dirs": options["watch_dirs"],
        "total_candidates": len(candidates),
        "processed": len(pending),
        "created_models": created_models,
        "appended_instances": appended_instances,
        "skipped_duplicates": skipped_duplicates,
        "moved_files": moved_files,
        "failed": failed,
        "details": details,
        "finished_at": now_iso(),
        "last_result": "processed",
        "source_label": str(source_label or "watcher"),
        "duration_seconds": max(int(round(perf_counter() - start_time)), 0),
    }
    report["report_path"] = write_report(report)
    report["notify_payload"] = build_notify_payload(report, source_label=source_label)
    update_state_meta(state, report)
    save_state(state)
    if logger:
        logger.info(
            "批量导入完成: 处理 %s, 新建模型 %s, 新增配置 %s, 跳过 %s, 失败 %s",
            report["processed"],
            created_models,
            appended_instances,
            skipped_duplicates,
            failed,
        )
    return report
