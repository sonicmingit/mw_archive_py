import json
import logging
import re
import shutil
import sys
import threading
import uuid
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

BASE_DIR = Path(__file__).resolve().parent
VERSION_FILE_CANDIDATES = [
    BASE_DIR / "version.yml",
]
CONFIG_PATH = BASE_DIR / "config.json"
GALLERY_FLAGS_PATH = BASE_DIR / "gallery_flags.json"
TMP_DIR = BASE_DIR / "tmp"
MANUAL_DRAFT_ROOT = TMP_DIR / "manual_drafts"
DEFAULT_CONFIG = {
    "download_dir": "./data",
    "cookie_file": "./cookie.txt",
    "logs_dir": "./logs",
}
MANUAL_COUNTER_LOCK = threading.Lock()
MANUAL_COUNTER_FILE = "_manual_import_counter.json"


def load_project_version() -> str:
    """读取 app/version.yml 中的 project_version。"""
    for version_file in VERSION_FILE_CANDIDATES:
        if not version_file.exists():
            continue
        try:
            for raw in version_file.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                key, value = line.split(":", 1)
                if key.strip() == "project_version":
                    ver = value.strip().strip("'\"")
                    if ver:
                        return ver
        except Exception:
            continue
    return "0.0.0"


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
# 文件
fh = logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8")
fh.setFormatter(fmt)
logger.addHandler(fh)
# 控制台
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(fmt)
logger.addHandler(sh)

