import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from archiver import archive_model, download_file, fetch_instance_3mf, parse_cookies, sanitize_filename

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
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
            name3mf, dl_url = fetch_instance_3mf(session, inst_id_int, cookie, api_url)
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
            name3mf, dl_url = fetch_instance_3mf(session, inst_id, cookie, api_url)
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
                name3mf, dl_url = fetch_instance_3mf(session, inst_id_int, cookie, api_url)
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
        logger.info("使用 Cookie 片段: %s", cookie[:200])
        result = archive_model(url, cookie, Path(CFG["download_dir"]), Path(CFG["logs_dir"]), logger)
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


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
