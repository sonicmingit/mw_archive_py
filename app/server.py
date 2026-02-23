import json
import logging
import re
import shutil
import sys
from html import escape as escape_html
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from archiver import (
    STYLE_CSS,
    archive_model,
    build_index_html,
    download_file,
    fetch_instance_3mf,
    parse_cookies,
    sanitize_filename,
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
GALLERY_FLAGS_PATH = BASE_DIR / "gallery_flags.json"
TMP_DIR = BASE_DIR / "tmp"
DEFAULT_CONFIG = {
    "download_dir": "./data",
    "cookie_file": "./cookie.txt",
    "logs_dir": "./logs"
}

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


def resolve_model_dir(model_dir: str) -> Path:
    if not model_dir or "/" in model_dir or "\\" in model_dir:
        raise HTTPException(400, "model_dir 无效")
    if not (model_dir.startswith("MW_") or model_dir.startswith("Others_")):
        raise HTTPException(400, "仅允许 MW_* 或 Others_* 目录")
    root = Path(CFG["download_dir"]).resolve()
    target = (root / model_dir).resolve()
    if not str(target).startswith(str(root)):
        raise HTTPException(400, "路径越界")
    if not target.exists() or not target.is_dir():
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


def pick_ext(filename: str, fallback: str) -> str:
    suffix = Path(filename).suffix if filename else ""
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    return suffix if suffix else fallback


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
                    log_obj.info("目标已存在，跳过移动: %s", target)
                    continue
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


def make_summary_payload(text: str, summary_files: List[str]) -> dict:
    clean_text = (text or "").strip()
    parts = []
    if clean_text:
        safe_text = escape_html(clean_text).replace("\n", "<br>")
        parts.append(f"<p>{safe_text}</p>")
    for idx, name in enumerate(summary_files, start=1):
        parts.append(f'<img src="./images/{name}" alt="summary {idx}">')
    html = "\n".join(parts)
    summary_text = " ".join(clean_text.split())
    return {"raw": html, "html": html, "text": summary_text}


def build_others_dir(title: str) -> tuple[str, Path]:
    safe_title = sanitize_filename(title).strip() or "model"
    date_stamp = datetime.now().strftime("%Y%m%d")
    base_name = f"Others_{safe_title}_{date_stamp}"
    root = Path(CFG["download_dir"]).resolve()
    candidate = root / base_name
    if not candidate.exists():
        return base_name, candidate
    idx = 1
    while True:
        name = f"{base_name}_{idx}"
        candidate = root / name
        if not candidate.exists():
            return name, candidate
        idx += 1


# ---------- 配置与持久化 ----------
def load_config():
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        cfg = DEFAULT_CONFIG
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    # 规范化为绝对路径
    cfg["download_dir"] = str((BASE_DIR / cfg.get("download_dir", "data")).resolve())
    cfg["cookie_file"] = str((BASE_DIR / cfg.get("cookie_file", "cookie.txt")).resolve())
    cfg["logs_dir"] = str((BASE_DIR / cfg.get("logs_dir", "logs")).resolve())
    Path(cfg["download_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["logs_dir"]).mkdir(parents=True, exist_ok=True)
    return cfg


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
    base = sanitize_filename(inst.get("title") or inst.get("name") or str(inst.get("id") or "model"))
    if not base:
        base = str(inst.get("id") or "model")
    ext = Path(name_hint).suffix if name_hint else ""
    if not ext:
        ext = ".3mf"
    elif not ext.startswith("."):
        ext = "." + ext
    return f"{base}{ext}"


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
        file_name = pick_instance_filename(target, name3mf)
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
        file_name = pick_instance_filename(target, name3mf or target.get("name") or "")
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

            file_name = pick_instance_filename(inst, name3mf or inst.get("name") or "")
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
    for d in root.glob("MW_*"):
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
            collected_at = datetime.fromtimestamp(meta.stat().st_mtime).isoformat()
            items.append({
                "baseName": data.get("baseName") or d.name,
                "title": data.get("title"),
                "id": data.get("id"),
                "cover": cover_file,
                "dir": d.name,
                "source": "makerworld",
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
    for d in root.glob("Others_*"):
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
            author = data.get("author") or {}
            collected_at = datetime.fromtimestamp(meta.stat().st_mtime).isoformat()
            items.append({
                "baseName": data.get("baseName") or d.name,
                "title": data.get("title"),
                "id": data.get("id"),
                "cover": cover_file,
                "dir": d.name,
                "source": "others",
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


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/files", StaticFiles(directory=CFG["download_dir"], html=True), name="files")


@app.get("/")
async def gallery_page():
    return FileResponse(BASE_DIR / "templates" / "gallery.html")


@app.get("/config")
async def config_page():
    return FileResponse(BASE_DIR / "templates" / "config.html")


@app.get("/api/config")
async def api_config():
    cfg = load_config()
    cookie_path = Path(cfg["cookie_file"])
    cookie_time = cookie_path.stat().st_mtime if cookie_path.exists() else None
    return {
        "download_dir": cfg["download_dir"],
        "logs_dir": cfg["logs_dir"],
        "cookie_file": cfg["cookie_file"],
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
        result = archive_model(url, cookie, TMP_DIR, Path(CFG["logs_dir"]), logger)
        tmp_work_dir = Path(result.get("work_dir") or "")
        final_dir = finalize_tmp_archive(tmp_work_dir, Path(CFG["download_dir"]), logger)
        result["work_dir"] = str(final_dir.resolve())
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
    if not attach_dir.exists():
        return {"files": []}
    files = sorted([p.name for p in attach_dir.iterdir() if p.is_file()])
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
    return {"status": "ok", "file": dest.name}


@app.get("/api/models/{model_dir}/printed")
async def api_list_printed(model_dir: str):
    target = resolve_model_dir(model_dir)
    printed_dir = target / "printed"
    if not printed_dir.exists():
        return {"files": []}
    files = sorted([p.name for p in printed_dir.iterdir() if p.is_file()])
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
    return {"status": "ok", "file": dest.name}


@app.post("/api/models/manual")
async def api_manual_import(
    title: str = Form(...),
    modelLink: str = Form(""),
    sourceLink: str = Form(""),
    summary: str = Form(""),
    tags: str = Form(""),
    cover: Optional[UploadFile] = File(None),
    design_images: List[UploadFile] = File([]),
    instance_files: List[UploadFile] = File([]),
    instance_pictures: List[UploadFile] = File([]),
    attachments: List[UploadFile] = File([]),
    instance_descs: str = Form(""),
    instance_picture_counts: str = Form(""),
):
    name = (title or "").strip()
    if not name:
        raise HTTPException(400, "模型名称不能为空")

    base_name, model_dir = build_others_dir(name)
    images_dir = model_dir / "images"
    instances_dir = model_dir / "instances"
    files_dir = model_dir / "file"
    images_dir.mkdir(parents=True, exist_ok=True)
    instances_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    design_names: List[str] = []
    summary_names: List[str] = []
    cover_name = ""

    if cover and cover.filename:
        ext = pick_ext(cover.filename, ".jpg")
        cover_name = f"cover{ext}"
        save_upload_file(cover, images_dir / cover_name)

    for idx, upload in enumerate(design_images, start=1):
        if not upload or not upload.filename:
            continue
        ext = pick_ext(upload.filename, ".jpg")
        fname = f"design_{idx:02d}{ext}"
        save_upload_file(upload, images_dir / fname)
        design_names.append(fname)

    if not cover_name and design_names:
        cover_name = design_names[0]
    if not cover_name and summary_names:
        cover_name = summary_names[0]
    if cover_name and not design_names:
        design_names = [cover_name]

    desc_list = parse_instance_descs(instance_descs)
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
    for idx, upload in enumerate(instance_files, start=1):
        if not upload or not upload.filename:
            continue
        safe_name = sanitize_filename(Path(upload.filename).name)
        if not safe_name:
            safe_name = f"instance_{idx}.3mf"
        stem = Path(safe_name).stem or f"instance_{idx}"
        suffix = pick_ext(safe_name, ".3mf")
        dest = ensure_unique_path(instances_dir / f"{stem}{suffix}")
        save_upload_file(upload, dest)
        inst_title = dest.stem
        inst_summary = desc_list[idx - 1] if (idx - 1) < len(desc_list) else ""
        pics = []
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
                "index": pic_idx,
                "url": "",
                "relPath": f"images/{fname}",
                "fileName": fname,
                "isRealLifePhoto": 0,
            })
        instances.append({
            "id": idx,
            "title": inst_title,
            "summary": inst_summary,
            "name": dest.name,
            "downloadCount": 0,
            "printCount": 0,
            "plates": [],
            "pictures": pics,
            "instanceFilaments": [],
        })

    for upload in attachments:
        if not upload or not upload.filename:
            continue
        safe_name = sanitize_filename(Path(upload.filename).name) or "attachment"
        dest = ensure_unique_path(files_dir / safe_name)
        save_upload_file(upload, dest)

    tag_list = [t for t in re.split(r"\s+", (tags or "").strip()) if t]
    summary_payload = make_summary_payload(summary, summary_names)
    author_url = (sourceLink or modelLink or "").strip()
    meta = {
        "baseName": base_name,
        "source": "others",
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
            "name": "手动导入",
            "url": author_url,
            "avatarUrl": "",
            "avatarLocal": "",
            "avatarRelPath": "",
        },
        "images": {
            "cover": cover_name,
            "design": design_names,
            "summary": summary_names,
        },
        "designImages": [
            {"index": idx, "originalUrl": "", "relPath": f"images/{fname}", "fileName": fname}
            for idx, fname in enumerate(design_names, start=1)
        ],
        "summaryImages": [
            {"index": idx, "originalUrl": "", "relPath": f"images/{fname}", "fileName": fname}
            for idx, fname in enumerate(summary_names, start=1)
        ],
        "summary": summary_payload,
        "instances": instances,
        "generatedAt": Path().absolute().as_posix(),
        "note": "本文件包含结构化数据与打印配置详情。",
    }

    meta_path = model_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    hero_file = cover_name or (design_names[0] if design_names else (summary_names[0] if summary_names else ""))
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
    (model_dir / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    index_html = build_index_html(meta, assets)
    (model_dir / "index.html").write_text(index_html, encoding="utf-8")

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


if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