_TAG_RE = re.compile(r"<[^>]+>")

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
    root = Path(cfg_now["download_dir"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / MANUAL_COUNTER_FILE


def read_manual_counter(cfg: Optional[dict] = None) -> int:
    path = manual_counter_path(cfg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    try:
        if isinstance(data, dict):
            value = int(data.get("counter") or 0)
        else:
            value = int(data or 0)
    except Exception:
        return 0
    return max(value, 0)


def write_manual_counter(counter: int, cfg: Optional[dict] = None):
    path = manual_counter_path(cfg)
    payload = {
        "counter": max(int(counter), 0),
        "updated_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_manual_counter_file(cfg: Optional[dict] = None):
    path = manual_counter_path(cfg)
    if path.exists():
        return
    write_manual_counter(0, cfg)


def build_local_model_dir(title: str) -> tuple[str, Path]:
    safe_title = sanitize_filename(title).strip() or "model"
    with MANUAL_COUNTER_LOCK:
        cfg_now = load_config()
        root = Path(cfg_now["download_dir"]).resolve()
        counter = read_manual_counter(cfg_now)

        while True:
            counter += 1
            base_name = f"LocalModel_{counter:06d}_{safe_title}"
            candidate = root / base_name
            if candidate.exists():
                continue
            write_manual_counter(counter, cfg_now)
            try:
                CFG.update(cfg_now)
            except Exception:
                pass
            return base_name, candidate


# ---------- 配置与持久化 ----------
def load_config():
    changed = False
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        cfg = dict(DEFAULT_CONFIG)
        changed = True
    if not isinstance(cfg, dict):
        cfg = dict(DEFAULT_CONFIG)
        changed = True
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
            changed = True

    # 仅移除已废弃字段，不因相对/绝对路径规范化而回写 config.json
    if "manual_local_model_counter" in cfg:
        del cfg["manual_local_model_counter"]
        changed = True

    # 运行时使用绝对路径，配置文件本身保留用户填写的相对路径
    runtime_cfg = dict(cfg)
    runtime_cfg["download_dir"] = str((BASE_DIR / cfg.get("download_dir", "data")).resolve())
    runtime_cfg["cookie_file"] = str((BASE_DIR / cfg.get("cookie_file", "cookie.txt")).resolve())
    runtime_cfg["logs_dir"] = str((BASE_DIR / cfg.get("logs_dir", "logs")).resolve())

    Path(runtime_cfg["download_dir"]).mkdir(parents=True, exist_ok=True)
    Path(runtime_cfg["logs_dir"]).mkdir(parents=True, exist_ok=True)
    if changed:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return runtime_cfg


def load_gallery_flags() -> dict:
    if GALLERY_FLAGS_PATH.exists():
        try:
            data = json.loads(GALLERY_FLAGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    favorites = data.get("favorites") if isinstance(data.get("favorites"), list) else []
    printed = data.get("printed") if isinstance(data.get("printed"), list) else []
    return {"favorites": favorites, "printed": printed}


def save_gallery_flags(flags: dict):
    data = {
        "favorites": list(dict.fromkeys(flags.get("favorites") or [])),
        "printed": list(dict.fromkeys(flags.get("printed") or [])),
    }
    GALLERY_FLAGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_cookie(cfg) -> str:
    cookie_path = Path(cfg["cookie_file"])
    if cookie_path.exists():
        return cookie_path.read_text(encoding="utf-8").strip()
    return ""


def write_cookie(cfg, cookie: str):
    cookie_path = Path(cfg["cookie_file"])
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(cookie.strip(), encoding="utf-8")
    logger.info("Cookie 更新")
    # 额外记录更新时间
    with (Path(cfg["logs_dir"]) / "cookie.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()}\tupdate\n")


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


def retry_missing_downloads(cfg, cookie: str):
    missing_log = Path(cfg["logs_dir"]) / "missing_3mf.log"
    if not missing_log.exists():
        return {"processed": 0, "success": 0, "failed": 0, "details": []}

    lines = [line for line in missing_log.read_text(encoding="utf-8").splitlines() if line.strip()]

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (MW-Redownload)"})
    session.cookies.update(parse_cookies(cookie))

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

        api_url = target.get("apiUrl") or f"https://makerworld.com.cn/api/v1/design-service/instance/{inst_id_str}/f3mf?type=download&fileType="
        try:
            inst_id_int = int(inst_id_str)
        except Exception:
            inst_id_int = inst_id_str

        try:
            name3mf, dl_url, used_api_url = fetch_instance_3mf(session, inst_id_int, cookie, api_url)
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
        try:
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
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


def redownload_instance_by_id(cfg, cookie: str, inst_id: int):
    """
    按实例 ID 扫描已下载模型，重新获取下载地址并覆盖保存到 instances 目录。
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (MW-Redownload-One)"})
    session.cookies.update(parse_cookies(cookie))

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
        api_url = target.get("apiUrl") or f"https://makerworld.com.cn/api/v1/design-service/instance/{inst_id}/f3mf?type=download&fileType="
        try:
            name3mf, dl_url, used_api_url = fetch_instance_3mf(session, inst_id, cookie, api_url)
        except Exception as e:
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
            download_file(session, dl_url, dest)
        except Exception as e:
            details.append({"status": "fail", "base_name": meta.get("baseName"), "inst_id": inst_id, "message": f"下载失败: {e}"})
            continue

        target["downloadUrl"] = dl_url
        if used_api_url:
            target["apiUrl"] = used_api_url
        if name3mf:
            target["name"] = name3mf
        target["fileName"] = file_name
        try:
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
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


def redownload_model_by_id(cfg, cookie: str, model_id: int):
    """
    按模型 ID (目录名 MW_{id}_*) 扫描，针对其中所有 instances 的 apiUrl 重新下载并更新 meta。
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (MW-Redownload-Model)"})
    session.cookies.update(parse_cookies(cookie))

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
            api_url = inst.get("apiUrl") or f"https://makerworld.com.cn/api/v1/design-service/instance/{inst_id}/f3mf?type=download&fileType="
            try:
                inst_id_int = int(inst_id) if inst_id is not None else inst_id
            except Exception:
                inst_id_int = inst_id
            try:
                name3mf, dl_url, used_api_url = fetch_instance_3mf(session, inst_id_int, cookie, api_url)
            except Exception as e:
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
                download_file(session, dl_url, dest)
            except Exception as e:
                details.append({"status": "fail", "base_name": meta.get("baseName"), "inst_id": inst_id, "message": f"下载失败: {e}"})
                continue

            inst["downloadUrl"] = dl_url
            if used_api_url:
                inst["apiUrl"] = used_api_url
            if name3mf:
                inst["name"] = name3mf
            inst["fileName"] = file_name
            success += 1
            details.append({"status": "ok", "base_name": meta.get("baseName"), "inst_id": inst_id, "file": dest.name, "downloadUrl": dl_url})

            # 清理缺失记录中对应实例
            if missing_lines:
                missing_lines = [
                    ln for ln in missing_lines
                    if not (len(ln.split("\t")) >= 3 and ln.split("\t")[2] == str(inst_id))
                ]

        try:
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
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
            raw_source = str(data.get("source") or "").strip().lower()
            if d.name.startswith("MW_"):
                source_value = "makerworld"
            elif raw_source in {"localmodel", "others"} or d.name.startswith("LocalModel_") or d.name.startswith("Others_"):
                source_value = "localmodel"
            else:
                source_value = "localmodel"
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
ensure_manual_counter_file(CFG)

TMP_DIR.mkdir(parents=True, exist_ok=True)
MANUAL_DRAFT_ROOT.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/files", StaticFiles(directory=CFG["download_dir"], html=True), name="files")
app.mount("/tmp", StaticFiles(directory=TMP_DIR), name="tmp")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


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
        },
    )


@app.get("/api/config")
async def api_config():
    cfg = load_config()
    cookie_path = Path(cfg["cookie_file"])
    cookie_time = cookie_path.stat().st_mtime if cookie_path.exists() else None
    return {
        "download_dir": cfg["download_dir"],
        "logs_dir": cfg["logs_dir"],
        "cookie_file": cfg["cookie_file"],
        "manual_local_model_counter": read_manual_counter(cfg),
        "cookie_updated_at": datetime.fromtimestamp(cookie_time).isoformat() if cookie_time else None,
    }


@app.post("/api/cookie")
async def api_cookie(body: dict):
    cookie = (body or {}).get("cookie", "")
    if not cookie.strip():
        raise HTTPException(400, "cookie 不能为空")
    write_cookie(CFG, cookie)
    return {"status": "ok", "updated_at": datetime.now().isoformat()}


@app.post("/api/archive")
async def api_archive(body: dict):
    url = (body or {}).get("url", "").strip()
    if not url:
        raise HTTPException(400, "url 不能为空")
    cookie = read_cookie(CFG)
    if not cookie:
        raise HTTPException(400, "请先设置 cookie")
    try:
        reset_tmp_dir(TMP_DIR)
        logger.info("使用 Cookie 片段: %s", cookie[:200])
        result = archive_model(
            url,
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
        return {"status": "ok", **result}
    except requests.HTTPError as e:
        # 输出更多上下文（状态码与前 300 字符）
        resp = e.response
        snippet = ""
        if resp is not None:
            snippet = (resp.text or "")[:300]
            logger.error("归档失败 HTTP %s: %s", resp.status_code, snippet)
        else:
            logger.error("归档失败 HTTP: %s", e)
        raise HTTPException(500, f"归档失败: {e} 片段: {snippet}")
    except Exception as e:
        logger.exception("归档失败")
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
    cookie = read_cookie(CFG)
    if not cookie:
        raise HTTPException(400, "请先设置 cookie")
    try:
        result = retry_missing_downloads(CFG, cookie)
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
    cookie = read_cookie(CFG)
    if not cookie:
        raise HTTPException(400, "请先设置 cookie")
    try:
        result = redownload_instance_by_id(CFG, cookie, inst_id)
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
    cookie = read_cookie(CFG)
    if not cookie:
        raise HTTPException(400, "请先设置 cookie")
    try:
        result = redownload_model_by_id(CFG, cookie, model_id)
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
    favorites = body.get("favorites") if isinstance(body, dict) else []
    printed = body.get("printed") if isinstance(body, dict) else []
    favorites_list = [str(x) for x in favorites] if isinstance(favorites, list) else []
    printed_list = [str(x) for x in printed] if isinstance(printed, list) else []
    save_gallery_flags({"favorites": favorites_list, "printed": printed_list})
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

    flags = load_gallery_flags()
    flags["favorites"] = [x for x in flags.get("favorites", []) if x != model_dir]
    flags["printed"] = [x for x in flags.get("printed", []) if x != model_dir]
    save_gallery_flags(flags)
    return {"status": "ok"}


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
