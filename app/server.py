import json
import logging
import re
import shutil
import sys
import threading
import uuid
from copy import deepcopy
from html import escape as escape_html
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from notify_dispatcher import NotificationDispatcher
from archiver import (
    archive_model,
    build_index_html,
    download_file,
    fetch_instance_3mf,
    parse_cookies,
    sanitize_filename,
)
from three_mf_parser import (
    attach_preview_urls,
    build_draft_payload,
    parse_3mf_to_session,
)
from batch_import_service import (
    build_runtime_batch_import_config,
    load_state as load_batch_import_state,
    normalize_batch_import_config,
    run_batch_import,
    scan_batch_import,
)
from batch_import_watcher import LocalBatchImportWatcher
from local_3mf_organizer import (
    DEFAULT_ORGANIZER_CONFIG,
    build_runtime_local_3mf_organizer_config,
    load_state as load_local_3mf_organizer_state,
    normalize_local_3mf_organizer_config,
    run_local_3mf_organizer,
    select_state_for_root,
)
from local_model_utils import (
    build_local_model_dir as shared_build_local_model_dir,
    ensure_manual_counter_file as shared_ensure_manual_counter_file,
    manual_counter_path as shared_manual_counter_path,
    read_manual_counter as shared_read_manual_counter,
    write_manual_counter as shared_write_manual_counter,
)
from tg_push import TelegramPushService, extract_makerworld_model_url

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
VERSION_FILE_CANDIDATES = [
    BASE_DIR / "version.yml",
]
CONFIG_PATH = CONFIG_DIR / "config.json"
GALLERY_FLAGS_PATH = CONFIG_DIR / "gallery_flags.json"
COOKIE_STORE_PATH = CONFIG_DIR / "cookie.json"
LEGACY_CONFIG_PATH = BASE_DIR / "config.json"
LEGACY_GALLERY_FLAGS_PATH = BASE_DIR / "gallery_flags.json"
LEGACY_COOKIE_PATH = BASE_DIR / "cookie.txt"
TMP_DIR = BASE_DIR / "tmp"
MANUAL_DRAFT_ROOT = TMP_DIR / "manual_drafts"
DEFAULT_CONFIG = {
    "download_dir": "./data",
    "cookie_file": "./config/cookie.json",
    "logs_dir": "./logs",
    "local_batch_import": {
        "enabled": False,
        "watch_dirs": ["./watch"],
        "processed_dir_name": "_imported",
        "failed_dir_name": "_failed",
        "scan_interval_seconds": 300,
        "max_parse_workers": 2,
        "notify_on_finish": True,
        "duplicate_policy": "skip",
    },
    "local_3mf_organizer": deepcopy(DEFAULT_ORGANIZER_CONFIG),
    "notifications": {
        "telegram": {
            "enable_push": False,
            "bot_token": "",
            "chat_id": "",
            "web_base_url": "http://127.0.0.1:8001",
        },
        # 预留其他通知渠道扩展（例如企业微信）
        "wecom": {
            "enable_push": False,
            "enable_command": False,
        },
    },
}
ARCHIVE_LOCK = threading.Lock()
DEFAULT_GALLERY_FLAGS = {
    "favorites": [],
    "printed": [],
    "folders": [],
}
DEFAULT_COOKIE_STORE = {
    "cn": [],
    "global": [],
    "_meta": {
        "rr_index": {
            "cn": 0,
            "global": 0,
        }
    },
}
COOKIE_STATUS_ACTIVE = "active"
COOKIE_STATUS_COOLDOWN = "cooldown"
COOKIE_STATUS_INVALID = "invalid"
COOKIE_PLATFORM_SET = {"cn", "global"}
COOKIE_COOLDOWN_SECONDS = 30 * 60
MODEL_DOWNLOAD_STATUS_OK = "ok"
MODEL_DOWNLOAD_STATUS_FAILED = "failed"
MODEL_DOWNLOAD_ERROR_COOKIE_INVALID = "cookie_invalid"
MODEL_DOWNLOAD_ERROR_COOKIE_CHALLENGE = "cookie_challenge"
MODEL_DOWNLOAD_ERROR_RATE_LIMIT = "rate_limit"
MODEL_DOWNLOAD_ERROR_UNKNOWN = "unknown"


def load_version_values() -> dict:
    """读取 app/version.yml 中的简单 key:value 配置。"""
    for version_file in VERSION_FILE_CANDIDATES:
        if not version_file.exists():
            continue
        try:
            values = {}
            for raw in version_file.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                key, value = line.split(":", 1)
                values[key.strip()] = value.strip().strip("'\"")
            if values:
                return values
        except Exception:
            continue
    return {}


def load_project_version() -> str:
    """读取 app/version.yml 中的 project_version。"""
    ver = str(load_version_values().get("project_version") or "").strip()
    if ver:
        return ver
    return "0.0.0"


def is_multi_cookie_enabled() -> bool:
    raw = str(load_version_values().get("multi_cookie_enabled") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def to_short_version(version: str) -> str:
    parts = [p for p in str(version or "").split(".") if p]
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return version or "0.0"

# 日志
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("app")
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
logger.propagate = False
if not logger.handlers:
    # 文件
    fh = logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # 控制台
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
META_HISTORY_DIR_NAME = ".meta_history"
DEFAULT_META_NOTE = "本文件包含结构化数据与打印配置详情。"

def strip_html(value: str) -> str:
    if not value:
        return ""
    return _TAG_RE.sub("", value).strip()


def resolve_collect_iso(data: dict, meta_path: Path) -> str:
    ts = data.get("collectDate") if isinstance(data, dict) else None
    try:
        ts_int = int(ts)
        if ts_int > 0:
            return datetime.fromtimestamp(ts_int).isoformat()
    except Exception:
        pass
    return datetime.fromtimestamp(meta_path.stat().st_mtime).isoformat()


def resolve_model_dir(model_dir: str) -> Path:
    if not model_dir or "/" in model_dir or "\\" in model_dir:
        raise HTTPException(400, "model_dir 无效")
    if not (model_dir.startswith("MW_") or model_dir.startswith("Others_") or model_dir.startswith("LocalModel_")):
        raise HTTPException(400, "仅允许 MW_* / Others_* / LocalModel_* 目录")
    
    root = Path(CFG["download_dir"]).resolve()
    target = (root / model_dir).resolve()
    
    if not str(target).startswith(str(root)):
        raise HTTPException(400, "路径越界")
        
    if not target.exists() or not target.is_dir():
        # Fallback for Windows trailing space issues
        stripped_name = model_dir.strip()
        fallback_target = (root / stripped_name).resolve()
        if fallback_target.exists() and fallback_target.is_dir():
            return fallback_target
            
        # Second fallback: scan directory to find match ignoring trailing spaces
        for item in root.iterdir():
            if item.is_dir() and item.name.strip() == stripped_name:
                return item
                
        raise HTTPException(404, "目录不存在")
        
    return target


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


def save_upload_file(upload: UploadFile, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)

def list_files_in_dir(dir_path: Path, image_only: bool = False) -> List[str]:
    if not dir_path.exists():
        return []
    files = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        if p.name.startswith(".") or p.name.startswith("_"):
            continue
        if image_only and not re.search(r"\.(jpg|jpeg|png|gif|webp|bmp)$", p.name, re.IGNORECASE):
            continue
        files.append(p.name)
    return sorted(files)


def write_dir_index(dir_path: Path, files: List[str]):
    dir_path.mkdir(parents=True, exist_ok=True)
    payload = {"files": files, "updated_at": datetime.now().isoformat()}
    (dir_path / "_index.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json_file(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def ensure_collect_date(data: dict, fallback_ts: int) -> dict:
    if not isinstance(data, dict):
        return data
    ts = data.get("collectDate")
    try:
        ts_int = int(ts)
    except Exception:
        ts_int = 0
    if ts_int <= 0:
        data["collectDate"] = int(fallback_ts)
    else:
        data["collectDate"] = ts_int
    return data


def save_model_meta(meta_path: Path, data: dict, rebuild_offline_page: bool = True):
    meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if not rebuild_offline_page:
        return
    try:
        index_path = meta_path.parent / "index.html"
        if index_path.exists():
            index_path.write_text(build_index_html(data, {}), encoding="utf-8")
    except Exception as e:
        logger.warning("重建模型离线详情页失败: %s", e)


def backup_model_meta(meta_path: Path) -> Optional[Path]:
    if not meta_path.exists():
        return None
    history_dir = meta_path.parent / META_HISTORY_DIR_NAME
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = history_dir / f"meta_{stamp}.json"
    shutil.copy2(meta_path, backup_path)
    return backup_path


def list_model_meta_backups(model_dir: Path) -> List[dict]:
    history_dir = model_dir / META_HISTORY_DIR_NAME
    if not history_dir.exists():
        return []
    backups = []
    for path in sorted(history_dir.glob("meta_*.json"), reverse=True):
        try:
            stat = path.stat()
        except Exception:
            continue
        backups.append({
            "name": path.name,
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size": stat.st_size,
        })
    return backups


def parse_json_list(raw: str) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception as exc:
        raise HTTPException(400, f"列表参数格式无效: {exc}")
    if not isinstance(data, list):
        raise HTTPException(400, "列表参数必须是数组")
    values = []
    for item in data:
        if isinstance(item, str):
            val = item.strip()
            if val:
                values.append(val)
    return values


def split_tags_input(raw: str) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    if re.search(r"[,\n，；;]", text):
        parts = re.split(r"[\n,，；;]+", text)
    else:
        parts = re.split(r"\s+", text)
    tags = []
    seen = set()
    for item in parts:
        val = str(item or "").strip()
        if not val or val in seen:
            continue
        seen.add(val)
        tags.append(val)
    return tags


def validate_text_field(name: str, value: str, *, required: bool = False, max_length: int = 0) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise HTTPException(400, f"{name}不能为空")
    if _CONTROL_CHAR_RE.search(text):
        raise HTTPException(400, f"{name}包含非法控制字符")
    if max_length > 0 and len(text) > max_length:
        raise HTTPException(400, f"{name}长度不能超过 {max_length}")
    return text


def build_design_image_records(files: List[str]) -> List[dict]:
    return [
        {
            "index": idx,
            "originalUrl": "",
            "relPath": f"images/{fname}",
            "fileName": fname,
        }
        for idx, fname in enumerate(files, start=1)
    ]


def normalize_existing_design_images(meta: dict) -> List[str]:
    images = meta.get("images") if isinstance(meta.get("images"), dict) else {}
    design = images.get("design")
    if isinstance(design, list):
        names = [Path(str(item)).name for item in design if str(item).strip()]
        if names:
            return names
    records = meta.get("designImages")
    if isinstance(records, list):
        names = []
        for item in records:
            if not isinstance(item, dict):
                continue
            name = Path(str(item.get("fileName") or item.get("relPath") or "")).name
            if name:
                names.append(name)
        if names:
            return names
    return []


def update_editable_model_meta(
    meta: dict,
    *,
    title: str,
    tags: List[str],
    category: str,
    version_note: str,
    summary_html: str,
    design_images: List[str],
    cover_name: str,
) -> dict:
    if not isinstance(meta, dict):
        raise HTTPException(500, "meta.json 格式无效")

    summary_payload = make_summary_payload(strip_html(summary_html), [], summary_html)
    images = meta.get("images") if isinstance(meta.get("images"), dict) else {}
    cover_payload = meta.get("cover") if isinstance(meta.get("cover"), dict) else {}

    final_cover = cover_name or (design_images[0] if design_images else "")
    images["design"] = design_images
    images["cover"] = final_cover
    meta["images"] = images
    meta["designImages"] = build_design_image_records(design_images)
    meta["title"] = title
    meta["tags"] = tags
    meta["tagsOriginal"] = list(tags)
    meta["summary"] = summary_payload
    meta["category"] = category
    meta["versionNote"] = version_note
    meta["update_time"] = datetime.now().isoformat()

    cover_payload["url"] = str(cover_payload.get("url") or "")
    cover_payload["localName"] = final_cover
    cover_payload["relPath"] = f"images/{final_cover}" if final_cover else ""
    meta["cover"] = cover_payload

    if not meta.get("note"):
        meta["note"] = DEFAULT_META_NOTE
    return meta


def normalize_model_download_error_type(error_type: str) -> str:
    value = str(error_type or "").strip().lower()
    if value in {
        MODEL_DOWNLOAD_ERROR_COOKIE_INVALID,
        MODEL_DOWNLOAD_ERROR_COOKIE_CHALLENGE,
        MODEL_DOWNLOAD_ERROR_RATE_LIMIT,
    }:
        return value
    return MODEL_DOWNLOAD_ERROR_UNKNOWN


def classify_model_download_error_type(err: Optional[Exception]) -> str:
    text = str(err or "").strip()
    if "cf_clearance" in text or "cloudflare" in text.lower():
        return MODEL_DOWNLOAD_ERROR_COOKIE_CHALLENGE
    status = classify_cookie_error(err) if err else None
    if status == COOKIE_STATUS_INVALID:
        return MODEL_DOWNLOAD_ERROR_COOKIE_INVALID
    if status == COOKIE_STATUS_COOLDOWN:
        return MODEL_DOWNLOAD_ERROR_RATE_LIMIT
    return MODEL_DOWNLOAD_ERROR_UNKNOWN


def mark_model_download_failed(
    meta: dict,
    error_type: str,
    error_message: str = "",
    failed_at: Optional[str] = None,
) -> bool:
    if not isinstance(meta, dict):
        return False
    normalized_type = normalize_model_download_error_type(error_type)
    normalized_message = str(error_message or "").strip()
    normalized_time = str(failed_at or datetime.now().isoformat()).strip()
    changed = False

    if meta.get("download_status") != MODEL_DOWNLOAD_STATUS_FAILED:
        meta["download_status"] = MODEL_DOWNLOAD_STATUS_FAILED
        changed = True
    if meta.get("download_error_type") != normalized_type:
        meta["download_error_type"] = normalized_type
        changed = True
    if meta.get("download_error_message") != normalized_message:
        meta["download_error_message"] = normalized_message
        changed = True
    if meta.get("download_error_at") != normalized_time:
        meta["download_error_at"] = normalized_time
        changed = True
    return changed


def clear_model_download_failed(meta: dict) -> bool:
    if not isinstance(meta, dict):
        return False
    changed = False
    if meta.get("download_status") != MODEL_DOWNLOAD_STATUS_OK:
        meta["download_status"] = MODEL_DOWNLOAD_STATUS_OK
        changed = True
    for key in ("download_error_type", "download_error_message", "download_error_at"):
        if key in meta:
            meta.pop(key, None)
            changed = True
    return changed


def sync_offline_files_to_meta(model_dir: Path, attachments: Optional[List[str]] = None, printed: Optional[List[str]] = None):
    meta_path = model_dir / "meta.json"
    if not meta_path.exists():
        return

    fallback_ts = int(meta_path.stat().st_mtime)
    data = read_json_file(meta_path, {})
    if not isinstance(data, dict):
        return
    ensure_collect_date(data, fallback_ts)

    if attachments is None:
        attachments = list_files_in_dir(model_dir / "file", image_only=False)
    if printed is None:
        printed = list_files_in_dir(model_dir / "printed", image_only=True)

    offline = data.get("offlineFiles")
    if not isinstance(offline, dict):
        offline = {}
    offline["attachments"] = list(dict.fromkeys([str(x) for x in (attachments or [])]))
    offline["printed"] = list(dict.fromkeys([str(x) for x in (printed or [])]))
    data["offlineFiles"] = offline

    meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_ext(filename: str, fallback: str) -> str:
    suffix = Path(filename).suffix if filename else ""
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    return suffix if suffix else fallback


def pick_ext_from_url(url: str, fallback: str = ".jpg") -> str:
    try:
        suffix = Path(urlparse(url or "").path).suffix.lower()
    except Exception:
        suffix = ""
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return suffix
    return fallback


def localize_summary_external_images(summary_html: str, images_dir: Path) -> tuple[str, List[dict]]:
    html_in = (summary_html or "").strip()
    if not html_in:
        return html_in, []

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (MW-ManualImport)"})

    summary_images: List[dict] = []
    cached: dict[str, str] = {}
    counter = 1
    pattern = re.compile(r'(<img\b[^>]*\bsrc\s*=\s*)(["\'])([^"\']+)(\2)', re.IGNORECASE)

    def repl(match: re.Match) -> str:
        nonlocal counter
        prefix, quote, src, _tail = match.groups()
        src_clean = (src or "").strip()
        if not src_clean.lower().startswith(("http://", "https://")):
            return match.group(0)
        if src_clean in cached:
            local_name = cached[src_clean]
            return f"{prefix}{quote}./images/{local_name}{quote}"

        ext = pick_ext_from_url(src_clean, ".jpg")
        dest = ensure_unique_path(images_dir / f"summary_ext_{counter:02d}{ext}")
        try:
            resp = session.get(src_clean, timeout=20)
            resp.raise_for_status()
            content = resp.content or b""
            if not content:
                return match.group(0)
            dest.write_bytes(content)
        except Exception:
            return match.group(0)

        local_name = dest.name
        cached[src_clean] = local_name
        summary_images.append({
            "index": len(summary_images) + 1,
            "originalUrl": src_clean,
            "relPath": f"images/{local_name}",
            "fileName": local_name,
        })
        counter += 1
        return f"{prefix}{quote}./images/{local_name}{quote}"

    localized = pattern.sub(repl, html_in)
    return localized, summary_images


def sanitize_instance_storage_name(filename: str, fallback: str = "instance") -> str:
    raw = Path(str(filename or "")).name
    # 草稿会临时写成 s01_xxx.3mf，落正式目录时去掉该前缀
    raw = re.sub(r"^s\d+_", "", raw, flags=re.IGNORECASE)
    safe = sanitize_filename(raw).strip()
    if not safe:
        safe = f"{fallback}.3mf"
    if Path(safe).suffix.lower() != ".3mf":
        safe = f"{Path(safe).stem or fallback}.3mf"
    return safe


def is_image_upload(upload: UploadFile) -> bool:
    content_type = (upload.content_type or "").lower()
    if content_type.startswith("image/"):
        return True
    name = Path(upload.filename or "").name.lower()
    return name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"))


def reset_tmp_dir(tmp_dir: Path):
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for item in tmp_dir.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception as e:
            logger.warning("清理临时子项失败: %s (%s)", item, e)


def merge_dir_skip_existing(src: Path, dest: Path, log_obj: logging.Logger):
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        try:
            if item.is_dir():
                if target.exists() and target.is_dir():
                    merge_dir_skip_existing(item, target, log_obj)
                    try:
                        item.rmdir()
                    except Exception:
                        pass
                elif not target.exists():
                    shutil.move(str(item), str(target))
            else:
                if target.exists():
                    log_obj.info("目标已存在，覆盖更新: %s", target)
                    try:
                        target.unlink()
                    except Exception:
                        pass
                shutil.move(str(item), str(target))
        except Exception as e:
            log_obj.warning("移动临时文件失败: %s -> %s (%s)", item, target, e)


def finalize_tmp_archive(tmp_work_dir: Path, final_root: Path, log_obj: logging.Logger) -> Path:
    final_root.mkdir(parents=True, exist_ok=True)
    target = final_root / tmp_work_dir.name
    if not tmp_work_dir.exists():
        raise RuntimeError("临时目录不存在，无法转移结果")
    if not target.exists():
        shutil.move(str(tmp_work_dir), str(target))
        return target
    merge_dir_skip_existing(tmp_work_dir, target, log_obj)
    try:
        shutil.rmtree(tmp_work_dir)
    except Exception:
        pass
    return target


def parse_instance_descs(raw: str) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(item or "") for item in data]


def parse_instance_titles(raw: str) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(item or "").strip() for item in data]


def pick_instance_profile_summary(parsed: dict) -> str:
    """仅提取配置级简介，并过滤与模型简介重复的内容。"""
    if not isinstance(parsed, dict):
        return ""
    profile = str(parsed.get("profileSummaryText") or "").strip()
    if not profile:
        return ""
    model = str(parsed.get("summaryText") or "").strip()
    if not model:
        return profile
    p_norm = "".join(profile.split())
    m_norm = "".join(model.split())
    if not p_norm or not m_norm:
        return profile
    if p_norm == m_norm or p_norm in m_norm or m_norm in p_norm:
        return ""
    return profile


def parse_draft_instance_overrides(raw: str) -> List[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append({
            "enabled": bool(item.get("enabled", True)),
            "title": str(item.get("title") or "").strip(),
            "summary": str(item.get("summary") or "").strip(),
        })
    return out


def load_manual_draft(session_id: str) -> tuple[Path, dict]:
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(400, "draft_session_id 不能为空")
    if not re.fullmatch(r"[a-f0-9]{32}", sid):
        raise HTTPException(400, "draft_session_id 无效")
    session_dir = MANUAL_DRAFT_ROOT / sid
    draft_path = session_dir / "draft.json"
    if not draft_path.exists():
        raise HTTPException(404, "3MF 草稿不存在")
    try:
        data = json.loads(draft_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"3MF 草稿读取失败: {e}")
    if not isinstance(data, dict):
        raise HTTPException(500, "3MF 草稿格式无效")
    return session_dir, data


def discard_manual_draft(session_id: str) -> bool:
    sid = (session_id or "").strip()
    if not sid or not re.fullmatch(r"[a-f0-9]{32}", sid):
        return False
    session_dir = (MANUAL_DRAFT_ROOT / sid).resolve()
    root = MANUAL_DRAFT_ROOT.resolve()
    if not str(session_dir).startswith(str(root)):
        return False
    if not session_dir.exists() or not session_dir.is_dir():
        return False
    shutil.rmtree(session_dir, ignore_errors=True)
    return True


def next_instance_id(instances: List[dict]) -> int:
    max_id = 0
    for inst in instances or []:
        try:
            max_id = max(max_id, int(inst.get("id")))
        except Exception:
            continue
    return max_id + 1


def copy_draft_image(session_dir: Path, image_name: str, images_dir: Path) -> str:
    src = session_dir / "images" / image_name
    if not src.exists() or not src.is_file():
        return ""
    safe = sanitize_filename(src.name) or src.name
    dest = ensure_unique_path(images_dir / safe)
    shutil.copy2(src, dest)
    return dest.name


def copy_draft_file(session_dir: Path, file_name: str, files_dir: Path) -> str:
    src = session_dir / "file" / file_name
    if not src.exists() or not src.is_file():
        return ""
    safe = sanitize_filename(src.name) or src.name
    dest = ensure_unique_path(files_dir / safe)
    shutil.copy2(src, dest)
    return dest.name


def looks_like_v2_index(content: str) -> bool:
    if not content:
        return False
    return (
        "window.__OFFLINE_META__" in content
        or "/static/js/model.js" in content
        or 'id="loadingState"' in content
    )


def get_v2_frontend_assets() -> List[Path]:
    return [
        BASE_DIR / "templates" / "model.html",
        BASE_DIR / "static" / "css" / "variables.css",
        BASE_DIR / "static" / "css" / "components.css",
        BASE_DIR / "static" / "css" / "model.css",
        BASE_DIR / "static" / "js" / "model.js",
    ]


def latest_rebuild_source_mtime(meta_path: Path, assets: List[Path]) -> float:
    latest = meta_path.stat().st_mtime
    for p in assets:
        if p.exists():
            latest = max(latest, p.stat().st_mtime)
    return latest


def _candidate_instance_names(inst: dict) -> List[str]:
    if not isinstance(inst, dict):
        return []
    out: List[str] = []
    for key in ("fileName", "name", "sourceFileName", "localName", "title"):
        raw = str(inst.get(key) or "").strip()
        if not raw:
            continue
        name = Path(raw).name.strip()
        if not name:
            continue
        out.append(name)
        # 不能用 Path(name).suffix 判定：标题里可能出现 "0.28mm" 这类小数点，导致误判为“已有扩展名”
        if not name.lower().endswith(".3mf"):
            out.append(f"{name}.3mf")
        else:
            # 兼容历史错误归档：磁盘文件可能是 xxx.3mf.3mf
            out.append(f"{name}.3mf")
    # 去重并保持顺序
    return list(dict.fromkeys(out))


def resolve_instance_filename(inst: dict, instances_dir: Path) -> str:
    if not instances_dir.exists() or not instances_dir.is_dir():
        return ""
    candidates = _candidate_instance_names(inst)
    for name in candidates:
        if (instances_dir / name).is_file():
            return name
    return ""


def write_rebuild_report_log(
    *,
    result: dict,
    unresolved_records: List[dict],
):
    """将归档更新中的跳过/失败/未定位明细写入独立日志文件。"""
    logs_dir = Path(CFG["logs_dir"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    report_path = logs_dir / "rebuild_pages.log"

    details = result.get("details") if isinstance(result.get("details"), list) else []
    skipped_rows = [x for x in details if isinstance(x, dict) and x.get("status") == "skipped"]
    failed_rows = [x for x in details if isinstance(x, dict) and x.get("status") == "fail"]

    lines = []
    lines.append(f"[{datetime.now().isoformat()}] 归档更新执行报告")
    lines.append(
        "汇总: processed={processed}, updated={updated}, skipped={skipped}, failed={failed}, "
        "fixed_instance_files={fixed}, unresolved_instance_files={unresolved}".format(
            processed=int(result.get("processed") or 0),
            updated=int(result.get("updated") or 0),
            skipped=int(result.get("skipped") or 0),
            failed=int(result.get("failed") or 0),
            fixed=int(result.get("fixed_instance_files") or 0),
            unresolved=int(result.get("unresolved_instance_files") or 0),
        )
    )

    lines.append("跳过详情:")
    if skipped_rows:
        for row in skipped_rows:
            lines.append(f"- dir={row.get('dir')}, message={row.get('message')}")
    else:
        lines.append("- 无")

    lines.append("失败详情:")
    if failed_rows:
        for row in failed_rows:
            lines.append(f"- dir={row.get('dir')}, message={row.get('message')}")
    else:
        lines.append("- 无")

    lines.append("未定位实例详情:")
    if unresolved_records:
        for row in unresolved_records:
            lines.append(
                "- dir={dir}, inst_id={inst_id}, title={title}, name={name}, fileName={file_name}".format(
                    dir=row.get("dir") or "",
                    inst_id=row.get("inst_id") or "",
                    title=row.get("title") or "",
                    name=row.get("name") or "",
                    file_name=row.get("file_name") or "",
                )
            )
    else:
        lines.append("- 无")

    lines.append("-" * 80)
    with report_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return report_path


def rebuild_archived_pages(force: bool = False, backup: bool = False, dry_run: bool = False) -> dict:
    root = Path(CFG["download_dir"]).resolve()
    assets = get_v2_frontend_assets()
    missing_assets = [str(p) for p in assets if not p.exists()]
    if missing_assets:
        raise RuntimeError("缺少前端资源文件: " + ", ".join(missing_assets))

    meta_paths = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if meta_path.exists():
            meta_paths.append(meta_path)

    processed = 0
    updated = 0
    kept_v1 = 0
    skipped = 0
    failed = 0
    fixed_instance_files = 0
    unresolved_instance_files = 0
    unresolved_records = []
    details = []

    for meta_path in meta_paths:
        model_dir = meta_path.parent
        index_path = model_dir / "index.html"
        v1_index_path = model_dir / "index_v1.0.html"
        processed += 1

        try:
            fallback_ts = int(meta_path.stat().st_mtime)
            meta_raw = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = dict(meta_raw)
            ensure_collect_date(meta, fallback_ts)
            meta["offlineFiles"] = {
                "attachments": list_files_in_dir(model_dir / "file", image_only=False),
                "printed": list_files_in_dir(model_dir / "printed", image_only=True),
            }
            instances = meta.get("instances")
            if isinstance(instances, list):
                instances_dir = model_dir / "instances"
                for inst in instances:
                    if not isinstance(inst, dict):
                        continue
                    resolved_name = resolve_instance_filename(inst, instances_dir)
                    if not resolved_name:
                        unresolved_instance_files += 1
                        unresolved_records.append(
                            {
                                "dir": model_dir.name,
                                "inst_id": inst.get("id"),
                                "title": str(inst.get("title") or "").strip(),
                                "name": str(inst.get("name") or "").strip(),
                                "file_name": str(inst.get("fileName") or "").strip(),
                            }
                        )
                        continue
                    if str(inst.get("fileName") or "").strip() != resolved_name:
                        inst["fileName"] = resolved_name
                        fixed_instance_files += 1
            meta_changed = meta != meta_raw

            old_content = ""
            if index_path.exists():
                old_content = index_path.read_text(encoding="utf-8", errors="ignore")
            should_migrate_v1 = index_path.exists() and not v1_index_path.exists() and not looks_like_v2_index(old_content)
            latest_src = latest_rebuild_source_mtime(meta_path, assets)
            is_up_to_date = index_path.exists() and index_path.stat().st_mtime >= latest_src

            if not force and not should_migrate_v1 and is_up_to_date and not meta_changed:
                skipped += 1
                details.append({"dir": model_dir.name, "status": "skipped", "message": "up-to-date"})
                continue

            html = build_index_html(meta, {})

            if dry_run:
                if should_migrate_v1:
                    details.append({"dir": model_dir.name, "status": "plan", "message": "index.html -> index_v1.0.html"})
                details.append({"dir": model_dir.name, "status": "plan", "message": "write index.html"})
                updated += 1
                if should_migrate_v1:
                    kept_v1 += 1
                continue

            if should_migrate_v1:
                index_path.rename(v1_index_path)
                kept_v1 += 1

            if backup and index_path.exists():
                bak_path = model_dir / "index.html.bak"
                bak_path.write_text(index_path.read_text(encoding="utf-8"), encoding="utf-8")

            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            index_path.write_text(html, encoding="utf-8")
            updated += 1
            details.append({"dir": model_dir.name, "status": "ok", "message": "updated"})
        except Exception as e:
            failed += 1
            details.append({"dir": model_dir.name, "status": "fail", "message": str(e)})

    result = {
        "root": str(root),
        "processed": processed,
        "updated": updated,
        "kept_v1": kept_v1,
        "skipped": skipped,
        "failed": failed,
        "fixed_instance_files": fixed_instance_files,
        "unresolved_instance_files": unresolved_instance_files,
        "dry_run": dry_run,
        "details": details,
    }
    report_path = write_rebuild_report_log(result=result, unresolved_records=unresolved_records)
    result["report_log"] = str(report_path)
    return result


def make_summary_payload(text: str, summary_files: List[str], html_content: str = "") -> dict:
    clean_text = (text or "").strip()
    html_raw = (html_content or "").strip()
    parts = []
    if html_raw:
        # 基础过滤，避免内联脚本注入
        html_raw = re.sub(r"<script[\s\S]*?>[\s\S]*?</script>", "", html_raw, flags=re.IGNORECASE).strip()
        if html_raw:
            parts.append(html_raw)
    elif clean_text:
        safe_text = escape_html(clean_text).replace("\n", "<br>")
        parts.append(f"<p>{safe_text}</p>")
    for idx, name in enumerate(summary_files, start=1):
        parts.append(f'<img src="./images/{name}" alt="summary {idx}">')
    html = "\n".join(parts)
    summary_text = " ".join((clean_text or strip_html(html)).split())
    return {"raw": html, "html": html, "text": summary_text}


def manual_counter_path(cfg: Optional[dict] = None) -> Path:
    cfg_now = cfg if isinstance(cfg, dict) else CFG
    return shared_manual_counter_path(cfg_now["download_dir"])


def read_manual_counter(cfg: Optional[dict] = None) -> int:
    cfg_now = cfg if isinstance(cfg, dict) else CFG
    return shared_read_manual_counter(cfg_now["download_dir"])


def write_manual_counter(counter: int, cfg: Optional[dict] = None):
    cfg_now = cfg if isinstance(cfg, dict) else CFG
    shared_write_manual_counter(cfg_now["download_dir"], counter)


def ensure_manual_counter_file(cfg: Optional[dict] = None):
    cfg_now = cfg if isinstance(cfg, dict) else CFG
    shared_ensure_manual_counter_file(cfg_now["download_dir"])


def build_local_model_dir(title: str) -> tuple[str, Path]:
    cfg_now = load_config()
    base_name, candidate = shared_build_local_model_dir(cfg_now["download_dir"], title)
    try:
        CFG.update(cfg_now)
    except Exception:
        pass
    return base_name, candidate


# ---------- 配置与持久化 ----------
def _merge_defaults(target: dict, defaults: dict) -> bool:
    changed = False
    for k, v in defaults.items():
        if k not in target:
            target[k] = deepcopy(v)
            changed = True
            continue
        if isinstance(v, dict):
            current = target.get(k)
            if not isinstance(current, dict):
                target[k] = deepcopy(v)
                changed = True
                continue
            if _merge_defaults(current, v):
                changed = True
    return changed


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat()


def parse_iso_datetime(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _normalize_cookie_store(data) -> tuple[dict, bool]:
    changed = False
    if not isinstance(data, dict):
        data = deepcopy(DEFAULT_COOKIE_STORE)
        changed = True

    out = {"_meta": {"rr_index": {"cn": 0, "global": 0}}}
    meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
    rr_raw = meta.get("rr_index") if isinstance(meta.get("rr_index"), dict) else {}
    rr_norm = {}
    for key in ("cn", "global"):
        try:
            rr_norm[key] = max(int(rr_raw.get(key) or 0), 0)
        except Exception:
            rr_norm[key] = 0
            changed = True
    out["_meta"]["rr_index"] = rr_norm

    for key in ("cn", "global"):
        raw = data.get(key)
        items = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    value = str(item.get("value") or "").strip()
                    if not value:
                        continue
                    status = str(item.get("status") or COOKIE_STATUS_ACTIVE).strip().lower()
                    if status not in {COOKIE_STATUS_ACTIVE, COOKIE_STATUS_COOLDOWN, COOKIE_STATUS_INVALID}:
                        status = COOKIE_STATUS_ACTIVE
                        changed = True
                    cooldown_until = str(item.get("cooldown_until") or "").strip()
                    if status == COOKIE_STATUS_COOLDOWN:
                        until_dt = parse_iso_datetime(cooldown_until)
                        if until_dt and until_dt <= datetime.now():
                            status = COOKIE_STATUS_ACTIVE
                            cooldown_until = ""
                            changed = True
                    entry = {
                        "value": value,
                        "status": status,
                        "label": str(item.get("label") or "").strip(),
                        "last_error": str(item.get("last_error") or "").strip(),
                        "last_used_at": str(item.get("last_used_at") or "").strip(),
                        "updated_at": str(item.get("updated_at") or "").strip(),
                        "cooldown_until": cooldown_until,
                        "success_count": max(int(item.get("success_count") or 0), 0),
                        "failure_count": max(int(item.get("failure_count") or 0), 0),
                    }
                    items.append(entry)
                else:
                    value = str(item or "").strip()
                    if not value:
                        continue
                    items.append({
                        "value": value,
                        "status": COOKIE_STATUS_ACTIVE,
                        "label": "",
                        "last_error": "",
                        "last_used_at": "",
                        "updated_at": "",
                        "cooldown_until": "",
                        "success_count": 0,
                        "failure_count": 0,
                    })
                    changed = True
        elif isinstance(raw, str):
            value = raw.strip()
            items = [{
                "value": value,
                "status": COOKIE_STATUS_ACTIVE,
                "label": "",
                "last_error": "",
                "last_used_at": "",
                "updated_at": "",
                "cooldown_until": "",
                "success_count": 0,
                "failure_count": 0,
            }] if value else []
            changed = True
        else:
            items = []
            if key not in data:
                changed = True
        out[key] = items

    if set(data.keys()) != {"cn", "global", "_meta"}:
        changed = True
    return out, changed


def load_cookie_store(cfg: Optional[dict] = None) -> dict:
    ensure_config_dir()
    cfg_now = cfg if isinstance(cfg, dict) else CFG
    cookie_path = Path((cfg_now or {}).get("cookie_file") or COOKIE_STORE_PATH)
    changed = False
    data = None

    if cookie_path.exists():
        try:
            raw_text = cookie_path.read_text(encoding="utf-8").strip()
        except Exception:
            raw_text = ""
        if raw_text:
            try:
                data = json.loads(raw_text)
            except Exception:
                data = {"cn": [raw_text], "global": []}
                changed = True
        else:
            data = deepcopy(DEFAULT_COOKIE_STORE)
            changed = True
    elif LEGACY_COOKIE_PATH.exists():
        try:
            legacy_cookie = LEGACY_COOKIE_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            legacy_cookie = ""
        data = {
            "cn": [legacy_cookie] if legacy_cookie else [],
            "global": [],
        }
        changed = True
    else:
        data = deepcopy(DEFAULT_COOKIE_STORE)
        changed = True

    data, normalized = _normalize_cookie_store(data)
    changed = changed or normalized
    if changed:
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        cookie_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def save_cookie_store(cfg: Optional[dict], store: dict):
    ensure_config_dir()
    cfg_now = cfg if isinstance(cfg, dict) else CFG
    cookie_path = Path((cfg_now or {}).get("cookie_file") or COOKIE_STORE_PATH)
    normalized, _changed = _normalize_cookie_store(store)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def get_cookie_entries(cfg, platform: str) -> List[dict]:
    store = load_cookie_store(cfg)
    if platform not in COOKIE_PLATFORM_SET:
        return []
    items = store.get(platform)
    return items if isinstance(items, list) else []


def save_cookie_entries(cfg, platform: str, entries: List[dict]):
    if platform not in COOKIE_PLATFORM_SET:
        raise ValueError("platform 仅支持 cn 或 global")
    store = load_cookie_store(cfg)
    store[platform] = entries
    save_cookie_store(cfg, store)


def detect_cookie_platform(url: str) -> str:
    text = str(url or "").strip().lower()
    if "makerworld.com.cn" in text:
        return "cn"
    if "makerworld.com/" in text or text.endswith("makerworld.com"):
        return "global"
    return "cn"


def should_try_multiple_cookies() -> bool:
    return is_multi_cookie_enabled()


def _is_cookie_entry_available(entry: dict) -> bool:
    value = str((entry or {}).get("value") or "").strip()
    if not value:
        return False
    status = str((entry or {}).get("status") or COOKIE_STATUS_ACTIVE).strip().lower()
    if status == COOKIE_STATUS_INVALID:
        return False
    if status == COOKIE_STATUS_COOLDOWN:
        until_dt = parse_iso_datetime(str((entry or {}).get("cooldown_until") or ""))
        if until_dt and until_dt > datetime.now():
            return False
    return True


def build_cookie_candidate_order(cfg, platform: str) -> List[dict]:
    store = load_cookie_store(cfg)
    entries = store.get(platform) if isinstance(store.get(platform), list) else []
    if not entries:
        return []

    if not should_try_multiple_cookies():
        first = entries[0] if entries else None
        if first and _is_cookie_entry_available(first):
            return [{"index": 0, "entry": first}]
        if first:
            return [{"index": 0, "entry": first}]
        return []

    rr_meta = (((store.get("_meta") or {}).get("rr_index") or {}))
    try:
        start_idx = max(int(rr_meta.get(platform) or 0), 0)
    except Exception:
        start_idx = 0

    indexed = [{"index": idx, "entry": item} for idx, item in enumerate(entries)]
    available = [x for x in indexed if _is_cookie_entry_available(x["entry"])]
    if not available:
        return indexed

    start_idx = start_idx % len(available)
    return available[start_idx:] + available[:start_idx]


def update_cookie_rotation_cursor(cfg, platform: str, index: int):
    if platform not in COOKIE_PLATFORM_SET:
        return
    store = load_cookie_store(cfg)
    rr_meta = ((store.get("_meta") or {}).get("rr_index") or {})
    rr_meta[platform] = max(int(index) + 1, 0)
    store.setdefault("_meta", {})["rr_index"] = rr_meta
    save_cookie_store(cfg, store)


def mark_cookie_result(cfg, platform: str, index: int, status: str, error_text: str = ""):
    if platform not in COOKIE_PLATFORM_SET:
        return
    store = load_cookie_store(cfg)
    entries = store.get(platform) if isinstance(store.get(platform), list) else []
    if index < 0 or index >= len(entries):
        return
    item = dict(entries[index] or {})
    item["updated_at"] = now_iso()
    if status == "success":
        item["status"] = COOKIE_STATUS_ACTIVE
        item["cooldown_until"] = ""
        item["last_error"] = ""
        item["last_used_at"] = item["updated_at"]
        item["success_count"] = max(int(item.get("success_count") or 0), 0) + 1
        entries[index] = item
        store[platform] = entries
        save_cookie_store(cfg, store)
        update_cookie_rotation_cursor(cfg, platform, index)
        return

    item["failure_count"] = max(int(item.get("failure_count") or 0), 0) + 1
    item["last_error"] = str(error_text or "").strip()
    if status == COOKIE_STATUS_INVALID:
        item["status"] = COOKIE_STATUS_INVALID
        item["cooldown_until"] = ""
    elif status == COOKIE_STATUS_COOLDOWN:
        item["status"] = COOKIE_STATUS_COOLDOWN
        item["cooldown_until"] = datetime.fromtimestamp(datetime.now().timestamp() + COOKIE_COOLDOWN_SECONDS).isoformat()
    else:
        item["status"] = COOKIE_STATUS_ACTIVE
    entries[index] = item
    store[platform] = entries
    save_cookie_store(cfg, store)


def build_alert_payload(title: str, summary: str = "", lines: Optional[List[str]] = None) -> dict:
    return {
        "title": str(title or "通知").strip(),
        "summary": str(summary or "").strip(),
        "lines": [str(x or "").strip() for x in (lines or []) if str(x or "").strip()],
    }


def format_cookie_platform_label(platform: str) -> str:
    return "国际平台" if str(platform or "").strip().lower() == "global" else "国内平台"


def notify_cookie_download_issue(action_name: str, platform: str, index: int, status: str, error_text: str = ""):
    normalized = str(status or "").strip().lower()
    if normalized not in {COOKIE_STATUS_INVALID, COOKIE_STATUS_COOLDOWN}:
        return
    cookie_name = f"{format_cookie_platform_label(platform)} Cookie #{index + 1}"
    if normalized == COOKIE_STATUS_COOLDOWN:
        title = "Cookie 限流告警"
        state_text = "冷却中"
        reason = "触发限流，已进入冷却状态"
    else:
        title = "Cookie 失效告警"
        state_text = "失效/待验证"
        reason = "疑似失效或触发验证"
    payload = build_alert_payload(
        title=title,
        summary=f"{action_name}失败",
        lines=[
            f"平台：{format_cookie_platform_label(platform)}",
            f"Cookie：#{index + 1}",
            f"状态：{state_text}",
            f"说明：{reason}",
            f"错误：{str(error_text).strip()[:300]}" if error_text else "",
        ],
    )
    NOTIFIER.notify_alert(payload)


def notify_archive_missing_download_issue(result: dict):
    missing = result.get("missing_3mf") or []
    if not missing:
        return
    cookie_ctx = result.get("cookie_context") if isinstance(result.get("cookie_context"), dict) else {}
    platform = str(cookie_ctx.get("platform") or "cn").strip().lower()
    try:
        index = max(int(cookie_ctx.get("index") or 0), 0)
    except Exception:
        index = 0
    count = len(missing)
    payload = build_alert_payload(
        title="Cookie 失效告警",
        summary="模型归档存在 3MF 下载失败",
        lines=[
            f"平台：{format_cookie_platform_label(platform)}",
            f"Cookie：#{index + 1}",
            "状态：失效/待验证",
            f"失败数量：{count}",
            "说明：当前 Cookie 可能触发了验证或下载受限",
            "建议：先手动下载任意模型完成验证，再执行缺失重试",
        ],
    )
    NOTIFIER.notify_alert(payload)


def classify_cookie_error(err: Exception) -> Optional[str]:
    if isinstance(err, requests.HTTPError):
        resp = err.response
        code = resp.status_code if resp is not None else 0
        if code in (401, 403):
            return COOKIE_STATUS_INVALID
        if code == 429:
            return COOKIE_STATUS_COOLDOWN
    text = str(err or "")
    if "cf_clearance" in text or "Cloudflare" in text:
        return COOKIE_STATUS_INVALID
    return None


def run_with_cookie_failover(cfg, target_url: str, action_name: str, runner, notify_cookie_issue: bool = False):
    platform = detect_cookie_platform(target_url)
    candidates = build_cookie_candidate_order(cfg, platform)
    if not candidates:
        raise ValueError(f"请先设置 {platform} 平台 Cookie")

    last_err = None
    attempted = []
    for candidate in candidates:
        idx = int(candidate["index"])
        entry = candidate["entry"] if isinstance(candidate.get("entry"), dict) else {}
        cookie = str(entry.get("value") or "").strip()
        if not cookie:
            continue
        logger.info("%s: 使用 %s Cookie #%s", action_name, platform, idx + 1)
        try:
            result = runner(cookie, platform, idx, entry)
            mark_cookie_result(cfg, platform, idx, "success")
            return result
        except Exception as err:
            last_err = err
            attempted.append(idx + 1)
            status = classify_cookie_error(err)
            if status:
                mark_cookie_result(cfg, platform, idx, status, str(err))
                if notify_cookie_issue:
                    notify_cookie_download_issue(action_name, platform, idx, status, str(err))
                logger.warning("%s: %s Cookie #%s 标记为 %s", action_name, platform, idx + 1, status)
                continue
            raise

    if last_err is not None:
        raise last_err
    raise ValueError(f"{action_name} 未找到可用 Cookie，已尝试: {attempted}")


def ensure_runtime_support_files(cfg: Optional[dict] = None):
    ensure_config_dir()
    cfg_now = cfg if isinstance(cfg, dict) else CFG
    load_cookie_store(cfg_now)
    load_gallery_flags()


def load_raw_config() -> dict:
    ensure_config_dir()
    changed = False
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            cfg = deepcopy(DEFAULT_CONFIG)
            changed = True
    elif LEGACY_CONFIG_PATH.exists():
        try:
            cfg = json.loads(LEGACY_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            cfg = deepcopy(DEFAULT_CONFIG)
        changed = True
    else:
        cfg = deepcopy(DEFAULT_CONFIG)
        changed = True

    if not isinstance(cfg, dict):
        cfg = deepcopy(DEFAULT_CONFIG)
        changed = True

    if _merge_defaults(cfg, DEFAULT_CONFIG):
        changed = True

    if "manual_local_model_counter" in cfg:
        del cfg["manual_local_model_counter"]
        changed = True

    cookie_file = str(cfg.get("cookie_file") or "").strip()
    legacy_cookie_aliases = {"cookie.txt", "./cookie.txt", ".\\cookie.txt"}
    if not cookie_file or cookie_file in legacy_cookie_aliases:
        cfg["cookie_file"] = DEFAULT_CONFIG["cookie_file"]
        changed = True

    if changed:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def build_runtime_config(raw_cfg: dict) -> dict:
    ensure_config_dir()
    cfg = deepcopy(raw_cfg)
    cfg["download_dir"] = str((BASE_DIR / raw_cfg.get("download_dir", "data")).resolve())
    cfg["cookie_file"] = str((BASE_DIR / raw_cfg.get("cookie_file", "./config/cookie.json")).resolve())
    cfg["logs_dir"] = str((BASE_DIR / raw_cfg.get("logs_dir", "logs")).resolve())
    cfg["local_batch_import"] = build_runtime_batch_import_config(raw_cfg.get("local_batch_import"))
    cfg["local_3mf_organizer"] = build_runtime_local_3mf_organizer_config(raw_cfg.get("local_3mf_organizer"))
    Path(cfg["download_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["logs_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["cookie_file"]).parent.mkdir(parents=True, exist_ok=True)
    return cfg


def load_config():
    return build_runtime_config(load_raw_config())


def save_raw_config(raw_cfg: dict):
    ensure_config_dir()
    CONFIG_PATH.write_text(json.dumps(raw_cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_gallery_folder(folder: dict) -> Optional[dict]:
    if not isinstance(folder, dict):
        return None
    name = str(folder.get("name") or "").strip()
    if not name:
        return None
    folder_id = str(folder.get("id") or "").strip() or uuid.uuid4().hex
    description = str(folder.get("description") or "").strip()
    raw_dirs = folder.get("modelDirs")
    model_dirs = []
    if isinstance(raw_dirs, list):
        for item in raw_dirs:
            value = str(item or "").strip()
            if value and value not in model_dirs:
                model_dirs.append(value)
    created_at = str(folder.get("createdAt") or "").strip() or now_iso()
    updated_at = str(folder.get("updatedAt") or "").strip() or now_iso()
    return {
        "id": folder_id,
        "name": name,
        "description": description,
        "modelDirs": model_dirs,
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


def normalize_gallery_flags_data(data: dict) -> dict:
    payload = data if isinstance(data, dict) else {}
    favorites = []
    for item in payload.get("favorites") or []:
        value = str(item or "").strip()
        if value and value not in favorites:
            favorites.append(value)
    printed = []
    for item in payload.get("printed") or []:
        value = str(item or "").strip()
        if value and value not in printed:
            printed.append(value)
    folders = []
    seen_folder_ids = set()
    seen_folder_names = set()
    raw_folders = payload.get("folders") if isinstance(payload.get("folders"), list) else []
    for folder in raw_folders:
        normalized = normalize_gallery_folder(folder)
        if not normalized:
            continue
        if normalized["id"] in seen_folder_ids:
            continue
        lowered_name = normalized["name"].lower()
        if lowered_name in seen_folder_names:
            continue
        seen_folder_ids.add(normalized["id"])
        seen_folder_names.add(lowered_name)
        folders.append(normalized)
    return {
        "favorites": favorites,
        "printed": printed,
        "folders": folders,
    }


def load_gallery_flags() -> dict:
    ensure_config_dir()
    changed = False
    if GALLERY_FLAGS_PATH.exists():
        try:
            data = json.loads(GALLERY_FLAGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = deepcopy(DEFAULT_GALLERY_FLAGS)
            changed = True
    elif LEGACY_GALLERY_FLAGS_PATH.exists():
        try:
            data = json.loads(LEGACY_GALLERY_FLAGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = deepcopy(DEFAULT_GALLERY_FLAGS)
        changed = True
    else:
        data = deepcopy(DEFAULT_GALLERY_FLAGS)
        changed = True
    normalized = normalize_gallery_flags_data(data)
    if changed or normalized != data:
        GALLERY_FLAGS_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def save_gallery_flags(flags: dict):
    ensure_config_dir()
    data = normalize_gallery_flags_data(flags)
    GALLERY_FLAGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def remove_model_dirs_from_gallery_flags(flags: dict, model_dirs: List[str]) -> dict:
    targets = {str(item or "").strip() for item in (model_dirs or []) if str(item or "").strip()}
    if not targets:
        return normalize_gallery_flags_data(flags)
    data = normalize_gallery_flags_data(flags)
    data["favorites"] = [x for x in data.get("favorites", []) if x not in targets]
    data["printed"] = [x for x in data.get("printed", []) if x not in targets]
    folders = []
    for folder in data.get("folders", []):
        next_folder = dict(folder)
        next_folder["modelDirs"] = [x for x in folder.get("modelDirs", []) if x not in targets]
        next_folder["updatedAt"] = now_iso()
        folders.append(next_folder)
    data["folders"] = folders
    return data


def read_cookie(cfg, platform: str = "cn") -> str:
    entries = get_cookie_entries(cfg, platform)
    if entries:
        return str((entries[0] or {}).get("value") or "").strip()
    return ""


def write_cookie(cfg, cookie: str, platform: str = "cn", append: bool = False):
    platform_key = str(platform or "cn").strip().lower()
    if platform_key not in {"cn", "global"}:
        raise ValueError("platform 仅支持 cn 或 global")
    value = str(cookie or "").strip()
    entries = get_cookie_entries(cfg, platform_key)
    if append:
        existing_values = [str((x or {}).get("value") or "").strip() for x in entries]
        existing_values = [x for x in existing_values if x]
        if value and value not in existing_values:
            entries.append({
                "value": value,
                "status": COOKIE_STATUS_ACTIVE,
                "label": "",
                "last_error": "",
                "last_used_at": "",
                "updated_at": now_iso(),
                "cooldown_until": "",
                "success_count": 0,
                "failure_count": 0,
            })
    else:
        entries = [{
            "value": value,
            "status": COOKIE_STATUS_ACTIVE,
            "label": "",
            "last_error": "",
            "last_used_at": "",
            "updated_at": now_iso(),
            "cooldown_until": "",
            "success_count": 0,
            "failure_count": 0,
        }] if value else []
    save_cookie_entries(cfg, platform_key, entries)
    logger.info("Cookie 更新")
    # 额外记录更新时间
    with (Path(cfg["logs_dir"]) / "cookie.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()}\tupdate\t{platform_key}\n")


def get_telegram_runtime_cfg() -> dict:
    tg = (CFG.get("notifications") or {}).get("telegram") or {}
    return {
        "enable_push": bool(tg.get("enable_push", False)),
        "bot_token": str(tg.get("bot_token") or "").strip(),
        "chat_id": str(tg.get("chat_id") or "").strip(),
        "web_base_url": str(tg.get("web_base_url") or "http://127.0.0.1:8000").strip(),
    }


def tg_cookie_status_text() -> str:
    store = load_cookie_store(CFG)
    cn_count = len(store.get("cn") or [])
    global_count = len(store.get("global") or [])
    if cn_count <= 0 and global_count <= 0:
        return "🍪 Cookie 状态：未设置\n🕒 更新时间：-"
    cookie_path = Path(CFG["cookie_file"])
    updated = (
        datetime.fromtimestamp(cookie_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        if cookie_path.exists()
        else "-"
    )
    return (
        "🍪 Cookie 状态：✅ 已设置\n"
        f"🇨🇳 国内 Cookie：{cn_count}\n"
        f"🌍 国际 Cookie：{global_count}\n"
        f"🕒 更新时间：{updated}"
    )


def tg_archive_count_text() -> str:
    root = Path(CFG["download_dir"])
    if not root.exists():
        return "当前已归档模型数：0"
    count = 0
    for p in root.iterdir():
        if p.is_dir() and (p / "meta.json").exists():
            count += 1
    return f"当前已归档模型数：{count}"


def tg_search_models_text(keyword: str) -> str:
    kw = str(keyword or "").strip().lower()
    if not kw:
        return "🔎 请输入关键词。"

    base_url = get_telegram_runtime_cfg().get("web_base_url") or "http://127.0.0.1:8000"
    base_url = str(base_url).rstrip("/")

    root = Path(CFG["download_dir"])
    if not root.exists():
        return "📭 本地模型库为空。"

    matched = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        title = str(meta.get("title") or d.name)
        if kw in title.lower() or kw in d.name.lower():
            matched.append(
                {
                    "title": title,
                    "dir": d.name,
                    "url": f"{base_url}/v2/files/{d.name}",
                }
            )
    if not matched:
        return f"📭 未找到关键词“{keyword}”相关模型。"

    lines = [f"🔎 关键词“{keyword}”匹配到 {len(matched)} 个模型："]
    for idx, item in enumerate(matched[:10], start=1):
        lines.append(f"{idx}. {item['title']}\n   {item['url']}")
    if len(matched) > 10:
        lines.append(f"... 其余 {len(matched) - 10} 个结果未展示，请缩小关键词范围。")
    return "\n".join(lines)


def tg_get_base_url_text() -> str:
    base_url = str(get_telegram_runtime_cfg().get("web_base_url") or "http://127.0.0.1:8000").strip()
    return base_url.rstrip("/")


def tg_set_base_url(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if not re.match(r"^https?://", value, re.IGNORECASE):
        return "❌ 地址无效，请以 http:// 或 https:// 开头。"
    value = value.rstrip("/")

    raw_cfg = load_raw_config()
    notifications = raw_cfg.get("notifications") if isinstance(raw_cfg.get("notifications"), dict) else {}
    telegram_cfg = notifications.get("telegram") if isinstance(notifications.get("telegram"), dict) else {}
    telegram_cfg["web_base_url"] = value
    notifications["telegram"] = telegram_cfg
    raw_cfg["notifications"] = notifications
    save_raw_config(raw_cfg)
    CFG.update(build_runtime_config(raw_cfg))
    return f"✅ 在线地址前缀已更新为：\n{value}"


def tg_redownload_missing_3mf_text() -> str:
    try:
        result = retry_missing_downloads(CFG)
    except Exception as e:
        logger.exception("Telegram 触发缺失 3MF 重下失败")
        return f"❌ 缺失 3MF 重下失败：{e}"

    processed = int(result.get("processed") or 0)
    success = int(result.get("success") or 0)
    failed = int(result.get("failed") or 0)
    if processed <= 0:
        return "📭 缺失 3MF 列表为空，无需重下。"
    return (
        "✅ 缺失 3MF 重下完成\n"
        f"总数：{processed}\n"
        f"成功：{success}\n"
        f"失败：{failed}"
    )


def classify_archive_exception(err: Exception) -> tuple[str, str]:
    if isinstance(err, requests.HTTPError):
        resp = err.response
        code = resp.status_code if resp is not None else 0
        if code in (401, 403):
            return "归档失败告警", "请求被拒绝（401/403），请稍后重试或检查当前访问环境。"
        if code == 429:
            return "限流告警", "请求触发限流（429），请稍后重试。"
        return "归档失败告警", f"HTTP 错误：{code}"
    text = str(err)
    if "cf_clearance" in text or "Cloudflare" in text:
        return "归档失败告警", "检测到 Cloudflare 验证，请稍后重试或检查当前访问环境。"
    return "归档失败告警", text or "未知错误"


def infer_model_platform(meta: dict, inst: Optional[dict] = None) -> str:
    if isinstance(inst, dict):
        api_url = str(inst.get("apiUrl") or "").strip()
        if api_url:
            return detect_cookie_platform(api_url)
    source_url = str((meta or {}).get("url") or "").strip()
    if source_url:
        return detect_cookie_platform(source_url)
    return "cn"


def normalize_model_source(meta: dict, dir_name: str = "", inst: Optional[dict] = None) -> str:
    raw_source = str((meta or {}).get("source") or "").strip().lower()
    if raw_source in {"mw_cn", "mw_global", "localmodel", "others"}:
        return raw_source
    if dir_name.startswith("LocalModel_"):
        return "localmodel"
    if dir_name.startswith("Others_"):
        return "others"
    platform = infer_model_platform(meta or {}, inst=inst)
    return "mw_global" if platform == "global" else "mw_cn"


def parse_missing(cfg) -> List[dict]:
    missing_log = Path(cfg["logs_dir"]) / "missing_3mf.log"
    if not missing_log.exists():
        return []
    rows = []
    for line in missing_log.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 5:
            ts, base_name, inst_id, title, status = parts[:5]
        elif len(parts) >= 4:
            ts, base_name, inst_id, title = parts[:4]
            status = ""
        else:
            continue
        rows.append({"time": ts, "base_name": base_name, "inst_id": inst_id, "title": title, "status": status})
    return rows


def pick_instance_filename(inst: dict, name_hint: str = "") -> str:
    base = sanitize_filename(
        inst.get("fileName")
        or inst.get("name")
        or inst.get("sourceFileName")
        or inst.get("localName")
        or inst.get("title")
        or str(inst.get("id") or "model")
    ).strip()
    if not base:
        base = str(inst.get("id") or "model")
    # base 可能已经包含 .3mf，避免拼成 xxx.3mf.3mf
    if base.lower().endswith(".3mf"):
        return base
    return f"{base}.3mf"


def choose_unique_instance_filename(
    inst: dict,
    all_instances: List[dict],
    instances_dir: Path,
    name_hint: str = "",
) -> str:
    """
    为实例选择“不会与其它实例冲突”的 3MF 文件名。

    规则：
    1) 优先使用当前实例已有 fileName（若安全）
    2) 否则使用 pick_instance_filename 结果
    3) 若冲突（其它实例已占用或磁盘已存在）则自动追加 _{id} / _{n}
    """
    explicit_raw = str(inst.get("fileName") or "").strip()
    explicit_name = ""
    if explicit_raw:
        explicit_name = sanitize_filename(Path(explicit_raw).name)
        if explicit_name and not explicit_name.lower().endswith(".3mf"):
            explicit_name += ".3mf"

    preferred = explicit_name or pick_instance_filename(inst, name_hint)
    if not preferred:
        preferred = f"{inst.get('id') or 'model'}.3mf"

    used_by_others = set()
    for other in all_instances or []:
        if other is inst or not isinstance(other, dict):
            continue
        raw = str(other.get("fileName") or "").strip()
        if not raw:
            continue
        nm = sanitize_filename(Path(raw).name)
        if nm and not nm.lower().endswith(".3mf"):
            nm += ".3mf"
        if nm:
            used_by_others.add(nm)

    def _can_use(name: str) -> bool:
        if not name:
            return False
        if name in used_by_others:
            return False
        if explicit_name and name == explicit_name:
            return True
        if (instances_dir / name).exists():
            return False
        return True

    if _can_use(preferred):
        return preferred

    stem = Path(preferred).stem or str(inst.get("id") or "model")
    ext = Path(preferred).suffix or ".3mf"

    inst_id = str(inst.get("id") or "").strip()
    if inst_id:
        candidate = sanitize_filename(f"{stem}_{inst_id}{ext}")
        if _can_use(candidate):
            return candidate

    idx = 1
    while True:
        candidate = sanitize_filename(f"{stem}_{idx}{ext}")
        if _can_use(candidate):
            return candidate
        idx += 1


def retry_missing_downloads(cfg):
    missing_log = Path(cfg["logs_dir"]) / "missing_3mf.log"
    if not missing_log.exists():
        return {"processed": 0, "success": 0, "failed": 0, "details": []}

    lines = [line for line in missing_log.read_text(encoding="utf-8").splitlines() if line.strip()]

    remaining_lines = []
    details = []
    success_cnt = 0

    for line in lines:
        parts = line.split("\t")
        if len(parts) < 4:
            remaining_lines.append(line)
            details.append({"status": "fail", "message": "行格式异常", "raw": line})
            continue
        _ts, base_name, inst_id, _title = parts[:4]
        inst_id_str = str(inst_id).strip()
        base_dir = Path(cfg["download_dir"]) / base_name
        meta_path = base_dir / "meta.json"
        if not meta_path.exists():
            details.append({"status": "fail", "base_name": base_name, "inst_id": inst_id_str, "message": "meta.json 不存在"})
            remaining_lines.append(line)
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            details.append({"status": "fail", "base_name": base_name, "inst_id": inst_id_str, "message": f"meta.json 读取失败: {e}"})
            remaining_lines.append(line)
            continue

        instances = meta.get("instances") or []
        target = next((i for i in instances if str(i.get("id")) == inst_id_str), None)
        if not target:
            details.append({"status": "fail", "base_name": base_name, "inst_id": inst_id_str, "message": "meta 中未找到该实例"})
            remaining_lines.append(line)
            continue

        platform = infer_model_platform(meta, target)
        default_host = "makerworld.com.cn" if platform == "cn" else "makerworld.com"
        api_url = target.get("apiUrl") or f"https://{default_host}/api/v1/design-service/instance/{inst_id_str}/f3mf?type=download&fileType="
        try:
            inst_id_int = int(inst_id_str)
        except Exception:
            inst_id_int = inst_id_str

        selected_cookie = ""
        try:
            def _runner(cookie: str, _platform: str, _cookie_index: int, _entry: dict):
                nonlocal selected_cookie
                selected_cookie = cookie
                session = requests.Session()
                session.headers.update({"User-Agent": "Mozilla/5.0 (MW-Redownload)"})
                session.cookies.update(parse_cookies(cookie))
                return fetch_instance_3mf(session, inst_id_int, cookie, api_url)

            name3mf, dl_url, used_api_url = run_with_cookie_failover(
                cfg, api_url, f"缺失 3MF 重试 {inst_id_str}", _runner, notify_cookie_issue=True
            )
        except Exception as e:
            logger.error("实例 %s 获取 3MF 失败: %s", inst_id_str, e)
            details.append({"status": "fail", "base_name": base_name, "inst_id": inst_id_str, "message": f"接口获取失败: {e}"})
            remaining_lines.append(line)
            continue

        if not dl_url:
            details.append({"status": "fail", "base_name": base_name, "inst_id": inst_id_str, "message": "未返回下载地址"})
            remaining_lines.append(line)
            continue

        inst_dir = base_dir / "instances"
        inst_dir.mkdir(parents=True, exist_ok=True)
        file_name = choose_unique_instance_filename(target, instances, inst_dir, name3mf)
        dest = inst_dir / file_name
        used_existing = False
        try:
            if dest.exists():
                used_existing = True
                logger.info("实例 %s 已存在文件 %s，跳过重新下载", inst_id_str, dest)
            else:
                session = requests.Session()
                session.headers.update({"User-Agent": "Mozilla/5.0 (MW-Redownload)"})
                session.cookies.update(parse_cookies(selected_cookie))
                download_file(session, dl_url, dest)
        except Exception as e:
            logger.error("实例 %s 下载 3MF 失败: %s", inst_id_str, e)
            details.append({"status": "fail", "base_name": base_name, "inst_id": inst_id_str, "message": f"下载失败: {e}"})
            remaining_lines.append(line)
            continue

        target["downloadUrl"] = dl_url
        if used_api_url:
            target["apiUrl"] = used_api_url
        if name3mf:
            target["name"] = name3mf
        target["fileName"] = file_name
        if clear_model_download_failed(meta):
            logger.info("清除模型下载失败标记: %s", base_name)
        try:
            save_model_meta(meta_path, meta)
        except Exception as e:
            details.append({"status": "fail", "base_name": base_name, "inst_id": inst_id_str, "message": f"写入 meta.json 失败: {e}"})
            remaining_lines.append(line)
            continue

        success_cnt += 1
        details.append({
            "status": "ok",
            "base_name": base_name,
            "inst_id": inst_id_str,
            "file": dest.name,
            "used_existing": used_existing,
            "downloadUrl": dl_url,
        })
        logger.info("实例 %s 下载完成 -> %s", inst_id_str, dest)

    failed_cnt = len(lines) - success_cnt
    missing_log.write_text("\n".join(remaining_lines), encoding="utf-8")
    return {"processed": len(lines), "success": success_cnt, "failed": failed_cnt, "details": details}


def redownload_instance_by_id(cfg, inst_id: int):
    """
    按实例 ID 扫描已下载模型，重新获取下载地址并覆盖保存到 instances 目录。
    """
    root = Path(cfg["download_dir"])
    found = 0
    success = 0
    details = []

    for meta_path in root.glob("MW_*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        instances = meta.get("instances") or []
        target = next((i for i in instances if str(i.get("id")) == str(inst_id)), None)
        if not target:
            continue
        found += 1
        platform = infer_model_platform(meta, target)
        default_host = "makerworld.com.cn" if platform == "cn" else "makerworld.com"
        api_url = target.get("apiUrl") or f"https://{default_host}/api/v1/design-service/instance/{inst_id}/f3mf?type=download&fileType="
        selected_cookie = ""
        try:
            def _runner(cookie: str, _platform: str, _cookie_index: int, _entry: dict):
                nonlocal selected_cookie
                selected_cookie = cookie
                session = requests.Session()
                session.headers.update({"User-Agent": "Mozilla/5.0 (MW-Redownload-One)"})
                session.cookies.update(parse_cookies(cookie))
                return fetch_instance_3mf(session, inst_id, cookie, api_url)

            name3mf, dl_url, used_api_url = run_with_cookie_failover(
                cfg, api_url, f"实例重下 {inst_id}", _runner, notify_cookie_issue=True
            )
        except Exception as e:
            if mark_model_download_failed(meta, classify_model_download_error_type(e), str(e)):
                try:
                    save_model_meta(meta_path, meta)
                except Exception as save_err:
                    logger.warning("写入实例重下失败标记失败: %s", save_err)
            details.append({"status": "fail", "base_name": meta.get("baseName"), "inst_id": inst_id, "message": f"接口失败: {e}"})
            continue

        if not dl_url:
            details.append({"status": "fail", "base_name": meta.get("baseName"), "inst_id": inst_id, "message": "未返回下载地址"})
            continue

        base_dir = meta_path.parent
        inst_dir = base_dir / "instances"
        inst_dir.mkdir(parents=True, exist_ok=True)
        file_name = choose_unique_instance_filename(target, instances, inst_dir, name3mf or target.get("name") or "")
        dest = inst_dir / file_name
        if dest.exists():
            try:
                dest.unlink()
            except Exception:
                pass
        try:
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 (MW-Redownload-One)"})
            session.cookies.update(parse_cookies(selected_cookie))
            download_file(session, dl_url, dest)
        except Exception as e:
            if mark_model_download_failed(meta, classify_model_download_error_type(e), str(e)):
                try:
                    save_model_meta(meta_path, meta)
                except Exception as save_err:
                    logger.warning("写入实例下载失败标记失败: %s", save_err)
            details.append({"status": "fail", "base_name": meta.get("baseName"), "inst_id": inst_id, "message": f"下载失败: {e}"})
            continue

        target["downloadUrl"] = dl_url
        if used_api_url:
            target["apiUrl"] = used_api_url
        if name3mf:
            target["name"] = name3mf
        target["fileName"] = file_name
        clear_model_download_failed(meta)
        try:
            save_model_meta(meta_path, meta)
        except Exception as e:
            details.append({"status": "fail", "base_name": meta.get("baseName"), "inst_id": inst_id, "message": f"写入 meta.json 失败: {e}"})
            continue

        # 同步移除缺失日志里的该实例
        missing_log = Path(cfg["logs_dir"]) / "missing_3mf.log"
        if missing_log.exists():
            filtered = []
            for line in missing_log.read_text(encoding="utf-8").splitlines():
                parts = line.split("\t")
                if len(parts) >= 3 and parts[2] == str(inst_id):
                    continue
                filtered.append(line)
            missing_log.write_text("\n".join(filtered), encoding="utf-8")

        success += 1
        details.append({"status": "ok", "base_name": meta.get("baseName"), "inst_id": inst_id, "file": dest.name, "downloadUrl": dl_url})

    return {"found": found, "success": success, "failed": max(found - success, 0), "details": details}


def redownload_model_by_id(cfg, model_id: int):
    """
    按模型 ID (目录名 MW_{id}_*) 扫描，针对其中所有 instances 的 apiUrl 重新下载并更新 meta。
    """
    root = Path(cfg["download_dir"])
    targets = list(root.glob(f"MW_{model_id}_*/meta.json"))
    if not targets:
        return {"processed": 0, "success": 0, "failed": 0, "details": []}

    details = []
    success = 0
    processed = 0
    missing_log = Path(cfg["logs_dir"]) / "missing_3mf.log"
    missing_lines = missing_log.read_text(encoding="utf-8").splitlines() if missing_log.exists() else []

    for meta_path in targets:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            details.append({"status": "fail", "base_name": meta_path.parent.name, "message": f"读取 meta 失败: {e}"})
            continue

        instances = meta.get("instances") or []
        base_dir = meta_path.parent
        inst_dir = base_dir / "instances"
        inst_dir.mkdir(parents=True, exist_ok=True)

        for inst in instances:
            processed += 1
            inst_id = inst.get("id")
            platform = infer_model_platform(meta, inst)
            default_host = "makerworld.com.cn" if platform == "cn" else "makerworld.com"
            api_url = inst.get("apiUrl") or f"https://{default_host}/api/v1/design-service/instance/{inst_id}/f3mf?type=download&fileType="
            try:
                inst_id_int = int(inst_id) if inst_id is not None else inst_id
            except Exception:
                inst_id_int = inst_id
            selected_cookie = ""
            try:
                def _runner(cookie: str, _platform: str, _cookie_index: int, _entry: dict):
                    nonlocal selected_cookie
                    selected_cookie = cookie
                    session = requests.Session()
                    session.headers.update({"User-Agent": "Mozilla/5.0 (MW-Redownload-Model)"})
                    session.cookies.update(parse_cookies(cookie))
                    return fetch_instance_3mf(session, inst_id_int, cookie, api_url)

                name3mf, dl_url, used_api_url = run_with_cookie_failover(
                    cfg, api_url, f"模型重下 {model_id}/{inst_id}", _runner, notify_cookie_issue=True
                )
            except Exception as e:
                mark_model_download_failed(meta, classify_model_download_error_type(e), str(e))
                details.append({"status": "fail", "base_name": meta.get("baseName"), "inst_id": inst_id, "message": f"接口失败: {e}"})
                continue

            if not dl_url:
                details.append({"status": "fail", "base_name": meta.get("baseName"), "inst_id": inst_id, "message": "未返回下载地址"})
                continue

            file_name = choose_unique_instance_filename(inst, instances, inst_dir, name3mf or inst.get("name") or "")
            dest = inst_dir / file_name
            if dest.exists():
                try:
                    dest.unlink()
                except Exception:
                    pass
            try:
                session = requests.Session()
                session.headers.update({"User-Agent": "Mozilla/5.0 (MW-Redownload-Model)"})
                session.cookies.update(parse_cookies(selected_cookie))
                download_file(session, dl_url, dest)
            except Exception as e:
                mark_model_download_failed(meta, classify_model_download_error_type(e), str(e))
                details.append({"status": "fail", "base_name": meta.get("baseName"), "inst_id": inst_id, "message": f"下载失败: {e}"})
                continue

            inst["downloadUrl"] = dl_url
            if used_api_url:
                inst["apiUrl"] = used_api_url
            if name3mf:
                inst["name"] = name3mf
            inst["fileName"] = file_name
            clear_model_download_failed(meta)
            success += 1
            details.append({"status": "ok", "base_name": meta.get("baseName"), "inst_id": inst_id, "file": dest.name, "downloadUrl": dl_url})

            # 清理缺失记录中对应实例
            if missing_lines:
                missing_lines = [
                    ln for ln in missing_lines
                    if not (len(ln.split("\t")) >= 3 and ln.split("\t")[2] == str(inst_id))
                ]

        try:
            save_model_meta(meta_path, meta)
        except Exception as e:
            details.append({"status": "fail", "base_name": meta.get("baseName"), "message": f"写入 meta.json 失败: {e}"})

    if missing_log is not None:
        missing_log.write_text("\n".join(missing_lines), encoding="utf-8")

    failed = max(processed - success, 0)
    return {"processed": processed, "success": success, "failed": failed, "details": details}


def scan_gallery(cfg) -> List[dict]:
    root = Path(cfg["download_dir"])
    items = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith(".") or d.name.startswith("_"):
            continue
        if not (
            d.name.startswith("MW_")
            or d.name.startswith("Others_")
            or d.name.startswith("LocalModel_")
        ):
            continue
        meta = d / "meta.json"
        if not meta.exists():
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            images = data.get("images") or {}
            cover_name = images.get("cover") or ""
            cover_file = (d / "images" / cover_name).name if cover_name else ""
            summary_data = data.get("summary") or {}
            raw_summary = summary_data.get("text") or summary_data.get("raw") or summary_data.get("html") or ""
            instances = data.get("instances") or []
            published_at = None
            for inst in instances:
                ts = inst.get("publishTime")
                if ts and (published_at is None or ts < published_at):
                    published_at = ts
            author = data.get("author") or {}
            collected_at = resolve_collect_iso(data, meta)
            source_value = normalize_model_source(data, d.name)
            items.append({
                "baseName": data.get("baseName") or d.name,
                "title": data.get("title"),
                "id": data.get("id"),
                "cover": cover_file,
                "dir": d.name,
                "source": source_value,
                "tags": data.get("tags") or [],
                "summary": strip_html(raw_summary),
                "author": {
                    "name": author.get("name"),
                    "url": author.get("url"),
                    "avatarRelPath": author.get("avatarRelPath"),
                },
                "stats": data.get("stats") or {},
                "instanceCount": len(instances),
                "publishedAt": published_at,
                "collectedAt": collected_at,
            })
        except Exception:
            continue
    return items


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CFG = load_config()
ensure_runtime_support_files(CFG)
ensure_manual_counter_file(CFG)

TMP_DIR.mkdir(parents=True, exist_ok=True)
MANUAL_DRAFT_ROOT.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/files", StaticFiles(directory=CFG["download_dir"], html=True), name="files")
app.mount("/tmp", StaticFiles(directory=TMP_DIR), name="tmp")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Telegram 服务：根据配置决定是否推送/命令轮询
TG_SERVICE = TelegramPushService(
    cfg_getter=get_telegram_runtime_cfg,
    logger=logger,
    on_archive_url=lambda url: {},
    on_cookie_status=tg_cookie_status_text,
    on_count=tg_archive_count_text,
    on_search=tg_search_models_text,
    on_get_base_url=tg_get_base_url_text,
    on_set_base_url=tg_set_base_url,
    on_redownload_missing=tg_redownload_missing_3mf_text,
)
NOTIFIER = NotificationDispatcher(logger)
NOTIFIER.register("telegram", TG_SERVICE)


def handle_local_batch_import_report(report: dict):
    cfg_now = CFG if isinstance(CFG, dict) else load_config()
    local_cfg = cfg_now.get("local_batch_import") if isinstance(cfg_now.get("local_batch_import"), dict) else {}
    if not local_cfg.get("notify_on_finish"):
        return
    processed = int(report.get("processed") or 0)
    if processed <= 0:
        return
    payload = report.get("notify_payload") if isinstance(report.get("notify_payload"), dict) else {}
    if payload:
        NOTIFIER.notify_alert(payload)


LOCAL_BATCH_WATCHER = LocalBatchImportWatcher(
    cfg_getter=lambda: CFG,
    runner=lambda cfg: run_batch_import(cfg, logger=logger, source_label="watcher"),
    logger=logger,
    on_report=handle_local_batch_import_report,
)


def build_archive_notify_payload(result: dict, final_dir: Path) -> dict:
    base_url = str(get_telegram_runtime_cfg().get("web_base_url") or "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "action": result.get("action") or "created",
        "base_name": result.get("base_name") or final_dir.name,
        "title": "",
        "url": "",
        "cover_url": "",
        "online_url": f"{base_url}/v2/files/{final_dir.name}",
        "missing_count": len(result.get("missing_3mf") or []),
    }
    meta_path = final_dir / "meta.json"
    if not meta_path.exists():
        return payload
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        payload["title"] = str(data.get("title") or "")
        payload["url"] = str(data.get("url") or "")
        cover = data.get("cover") if isinstance(data.get("cover"), dict) else {}
        payload["cover_url"] = str(cover.get("url") or data.get("coverUrl") or "")
    except Exception:
        return payload
    return payload


def archive_model_with_lock(url: str) -> dict:
    model_url = extract_makerworld_model_url(url)
    if not model_url:
        raise ValueError("链接格式无效，仅支持 makerworld 模型链接")

    with ARCHIVE_LOCK:
        def _runner(cookie: str, platform: str, cookie_index: int, _entry: dict):
            reset_tmp_dir(TMP_DIR)
            logger.info("归档使用 %s Cookie #%s", platform, cookie_index + 1)
            result = archive_model(
                model_url,
                cookie,
                TMP_DIR,
                Path(CFG["logs_dir"]),
                logger,
                existing_root=Path(CFG["download_dir"]),
            )
            tmp_work_dir = Path(result.get("work_dir") or "")
            final_dir = finalize_tmp_archive(tmp_work_dir, Path(CFG["download_dir"]), logger)
            result["work_dir"] = str(final_dir.resolve())
            action = result.get("action") or "created"
            result["message"] = "模型已更新成功" if action == "updated" else "模型归档成功"
            result["notify_payload"] = build_archive_notify_payload(result, final_dir)
            result["cookie_context"] = {"platform": platform, "index": cookie_index}
            meta_path = final_dir / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    if result.get("missing_3mf"):
                        mark_model_download_failed(
                            meta,
                            MODEL_DOWNLOAD_ERROR_COOKIE_INVALID,
                            "模型 3MF 下载失败，需更新 Cookie 后重试",
                        )
                    else:
                        clear_model_download_failed(meta)
                    save_model_meta(meta_path, meta)
                except Exception as e:
                    logger.warning("归档后写入模型下载状态失败: %s", e)
            return result

        return run_with_cookie_failover(CFG, model_url, "模型归档", _runner)


def _tg_archive_callback(url: str) -> dict:
    try:
        return archive_model_with_lock(url)
    except Exception as e:
        title, detail = classify_archive_exception(e)
        NOTIFIER.notify_alert(build_alert_payload(title=title, summary=detail))
        raise


TG_SERVICE.set_archive_handler(_tg_archive_callback)


def sync_runtime_services():
    NOTIFIER.start()
    if LOCAL_BATCH_WATCHER.should_run():
        LOCAL_BATCH_WATCHER.start()
    else:
        LOCAL_BATCH_WATCHER.stop()


@app.on_event("startup")
async def startup_events():
    sync_runtime_services()


@app.on_event("shutdown")
async def shutdown_events():
    LOCAL_BATCH_WATCHER.stop()
    NOTIFIER.stop()


@app.get("/")
async def gallery_page():
    return FileResponse(BASE_DIR / "templates" / "gallery.html")


@app.get("/config")
async def config_page(request: Request):
    project_version = load_project_version()
    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "project_version": project_version,
            "project_version_short": to_short_version(project_version),
            "multi_cookie_enabled": is_multi_cookie_enabled(),
        },
    )


@app.get("/api/config")
async def api_config():
    cfg = load_config()
    cookie_path = Path(cfg["cookie_file"])
    cookie_time = cookie_path.stat().st_mtime if cookie_path.exists() else None
    cookie_store = load_cookie_store(cfg)
    tg = get_telegram_runtime_cfg()
    local_batch = cfg.get("local_batch_import") if isinstance(cfg.get("local_batch_import"), dict) else {}
    local_organizer = cfg.get("local_3mf_organizer") if isinstance(cfg.get("local_3mf_organizer"), dict) else {}
    return {
        "download_dir": cfg["download_dir"],
        "logs_dir": cfg["logs_dir"],
        "cookie_file": cfg["cookie_file"],
        "multi_cookie_enabled": is_multi_cookie_enabled(),
        "cookie_store": cookie_store,
        "cookie_counts": {
            "cn": len(cookie_store.get("cn") or []),
            "global": len(cookie_store.get("global") or []),
        },
        "manual_local_model_counter": read_manual_counter(cfg),
        "cookie_updated_at": datetime.fromtimestamp(cookie_time).isoformat() if cookie_time else None,
        "local_batch_import": {
            "enabled": bool(local_batch.get("enabled", False)),
            "watch_dirs": local_batch.get("watch_dirs") or [],
            "processed_dir_name": str(local_batch.get("processed_dir_name") or "_imported"),
            "failed_dir_name": str(local_batch.get("failed_dir_name") or "_failed"),
            "scan_interval_seconds": int(local_batch.get("scan_interval_seconds") or 300),
            "max_parse_workers": int(local_batch.get("max_parse_workers") or 2),
        },
        "local_3mf_organizer": {
            "root_dir": str(local_organizer.get("root_dir") or ""),
            "mode": str(local_organizer.get("mode") or DEFAULT_ORGANIZER_CONFIG["mode"]),
        },
        "notify": {
            "telegram": {
                "enable_push": tg["enable_push"],
            }
        },
    }


@app.get("/api/notify-config")
async def api_get_notify_config():
    return {"telegram": get_telegram_runtime_cfg()}


@app.post("/api/notify-config")
async def api_save_notify_config(body: dict):
    payload = body or {}
    tg_payload = payload.get("telegram") if isinstance(payload.get("telegram"), dict) else {}

    raw_cfg = load_raw_config()
    notifications = raw_cfg.get("notifications") if isinstance(raw_cfg.get("notifications"), dict) else {}
    telegram_cfg = notifications.get("telegram") if isinstance(notifications.get("telegram"), dict) else {}

    telegram_cfg["enable_push"] = bool(tg_payload.get("enable_push", telegram_cfg.get("enable_push", False)))
    telegram_cfg["bot_token"] = str(tg_payload.get("bot_token", telegram_cfg.get("bot_token", ""))).strip()
    telegram_cfg["chat_id"] = str(tg_payload.get("chat_id", telegram_cfg.get("chat_id", ""))).strip()
    telegram_cfg["web_base_url"] = str(
        tg_payload.get("web_base_url", telegram_cfg.get("web_base_url", "http://127.0.0.1:8000"))
    ).strip()

    notifications["telegram"] = telegram_cfg
    raw_cfg["notifications"] = notifications
    save_raw_config(raw_cfg)

    # 持久化后刷新运行时配置
    CFG.update(build_runtime_config(raw_cfg))
    sync_runtime_services()
    return {"status": "ok", "telegram": get_telegram_runtime_cfg()}


@app.post("/api/notify-test")
async def api_notify_test():
    result = NOTIFIER.send_test_connection()
    if result.get("status") != "ok":
        raise HTTPException(400, result.get("message") or "测试连接失败")
    return result


@app.get("/api/local-batch-import/config")
async def api_get_local_batch_import_config():
    raw_cfg = load_raw_config()
    runtime_cfg = load_config()
    batch_state = load_batch_import_state()
    return {
        "config": normalize_batch_import_config(raw_cfg.get("local_batch_import")),
        "runtime": runtime_cfg.get("local_batch_import") or {},
        "state": batch_state.get("meta") if isinstance(batch_state.get("meta"), dict) else {},
    }


@app.post("/api/local-batch-import/config")
async def api_save_local_batch_import_config(body: dict):
    payload = body or {}
    incoming = payload.get("local_batch_import") if isinstance(payload.get("local_batch_import"), dict) else payload
    local_cfg = normalize_batch_import_config(incoming)

    raw_cfg = load_raw_config()
    raw_cfg["local_batch_import"] = local_cfg
    save_raw_config(raw_cfg)

    CFG.update(build_runtime_config(raw_cfg))
    sync_runtime_services()
    return {
        "status": "ok",
        "config": local_cfg,
        "runtime": CFG.get("local_batch_import") or {},
    }


@app.get("/api/local-3mf-organizer/config")
async def api_get_local_3mf_organizer_config():
    raw_cfg = load_raw_config()
    runtime_cfg = load_config()
    organizer_state = load_local_3mf_organizer_state()
    runtime_organizer_cfg = runtime_cfg.get("local_3mf_organizer") if isinstance(runtime_cfg.get("local_3mf_organizer"), dict) else {}
    root_dir = str(runtime_organizer_cfg.get("root_dir") or "")
    return {
        "config": normalize_local_3mf_organizer_config(raw_cfg.get("local_3mf_organizer")),
        "runtime": runtime_organizer_cfg,
        "state": select_state_for_root(organizer_state, root_dir),
    }


@app.post("/api/local-3mf-organizer/config")
async def api_save_local_3mf_organizer_config(body: dict):
    payload = body or {}
    incoming = payload.get("local_3mf_organizer") if isinstance(payload.get("local_3mf_organizer"), dict) else payload
    organizer_cfg = normalize_local_3mf_organizer_config(incoming)

    raw_cfg = load_raw_config()
    raw_cfg["local_3mf_organizer"] = organizer_cfg
    save_raw_config(raw_cfg)

    CFG.update(build_runtime_config(raw_cfg))
    return {
        "status": "ok",
        "config": organizer_cfg,
        "runtime": CFG.get("local_3mf_organizer") or {},
    }


@app.post("/api/local-3mf-organizer/run")
async def api_run_local_3mf_organizer(body: dict):
    payload = body or {}
    cfg_now = load_config()
    runtime_cfg = cfg_now.get("local_3mf_organizer") if isinstance(cfg_now.get("local_3mf_organizer"), dict) else {}
    root_dir = str(payload.get("root_dir") or runtime_cfg.get("root_dir") or "").strip()
    mode = str(payload.get("mode") or runtime_cfg.get("mode") or DEFAULT_ORGANIZER_CONFIG["mode"]).strip().lower()
    dry_run = bool(payload.get("dry_run", False))
    try:
        limit = int(payload.get("limit") or 0)
    except Exception:
        limit = 0
    report = run_local_3mf_organizer(runtime_cfg, root_dir=root_dir, mode=mode, dry_run=dry_run, limit=limit)
    return report


@app.post("/api/local-batch-import/scan")
async def api_local_batch_import_scan(body: dict):
    payload = body or {}
    paths = payload.get("paths") if isinstance(payload.get("paths"), list) else None
    force = bool(payload.get("force", False))
    cfg_now = load_config()
    return scan_batch_import(cfg_now, explicit_paths=paths, force=force)


@app.post("/api/local-batch-import/run")
async def api_local_batch_import_run(body: dict):
    payload = body or {}
    paths = payload.get("paths") if isinstance(payload.get("paths"), list) else None
    force = bool(payload.get("force", False))
    cfg_now = load_config()
    source_label = str(payload.get("source_label") or "watcher").strip().lower() or "watcher"
    report = run_batch_import(cfg_now, explicit_paths=paths, force=force, logger=logger, source_label=source_label)
    handle_local_batch_import_report(report)
    return report


@app.post("/api/local-batch-import/run-upload")
async def api_local_batch_import_run_upload(
    files: List[UploadFile] = File(...),
    force: str = Form("true"),
):
    file_list = [f for f in (files or []) if f and f.filename]
    if not file_list:
        raise HTTPException(400, "请至少上传一个文件")

    force_flag = str(force or "").strip().lower() in {"1", "true", "yes", "on"}
    session_dir = TMP_DIR / "batch_import_uploads" / uuid.uuid4().hex
    session_dir.mkdir(parents=True, exist_ok=True)
    staged_paths: List[str] = []
    skipped_files: List[str] = []

    try:
        for idx, upload in enumerate(file_list, start=1):
            raw_name = str(upload.filename or "").strip()
            rel_path = raw_name.replace("\\", "/").lstrip("/")
            if Path(rel_path).suffix.lower() != ".3mf":
                skipped_files.append(raw_name)
                continue
            safe_name = sanitize_filename(Path(rel_path).name) or f"upload_{idx}.3mf"
            staged = session_dir / f"{idx:04d}_{safe_name}"
            data = await upload.read()
            if not data:
                skipped_files.append(raw_name)
                continue
            staged.write_bytes(data)
            staged_paths.append(str(staged))

        if not staged_paths:
            raise HTTPException(400, "未识别到有效的 3MF 文件")

        cfg_now = load_config()
        report = run_batch_import(
            cfg_now,
            explicit_paths=staged_paths,
            force=force_flag,
            logger=logger,
            source_label="manual",
        )
        if skipped_files:
            report["skipped_upload_files"] = skipped_files
        handle_local_batch_import_report(report)
        return report
    finally:
        shutil.rmtree(session_dir, ignore_errors=True)


@app.post("/api/cookie")
async def api_cookie(body: dict):
    payload = body or {}
    platform = str(payload.get("platform") or "cn").strip().lower()
    append = bool(payload.get("append", False))
    cookies = payload.get("cookies")

    if isinstance(cookies, list):
        cleaned = [str(x or "").strip() for x in cookies if str(x or "").strip()]
        if not cleaned:
            raise HTTPException(400, "cookies 不能为空")
        store = load_cookie_store(CFG)
        if platform not in {"cn", "global"}:
            raise HTTPException(400, "platform 仅支持 cn 或 global")
        if append:
            current = store.get(platform) if isinstance(store.get(platform), list) else []
            store[platform] = list(dict.fromkeys([*current, *cleaned]))
        else:
            store[platform] = cleaned
        save_cookie_store(CFG, store)
    else:
        cookie = str(payload.get("cookie") or "").strip()
        if not cookie:
            raise HTTPException(400, "cookie 不能为空")
        try:
            write_cookie(CFG, cookie, platform=platform, append=append)
        except ValueError as e:
            raise HTTPException(400, str(e))
    return {
        "status": "ok",
        "updated_at": datetime.now().isoformat(),
        "cookie_file": CFG["cookie_file"],
        "cookie_store": load_cookie_store(CFG),
    }


@app.get("/api/cookies")
async def api_get_cookies():
    return {
        "multi_cookie_enabled": is_multi_cookie_enabled(),
        "cookie_store": load_cookie_store(CFG),
        "cookie_file": CFG["cookie_file"],
    }


@app.post("/api/cookies")
async def api_save_cookies(body: dict):
    payload = body or {}
    store = payload.get("cookie_store")
    if not isinstance(store, dict):
        raise HTTPException(400, "cookie_store 格式错误")
    normalized, _changed = _normalize_cookie_store(store)
    save_cookie_store(CFG, normalized)
    return {
        "status": "ok",
        "updated_at": now_iso(),
        "multi_cookie_enabled": is_multi_cookie_enabled(),
        "cookie_store": load_cookie_store(CFG),
        "cookie_file": CFG["cookie_file"],
    }


@app.post("/api/archive")
async def api_archive(body: dict):
    url = (body or {}).get("url", "").strip()
    if not url:
        raise HTTPException(400, "url 不能为空")
    try:
        result = archive_model_with_lock(url)
        NOTIFIER.notify_success(result.get("notify_payload") or {})
        if len(result.get("missing_3mf") or []) > 0:
            notify_archive_missing_download_issue(result)
        return {"status": "ok", **result}
    except ValueError as e:
        err_text = str(e)
        if "链接格式无效" not in err_text:
            title, detail = classify_archive_exception(e)
            NOTIFIER.notify_alert(build_alert_payload(title=title, summary=detail))
        raise HTTPException(400, str(e))
    except requests.HTTPError as e:
        resp = e.response
        snippet = ""
        if resp is not None:
            snippet = (resp.text or "")[:300]
            logger.error("归档失败 HTTP %s: %s", resp.status_code, snippet)
        else:
            logger.error("归档失败 HTTP: %s", e)
        title, detail = classify_archive_exception(e)
        NOTIFIER.notify_alert(build_alert_payload(title=title, summary=detail))
        raise HTTPException(500, f"归档失败: {e} 片段: {snippet}")
    except Exception as e:
        logger.exception("归档失败")
        title, detail = classify_archive_exception(e)
        NOTIFIER.notify_alert(build_alert_payload(title=title, summary=detail))
        raise HTTPException(500, f"归档失败: {e}")
    finally:
        try:
            reset_tmp_dir(TMP_DIR)
        except Exception as e:
            logger.warning("清理临时目录失败: %s", e)


@app.post("/api/archive/rebuild-pages")
async def api_rebuild_archived_pages(body: dict = None):
    payload = body or {}
    force = bool(payload.get("force", False))
    backup = bool(payload.get("backup", False))
    dry_run = bool(payload.get("dry_run", False))
    try:
        result = rebuild_archived_pages(force=force, backup=backup, dry_run=dry_run)
        return {"status": "ok", **result}
    except Exception as e:
        logger.exception("更新已归档页面失败")
        raise HTTPException(500, f"更新已归档页面失败: {e}")


@app.get("/api/logs/missing-3mf")
async def api_missing():
    return parse_missing(CFG)


@app.post("/api/logs/missing-3mf/redownload")
async def api_redownload_missing():
    try:
        result = retry_missing_downloads(CFG)
        return {"status": "ok", **result}
    except Exception as e:
        logger.exception("缺失 3MF 重试下载失败")
        raise HTTPException(500, f"重试下载失败: {e}")


@app.get("/api/bambu/download/{hex_path}.3mf")
async def api_bambu_download(hex_path: str):
    import urllib.parse
    logger.info(f"Bambu Studio 请求下载 (Hex的路径): {hex_path}")
    try:
        rel_path = bytes.fromhex(hex_path).decode('utf-8')
    except Exception:
        logger.error("Hex 路径解码失败")
        raise HTTPException(400, "无效的文件路径编码")
        
    full_path = Path(CFG["download_dir"]) / rel_path
    if not full_path.is_file():
        logger.error(f"找不到文件: {full_path}")
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")
        
    filename = full_path.name
    encoded_filename = urllib.parse.quote(filename)
    logger.info(f"成功提供文件: {filename}")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
    }
    return FileResponse(full_path, headers=headers)


@app.get("/api/bambu/model/{model_dir}/instance/{inst_id}.3mf")
async def api_bambu_download_instance(model_dir: str, inst_id: int):
    import urllib.parse

    target = resolve_model_dir(model_dir)
    meta_path = target / "meta.json"
    instances_dir = target / "instances"
    if not meta_path.exists() or not instances_dir.exists():
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    data = read_json_file(meta_path, {})
    instances = data.get("instances") if isinstance(data, dict) else None
    if not isinstance(instances, list):
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    target_inst = next((x for x in instances if isinstance(x, dict) and str(x.get("id")) == str(inst_id)), None)
    if not target_inst:
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    resolved_name = resolve_instance_filename(target_inst, instances_dir)
    if not resolved_name:
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    full_path = (instances_dir / resolved_name).resolve()
    if not str(full_path).startswith(str(instances_dir.resolve())) or not full_path.is_file():
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    if str(target_inst.get("fileName") or "").strip() != resolved_name:
        target_inst["fileName"] = resolved_name
        try:
            meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("回填实例 fileName 失败: %s / %s", model_dir, inst_id)

    encoded_filename = urllib.parse.quote(full_path.name)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
    }
    return FileResponse(full_path, headers=headers, media_type="application/octet-stream")


@app.get("/api/bambu/model/{model_dir}/instance/{inst_id}/{display_name}")
async def api_bambu_download_instance_named(model_dir: str, inst_id: int, display_name: str):
    import urllib.parse

    target = resolve_model_dir(model_dir)
    meta_path = target / "meta.json"
    instances_dir = target / "instances"
    if not meta_path.exists() or not instances_dir.exists():
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    data = read_json_file(meta_path, {})
    instances = data.get("instances") if isinstance(data, dict) else None
    if not isinstance(instances, list):
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    target_inst = next((x for x in instances if isinstance(x, dict) and str(x.get("id")) == str(inst_id)), None)
    if not target_inst:
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    resolved_name = resolve_instance_filename(target_inst, instances_dir)
    if not resolved_name:
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    full_path = (instances_dir / resolved_name).resolve()
    if not str(full_path).startswith(str(instances_dir.resolve())) or not full_path.is_file():
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    # 运行时自愈
    if str(target_inst.get("fileName") or "").strip() != resolved_name:
        target_inst["fileName"] = resolved_name
        try:
            meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("回填实例 fileName 失败: %s / %s", model_dir, inst_id)

    # display_name 仅用于 Bambu 链接显示，文件实际读取仍以 inst_id 解析
    encoded_filename = urllib.parse.quote(resolved_name)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
    }
    return FileResponse(full_path, headers=headers, media_type="application/octet-stream")


@app.post("/api/instances/{inst_id}/redownload")
async def api_redownload_instance(inst_id: int):
    try:
        result = redownload_instance_by_id(CFG, inst_id)
        if result.get("found", 0) == 0:
            raise HTTPException(404, "未找到该实例")
        return {"status": "ok", **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("实例重下失败")
        raise HTTPException(500, f"重下失败: {e}")


@app.post("/api/models/{model_id}/redownload")
async def api_redownload_model(model_id: int):
    try:
        result = redownload_model_by_id(CFG, model_id)
        if result.get("processed", 0) == 0:
            raise HTTPException(404, "未找到该模型或 meta")
        return {"status": "ok", **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("模型重下失败")
        raise HTTPException(500, f"重下失败: {e}")


@app.delete("/api/logs/missing-3mf/{index:int}")
async def api_delete_missing(index: int):
    missing_log = Path(CFG["logs_dir"]) / "missing_3mf.log"
    if not missing_log.exists():
        raise HTTPException(404, "日志不存在")
    
    lines = missing_log.read_text(encoding="utf-8").splitlines()
    if index < 0 or index >= len(lines):
        raise HTTPException(400, "索引超出范围")
    
    lines.pop(index)
    missing_log.write_text("\n".join(lines), encoding="utf-8")
    logger.info("删除缺失记录 #%d", index)
    return {"status": "ok"}


@app.get("/api/gallery")
async def api_gallery():
    return scan_gallery(CFG)


@app.get("/api/gallery/flags")
async def api_gallery_flags():
    return load_gallery_flags()


@app.post("/api/gallery/flags")
async def api_save_gallery_flags(body: dict):
    payload = body if isinstance(body, dict) else {}
    save_gallery_flags(payload)
    return {"status": "ok"}


@app.get("/api/models/{model_dir}/attachments")
async def api_list_attachments(model_dir: str):
    target = resolve_model_dir(model_dir)
    attach_dir = target / "file"
    files = list_files_in_dir(attach_dir, image_only=False)
    write_dir_index(attach_dir, files)
    sync_offline_files_to_meta(target, attachments=files)
    return {"files": files}


@app.post("/api/models/{model_dir}/attachments")
async def api_upload_attachment(model_dir: str, file: UploadFile = File(...)):
    if file is None or not file.filename:
        raise HTTPException(400, "附件不能为空")
    target = resolve_model_dir(model_dir)
    safe_name = sanitize_filename(Path(file.filename).name)
    if not safe_name:
        safe_name = "attachment"
    attach_dir = target / "file"
    attach_dir.mkdir(parents=True, exist_ok=True)
    dest = attach_dir / safe_name
    if dest.exists():
        stem = dest.stem or "attachment"
        suffix = dest.suffix
        idx = 1
        while True:
            candidate = attach_dir / f"{stem}_{idx}{suffix}"
            if not candidate.exists():
                dest = candidate
                break
            idx += 1
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.exception("附件保存失败")
        raise HTTPException(500, f"附件保存失败: {e}")
    files = list_files_in_dir(attach_dir, image_only=False)
    write_dir_index(attach_dir, files)
    sync_offline_files_to_meta(target, attachments=files)
    return {"status": "ok", "file": dest.name}


@app.get("/api/models/{model_dir}/printed")
async def api_list_printed(model_dir: str):
    target = resolve_model_dir(model_dir)
    printed_dir = target / "printed"
    files = list_files_in_dir(printed_dir, image_only=True)
    write_dir_index(printed_dir, files)
    sync_offline_files_to_meta(target, printed=files)
    return {"files": files}


@app.post("/api/models/{model_dir}/printed")
async def api_upload_printed(model_dir: str, file: UploadFile = File(...)):
    if file is None or not file.filename:
        raise HTTPException(400, "图片不能为空")
    if not is_image_upload(file):
        raise HTTPException(400, "仅支持图片文件")
    target = resolve_model_dir(model_dir)
    safe_name = sanitize_filename(Path(file.filename).name)
    if not safe_name:
        safe_name = f"printed{pick_ext(file.filename, '.jpg')}"
    printed_dir = target / "printed"
    printed_dir.mkdir(parents=True, exist_ok=True)
    dest = printed_dir / safe_name
    if dest.exists():
        stem = dest.stem or "printed"
        suffix = dest.suffix
        idx = 1
        while True:
            candidate = printed_dir / f"{stem}_{idx}{suffix}"
            if not candidate.exists():
                dest = candidate
                break
            idx += 1
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.exception("打印成品保存失败")
        raise HTTPException(500, f"打印成品保存失败: {e}")
    files = list_files_in_dir(printed_dir, image_only=True)
    write_dir_index(printed_dir, files)
    sync_offline_files_to_meta(target, printed=files)
    return {"status": "ok", "file": dest.name}


@app.get("/api/models/{model_dir}/history")
async def api_model_history(model_dir: str):
    target = resolve_model_dir(model_dir)
    return {"items": list_model_meta_backups(target)}


@app.post("/api/models/{model_dir}/edit")
async def api_edit_model(
    model_dir: str,
    title: str = Form(""),
    tags: str = Form(""),
    category: str = Form(""),
    version_note: str = Form(""),
    summary_html: str = Form(""),
    keep_design_images: str = Form("[]"),
    cover_name: str = Form(""),
    design_images: List[UploadFile] = File([]),
):
    target = resolve_model_dir(model_dir)
    meta_path = target / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "meta.json 不存在")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"读取 meta.json 失败: {e}")
    if not isinstance(meta, dict):
        raise HTTPException(500, "meta.json 格式无效")

    title_value = validate_text_field("标题", title, required=True, max_length=120)
    category_value = validate_text_field("分类", category, max_length=40)
    version_note_value = validate_text_field("版本备注", version_note, max_length=200)
    summary_value = validate_text_field("说明", summary_html, max_length=50000)
    tag_list = split_tags_input(tags)
    if len(tag_list) > 30:
        raise HTTPException(400, "标签数量不能超过 30")
    for tag in tag_list:
        validate_text_field("标签", tag, max_length=32)

    existing_design = normalize_existing_design_images(meta)
    keep_list_raw = parse_json_list(keep_design_images)
    keep_list = []
    keep_seen = set()
    for item in keep_list_raw:
        name = Path(item).name
        if name in existing_design and name not in keep_seen:
            keep_seen.add(name)
            keep_list.append(name)

    images_dir = target / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    uploaded_names: List[str] = []
    for upload in design_images:
        if not upload or not upload.filename:
            continue
        if not is_image_upload(upload):
            raise HTTPException(400, f"仅支持图片文件: {upload.filename}")
        safe_name = sanitize_filename(Path(upload.filename).name)
        if not safe_name:
            safe_name = f"design_{len(existing_design) + len(uploaded_names) + 1:02d}{pick_ext(upload.filename, '.jpg')}"
        dest = ensure_unique_path(images_dir / safe_name)
        save_upload_file(upload, dest)
        uploaded_names.append(dest.name)

    final_design_images = keep_list + uploaded_names
    cover_value = Path(str(cover_name or "")).name
    if cover_value and cover_value not in final_design_images:
        raise HTTPException(400, "封面图片必须来自当前保留图片或新上传图片")

    deleted_names = [name for name in existing_design if name not in keep_list]

    backup_path = backup_model_meta(meta_path)
    meta = update_editable_model_meta(
        meta,
        title=title_value,
        tags=tag_list,
        category=category_value,
        version_note=version_note_value,
        summary_html=summary_value,
        design_images=final_design_images,
        cover_name=cover_value,
    )
    save_model_meta(meta_path, meta)
    sync_offline_files_to_meta(target)

    for name in deleted_names:
        try:
            (images_dir / name).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("删除旧设计图失败: %s (%s)", name, e)

    return {
        "status": "ok",
        "message": "模型信息已保存",
        "backup": backup_path.name if backup_path else "",
        "design_image_count": len(final_design_images),
    }


@app.post("/api/models/{model_dir}/history/restore-latest")
async def api_restore_model_latest_backup(model_dir: str):
    target = resolve_model_dir(model_dir)
    meta_path = target / "meta.json"
    backups = list_model_meta_backups(target)
    if not backups:
        raise HTTPException(404, "没有可恢复的备份")

    latest_name = backups[0]["name"]
    if "/" in latest_name or "\\" in latest_name:
        raise HTTPException(400, "备份文件名无效")
    backup_path = target / META_HISTORY_DIR_NAME / latest_name
    if not backup_path.exists():
        raise HTTPException(404, "备份文件不存在")

    try:
        backup_data = json.loads(backup_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"读取备份失败: {e}")
    if not isinstance(backup_data, dict):
        raise HTTPException(500, "备份内容格式无效")

    current_backup = backup_model_meta(meta_path)
    save_model_meta(meta_path, backup_data)
    sync_offline_files_to_meta(target)
    return {
        "status": "ok",
        "message": "已恢复最近一次备份",
        "restored_from": latest_name,
        "backup_of_current": current_backup.name if current_backup else "",
    }


@app.post("/api/manual/3mf/parse")
async def api_manual_parse_3mf(files: List[UploadFile] = File(...)):
    file_list = [f for f in (files or []) if f and f.filename]
    if not file_list:
        raise HTTPException(400, "请至少上传一个 3MF 文件")

    sid = uuid.uuid4().hex
    session_dir = MANUAL_DRAFT_ROOT / sid
    session_dir.mkdir(parents=True, exist_ok=True)

    parsed_items = []
    errors = []
    for idx, upload in enumerate(file_list, start=1):
        name = upload.filename or f"instance_{idx}.3mf"
        if Path(name).suffix.lower() != ".3mf":
            errors.append({"file": name, "message": "仅支持 .3mf 文件"})
            continue
        try:
            data = await upload.read()
            if not data:
                errors.append({"file": name, "message": "文件为空"})
                continue
            parsed = parse_3mf_to_session(data, name, session_dir, idx)
            parsed_items.append(parsed)
        except Exception as e:
            errors.append({"file": name, "message": str(e)})

    if not parsed_items:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(400, "3MF 解析失败: 未识别到有效内容")

    draft = build_draft_payload(sid, parsed_items)
    draft["createdAt"] = datetime.now().isoformat()
    draft["errors"] = errors
    (session_dir / "draft.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "ok",
        "draft": attach_preview_urls(draft, prefix="manual_drafts"),
    }


@app.delete("/api/manual/drafts/{session_id}")
async def api_delete_manual_draft(session_id: str):
    removed = discard_manual_draft(session_id)
    return {"status": "ok", "removed": removed}


@app.post("/api/manual/drafts/{session_id}/discard")
async def api_discard_manual_draft(session_id: str):
    removed = discard_manual_draft(session_id)
    return {"status": "ok", "removed": removed}


@app.post("/api/models/{model_dir}/instances/import-3mf")
async def api_model_add_instance_from_3mf(
    model_dir: str,
    file: UploadFile = File(...),
    title: str = Form(""),
    summary: str = Form(""),
):
    if file is None or not file.filename:
        raise HTTPException(400, "3MF 文件不能为空")
    if Path(file.filename).suffix.lower() != ".3mf":
        raise HTTPException(400, "仅支持 .3mf 文件")

    target = resolve_model_dir(model_dir)
    meta_path = target / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "meta.json 不存在")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"读取 meta.json 失败: {e}")
    if not isinstance(meta, dict):
        raise HTTPException(500, "meta.json 格式无效")

    images_dir = target / "images"
    instances_dir = target / "instances"
    images_dir.mkdir(parents=True, exist_ok=True)
    instances_dir.mkdir(parents=True, exist_ok=True)

    temp_session = TMP_DIR / "instance_imports" / uuid.uuid4().hex
    temp_session.mkdir(parents=True, exist_ok=True)
    try:
        parsed = parse_3mf_to_session(await file.read(), file.filename, temp_session, 1)
        # 复制 3MF
        src_3mf = temp_session / "instances" / str(parsed.get("instanceFile") or "")
        if not src_3mf.exists():
            raise HTTPException(500, "未解析到有效 3MF 文件")
        source_name = str(parsed.get("sourceName") or file.filename or src_3mf.name)
        storage_name = sanitize_instance_storage_name(source_name, fallback=f"instance_{next_instance_id(meta.get('instances') if isinstance(meta.get('instances'), list) else [])}")
        dest_3mf = ensure_unique_path(instances_dir / storage_name)
        shutil.copy2(src_3mf, dest_3mf)

        # 复制实例图片
        pics = []
        pic_files = parsed.get("profilePictureFiles") or parsed.get("designFiles") or []
        for pidx, fn in enumerate(pic_files, start=1):
            copied = copy_draft_image(temp_session, str(fn), images_dir)
            if not copied:
                continue
            pics.append({
                "index": pidx,
                "url": "",
                "relPath": f"images/{copied}",
                "fileName": copied,
                "isRealLifePhoto": 0,
            })

        # 复制盘缩略图
        plates = []
        for pidx, plate in enumerate(parsed.get("plates") or [], start=1):
            src_th = str(plate.get("thumbnailFile") or "")
            copied_th = copy_draft_image(temp_session, src_th, images_dir)
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

        instances = meta.get("instances")
        if not isinstance(instances, list):
            instances = []
            meta["instances"] = instances
        new_id = next_instance_id(instances)
        inst_title = (title or "").strip() or str(parsed.get("profileTitle") or parsed.get("modelTitle") or dest_3mf.stem)
        # 实例介绍只允许来自配置描述（ProfileDescription），且过滤与模型简介重复的内容
        inst_summary = (summary or "").strip() or pick_instance_profile_summary(parsed)

        instances.append({
            "id": new_id,
            "title": inst_title,
            "titleTranslated": "",
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
            "summary": inst_summary,
            "summaryTranslated": "",
            "name": dest_3mf.name,
            "fileName": dest_3mf.name,
            "sourceFileName": Path(source_name).name,
            "downloadUrl": "",
            "apiUrl": "",
        })

        meta["update_time"] = datetime.now().isoformat()
        ensure_collect_date(meta, int(meta_path.stat().st_mtime))
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        sync_offline_files_to_meta(target)
        (target / "index.html").write_text(build_index_html(meta, {}), encoding="utf-8")

        return {"status": "ok", "message": f"模型已更新成功：已添加打印配置 {inst_title}", "instance_id": new_id}
    finally:
        shutil.rmtree(temp_session, ignore_errors=True)


@app.post("/api/models/manual")
async def api_manual_import(
    title: str = Form(""),
    modelLink: str = Form(""),
    sourceLink: str = Form(""),
    summary: str = Form(""),
    summary_html: str = Form(""),
    tags: str = Form(""),
    draft_session_id: str = Form(""),
    draft_instance_overrides: str = Form(""),
    cover: Optional[UploadFile] = File(None),
    design_images: List[UploadFile] = File([]),
    instance_files: List[UploadFile] = File([]),
    instance_pictures: List[UploadFile] = File([]),
    attachments: List[UploadFile] = File([]),
    instance_descs: str = Form(""),
    instance_titles: str = Form(""),
    instance_picture_counts: str = Form(""),
):
    draft_data = {}
    draft_session_dir: Optional[Path] = None
    if (draft_session_id or "").strip():
        draft_session_dir, draft_data = load_manual_draft(draft_session_id)

    name = (title or "").strip() or str(draft_data.get("title") or "").strip()
    if not name:
        raise HTTPException(400, "模型名称不能为空")

    base_name, model_dir = build_local_model_dir(name)
    images_dir = model_dir / "images"
    instances_dir = model_dir / "instances"
    files_dir = model_dir / "file"
    images_dir.mkdir(parents=True, exist_ok=True)
    instances_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    design_names: List[str] = []
    summary_names: List[str] = []
    cover_name = ""
    draft_overrides = parse_draft_instance_overrides(draft_instance_overrides)

    if draft_data and draft_session_dir is not None:
        draft_cover = str(draft_data.get("coverFile") or "").strip()
        if draft_cover:
            copied = copy_draft_image(draft_session_dir, draft_cover, images_dir)
            if copied:
                cover_name = copied

        for draft_img in draft_data.get("designFiles") or []:
            copied = copy_draft_image(draft_session_dir, str(draft_img), images_dir)
            if copied:
                design_names.append(copied)

        for draft_att in draft_data.get("attachments") or []:
            copy_draft_file(draft_session_dir, str(draft_att), files_dir)

    if cover and cover.filename:
        ext = pick_ext(cover.filename, ".jpg")
        cover_name = f"cover{ext}"
        save_upload_file(cover, images_dir / cover_name)

    for idx, upload in enumerate(design_images, start=1):
        if not upload or not upload.filename:
            continue
        ext = pick_ext(upload.filename, ".jpg")
        fname = f"design_{len(design_names) + idx:02d}{ext}"
        save_upload_file(upload, images_dir / fname)
        design_names.append(fname)

    if not cover_name and design_names:
        cover_name = design_names[0]
    if not cover_name and summary_names:
        cover_name = summary_names[0]
    if cover_name and not design_names:
        design_names = [cover_name]

    desc_list = parse_instance_descs(instance_descs)
    title_list = parse_instance_titles(instance_titles)
    try:
        pic_counts_raw = json.loads(instance_picture_counts) if instance_picture_counts else []
    except Exception:
        pic_counts_raw = []
    pic_counts = []
    if isinstance(pic_counts_raw, list):
        for item in pic_counts_raw:
            try:
                pic_counts.append(max(int(item), 0))
            except Exception:
                pic_counts.append(0)
    pic_offset = 0
    instances = []
    curr_inst_id = 1

    if draft_data and draft_session_dir is not None:
        draft_instances = draft_data.get("instances") or []
        for i, ditem in enumerate(draft_instances, start=1):
            ov = draft_overrides[i - 1] if (i - 1) < len(draft_overrides) else {}
            if ov and not ov.get("enabled", True):
                continue
            src_name = str(ditem.get("name") or "").strip()
            src_3mf = draft_session_dir / "instances" / src_name
            if not src_name or not src_3mf.exists():
                continue
            source_name = str(ditem.get("sourceFileName") or src_name)
            storage_name = sanitize_instance_storage_name(source_name, fallback=f"instance_{i}")
            dest_3mf = ensure_unique_path(instances_dir / storage_name)
            shutil.copy2(src_3mf, dest_3mf)

            pics = []
            for pidx, pic in enumerate(ditem.get("pictures") or [], start=1):
                src_pic_name = str(pic.get("fileName") or Path(str(pic.get("relPath") or "")).name)
                copied = copy_draft_image(draft_session_dir, src_pic_name, images_dir)
                if not copied:
                    continue
                pics.append({
                    "index": pidx,
                    "url": "",
                    "relPath": f"images/{copied}",
                    "fileName": copied,
                    "isRealLifePhoto": int(pic.get("isRealLifePhoto") or 0),
                })

            plates = []
            for pidx, plate in enumerate(ditem.get("plates") or [], start=1):
                src_th = str(plate.get("thumbnailFile") or Path(str(plate.get("thumbnailRelPath") or "")).name)
                copied_th = copy_draft_image(draft_session_dir, src_th, images_dir)
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

            inst_title = str((ov.get("title") if isinstance(ov, dict) else "") or ditem.get("title") or dest_3mf.stem)
            inst_summary = str((ov.get("summary") if isinstance(ov, dict) else "") or ditem.get("summary") or "")
            instances.append({
                "id": curr_inst_id,
                "title": inst_title,
                "titleTranslated": "",
                "summary": inst_summary,
                "summaryTranslated": "",
                "name": dest_3mf.name,
                "fileName": dest_3mf.name,
                "sourceFileName": Path(source_name).name,
                "publishTime": str(ditem.get("publishTime") or ""),
                "downloadCount": 0,
                "printCount": 0,
                "prediction": int(ditem.get("prediction") or 0),
                "weight": int(ditem.get("weight") or 0),
                "materialCnt": int(ditem.get("materialCnt") or 0),
                "materialColorCnt": int(ditem.get("materialColorCnt") or 0),
                "needAms": bool(ditem.get("needAms") or False),
                "plates": plates,
                "pictures": pics,
                "instanceFilaments": ditem.get("instanceFilaments") if isinstance(ditem.get("instanceFilaments"), list) else [],
                "downloadUrl": "",
                "apiUrl": "",
            })
            curr_inst_id += 1

    for idx, upload in enumerate(instance_files, start=1):
        if not upload or not upload.filename:
            continue
        source_name = Path(upload.filename).name if upload and upload.filename else f"instance_{idx}.3mf"
        storage_name = sanitize_instance_storage_name(source_name, fallback=f"instance_{idx}")
        dest = ensure_unique_path(instances_dir / storage_name)

        raw_data = await upload.read()
        if not raw_data:
            continue
        dest.write_bytes(raw_data)

        parsed_inst: dict = {}
        temp_session = TMP_DIR / "manual_instance_parse" / uuid.uuid4().hex
        temp_session.mkdir(parents=True, exist_ok=True)
        try:
            parsed_inst = parse_3mf_to_session(raw_data, source_name, temp_session, idx)
        except Exception:
            parsed_inst = {}

        manual_title = (title_list[idx - 1] if (idx - 1) < len(title_list) else "").strip()
        parsed_title = str(parsed_inst.get("profileTitle") or parsed_inst.get("modelTitle") or "").strip() if parsed_inst else ""
        inst_title = manual_title or parsed_title or dest.stem

        manual_summary = (desc_list[idx - 1] if (idx - 1) < len(desc_list) else "").strip()
        # 手动添加实例时，避免把模型主介绍误写入实例介绍
        parsed_summary = pick_instance_profile_summary(parsed_inst) if parsed_inst else ""
        inst_summary = manual_summary or parsed_summary

        pics = []
        parsed_pic_files = (parsed_inst.get("profilePictureFiles") or parsed_inst.get("designFiles") or []) if parsed_inst else []
        for pidx, fn in enumerate(parsed_pic_files, start=1):
            copied = copy_draft_image(temp_session, str(fn), images_dir)
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
        for pidx, plate in enumerate(parsed_inst.get("plates") or [], start=1):
            src_th = str(plate.get("thumbnailFile") or "")
            copied_th = copy_draft_image(temp_session, src_th, images_dir)
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
        shutil.rmtree(temp_session, ignore_errors=True)

        wanted = pic_counts[idx - 1] if (idx - 1) < len(pic_counts) else 0
        for pic_idx in range(1, wanted + 1):
            if pic_offset >= len(instance_pictures):
                break
            pic_upload = instance_pictures[pic_offset]
            pic_offset += 1
            if not pic_upload or not pic_upload.filename:
                continue
            ext = pick_ext(pic_upload.filename, ".jpg")
            fname = f"inst{idx:02d}_pic_{pic_idx:02d}{ext}"
            save_upload_file(pic_upload, images_dir / fname)
            pics.append({
                "index": len(pics) + 1,
                "url": "",
                "relPath": f"images/{fname}",
                "fileName": fname,
                "isRealLifePhoto": 0,
            })
        instances.append({
            "id": curr_inst_id,
            "title": inst_title,
            "summary": inst_summary,
            "name": dest.name,
            "fileName": dest.name,
            "sourceFileName": source_name,
            "publishTime": str(parsed_inst.get("creationDate") or "") if parsed_inst else "",
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
        })
        curr_inst_id += 1

    for upload in attachments:
        if not upload or not upload.filename:
            continue
        safe_name = sanitize_filename(Path(upload.filename).name) or "attachment"
        dest = ensure_unique_path(files_dir / safe_name)
        save_upload_file(upload, dest)

    tag_list = [t for t in re.split(r"\s+", (tags or "").strip()) if t]
    summary_text = (summary or "").strip() or str(draft_data.get("summary") or "").strip()
    summary_html_value = (summary_html or "").strip() or str(draft_data.get("summaryHtml") or "").strip()
    summary_payload = make_summary_payload(summary_text, summary_names, summary_html_value)
    localized_html, ext_summary_images = localize_summary_external_images(summary_payload.get("html") or "", images_dir)
    if localized_html:
        summary_payload["html"] = localized_html
        summary_payload["raw"] = localized_html
        summary_payload["text"] = " ".join(strip_html(localized_html).split())

    summary_records = [
        {"index": idx, "originalUrl": "", "relPath": f"images/{fname}", "fileName": fname}
        for idx, fname in enumerate(summary_names, start=1)
    ]
    existing_summary = {x.get("fileName") for x in summary_records}
    for rec in ext_summary_images:
        fn = rec.get("fileName")
        if fn and fn not in existing_summary:
            summary_records.append({
                "index": len(summary_records) + 1,
                "originalUrl": rec.get("originalUrl") or "",
                "relPath": rec.get("relPath") or f"images/{fn}",
                "fileName": fn,
            })
            existing_summary.add(fn)
    summary_names_all = [x.get("fileName") for x in summary_records if x.get("fileName")]

    author_url = (sourceLink or modelLink or "").strip()
    author_name = "手动导入"
    if draft_data and str(draft_data.get("designer") or "").strip():
        author_name = str(draft_data.get("designer") or "").strip()
    meta = {
        "baseName": base_name,
        "source": "LocalModel",
        "url": (modelLink or sourceLink or "").strip(),
        "id": None,
        "slug": "",
        "title": name,
        "titleTranslated": "",
        "coverUrl": "",
        "tags": tag_list,
        "tagsOriginal": tag_list,
        "stats": {"likes": 0, "favorites": 0, "downloads": 0, "prints": 0, "views": 0},
        "cover": {
            "url": "",
            "localName": cover_name,
            "relPath": f"images/{cover_name}" if cover_name else "",
        },
        "author": {
            "name": author_name,
            "url": author_url,
            "avatarUrl": "",
            "avatarLocal": "",
            "avatarRelPath": "",
        },
        "images": {
            "cover": cover_name,
            "design": design_names,
            "summary": summary_names_all,
        },
        "designImages": [
            {"index": idx, "originalUrl": "", "relPath": f"images/{fname}", "fileName": fname}
            for idx, fname in enumerate(design_names, start=1)
        ],
        "summaryImages": summary_records,
        "summary": summary_payload,
        "instances": instances,
        "collectDate": int(datetime.now().timestamp()),
        "update_time": datetime.now().isoformat(),
        "generatedAt": Path().absolute().as_posix(),
        "note": "本文件包含结构化数据与打印配置详情。",
    }

    meta_path = model_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_offline_files_to_meta(model_dir)

    hero_file = cover_name or (design_names[0] if design_names else (summary_names_all[0] if summary_names_all else ""))
    hero_rel = f"./images/{hero_file}" if hero_file else "screenshot.png"
    assets = {
        "design_files": design_names,
        "hero": hero_rel,
        "avatar": None,
        "collected_date": datetime.now().strftime("%Y-%m-%d"),
        "instance_files": [],
        "base_name": base_name,
        "hide_stats": True,
        "hide_inst_stats": True,
    }
    index_html = build_index_html(meta, assets)
    (model_dir / "index.html").write_text(index_html, encoding="utf-8")

    # 手动导入成功后，清理对应草稿临时目录，避免 manual_drafts 持续堆积
    if draft_session_dir is not None and draft_session_dir.exists():
        try:
            shutil.rmtree(draft_session_dir, ignore_errors=True)
        except Exception as e:
            logger.warning("清理手动导入草稿目录失败: %s (%s)", draft_session_dir, e)

    logger.info("手动导入模型完成: %s", model_dir)
    return {"status": "ok", "base_name": base_name, "work_dir": str(model_dir.resolve())}


@app.post("/api/models/{model_dir}/delete")
async def api_delete_model(model_dir: str):
    target = resolve_model_dir(model_dir)
    try:
        shutil.rmtree(target)
    except Exception as e:
        logger.exception("删除目录失败")
        raise HTTPException(500, f"删除失败: {e}")

    save_gallery_flags(remove_model_dirs_from_gallery_flags(load_gallery_flags(), [model_dir]))
    return {"status": "ok"}


@app.post("/api/models/batch-delete")
async def api_batch_delete_models(body: dict):
    payload = body if isinstance(body, dict) else {}
    model_dirs_raw = payload.get("model_dirs") if isinstance(payload.get("model_dirs"), list) else []
    model_dirs = []
    for item in model_dirs_raw:
        value = str(item or "").strip()
        if value and value not in model_dirs:
            model_dirs.append(value)
    if not model_dirs:
        raise HTTPException(400, "model_dirs 不能为空")

    deleted = []
    failed = []
    for model_dir in model_dirs:
        try:
            target = resolve_model_dir(model_dir)
            shutil.rmtree(target)
            deleted.append(model_dir)
        except HTTPException as exc:
            failed.append({"model_dir": model_dir, "message": str(exc.detail)})
        except Exception as exc:
            logger.exception("批量删除目录失败: %s", model_dir)
            failed.append({"model_dir": model_dir, "message": str(exc)})

    if deleted:
        save_gallery_flags(remove_model_dirs_from_gallery_flags(load_gallery_flags(), deleted))

    return {
        "status": "ok",
        "deleted": deleted,
        "failed": failed,
    }


# ---------- v2: 模板渲染模型详情页（测试） ----------

@app.get("/api/models/{model_dir}/instances/{inst_id}/download")
async def api_model_instance_download(model_dir: str, inst_id: int):
    import urllib.parse

    target = resolve_model_dir(model_dir)
    meta_path = target / "meta.json"
    instances_dir = target / "instances"
    if not meta_path.exists():
        raise HTTPException(404, "meta.json 不存在")
    if not instances_dir.exists() or not instances_dir.is_dir():
        raise HTTPException(404, "instances 目录不存在")

    data = read_json_file(meta_path, {})
    instances = data.get("instances") if isinstance(data, dict) else None
    if not isinstance(instances, list):
        raise HTTPException(404, "未找到实例信息")

    target_inst = next((x for x in instances if isinstance(x, dict) and str(x.get("id")) == str(inst_id)), None)
    if not target_inst:
        raise HTTPException(404, "未找到对应实例")

    resolved_name = resolve_instance_filename(target_inst, instances_dir)
    if not resolved_name:
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    full_path = (instances_dir / resolved_name).resolve()
    if not str(full_path).startswith(str(instances_dir.resolve())) or not full_path.is_file():
        raise HTTPException(404, "找不到对应的打印配置或者模型文件")

    # 运行时自愈：回填 fileName，后续无需再次猜测
    if str(target_inst.get("fileName") or "").strip() != resolved_name:
        target_inst["fileName"] = resolved_name
        try:
            meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("回填实例 fileName 失败: %s / %s", model_dir, inst_id)

    encoded_filename = urllib.parse.quote(full_path.name)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    return FileResponse(full_path, headers=headers)

@app.get("/api/models/{model_dir}/file/{file_path:path}")
async def api_model_file_download(model_dir: str, file_path: str):
    """通用文件下载接口 — 解决 v2 页面中文路径编码问题"""
    import urllib.parse
    target = resolve_model_dir(model_dir)
    # 安全：防止路径遍历
    clean_rel = Path(file_path)
    if ".." in clean_rel.parts:
        raise HTTPException(400, "非法路径")
    full_path = (target / clean_rel).resolve()
    if not str(full_path).startswith(str(target.resolve())):
        raise HTTPException(400, "路径越界")
    if not full_path.is_file():
        raise HTTPException(404, "文件不存在")
    # 对于 3mf 等文件，加 Content-Disposition 触发下载
    headers = {}
    if full_path.suffix.lower() in {".3mf", ".stl", ".step", ".stp", ".zip", ".rar", ".7z"}:
        encoded_name = urllib.parse.quote(full_path.name)
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_name}"
    return FileResponse(full_path, headers=headers)


@app.get("/v2/files/{model_dir}")
async def v2_model_page(model_dir: str):
    """返回通用模型详情页模板，由前端 JS 动态加载 meta.json 渲染"""
    resolve_model_dir(model_dir)  # 校验目录合法性
    return FileResponse(BASE_DIR / "templates" / "model.html")


@app.get("/api/v2/models/{model_dir}/meta")
async def api_v2_model_meta(model_dir: str):
    """返回模型目录下的 meta.json"""
    target = resolve_model_dir(model_dir)
    meta_path = target / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "meta.json 不存在")
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(data.get("offlineFiles"), dict):
            data["offlineFiles"] = {
                "attachments": list_files_in_dir(target / "file", image_only=False),
                "printed": list_files_in_dir(target / "printed", image_only=True),
            }
        ensure_collect_date(data, int(meta_path.stat().st_mtime))
        if not data.get("update_time"):
            data["update_time"] = datetime.fromtimestamp(meta_path.stat().st_mtime).isoformat()
        data["source"] = normalize_model_source(data, model_dir)

        # 兼容历史归档：批量回填 instances[].fileName，减少前端/接口猜测成本
        instances_changed = False
        instances = data.get("instances")
        if isinstance(instances, list):
            instances_dir = target / "instances"
            for inst in instances:
                if not isinstance(inst, dict):
                    continue
                resolved = resolve_instance_filename(inst, instances_dir)
                if not resolved:
                    continue
                if str(inst.get("fileName") or "").strip() != resolved:
                    inst["fileName"] = resolved
                    instances_changed = True
        if instances_changed:
            try:
                meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                logger.warning("批量回填 instances.fileName 失败: %s", model_dir)

        return data
    except Exception as e:
        raise HTTPException(500, f"读取 meta.json 失败: {e}")


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
