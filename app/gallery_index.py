import json
import threading
from functools import wraps
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
GALLERY_INDEX_PATH = CONFIG_DIR / "gallery_index.json"
MODEL_DIR_PREFIXES = ("MW_", "Others_", "LocalModel_")

_TAG_RE = __import__("re").compile(r"<[^>]+>")
_INDEX_LOCK = threading.RLock()


def index_transaction(fn):
    @wraps(fn)
    def locked(*args, **kwargs):
        with _INDEX_LOCK:
            return fn(*args, **kwargs)
    return locked

_CACHE = {
    "mtime_ns": None,
    "payload": None,
}


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


def infer_model_platform(meta: dict, inst: Optional[dict] = None) -> str:
    value_pool = [
        meta.get("platform"),
        meta.get("region"),
        meta.get("source"),
        meta.get("url"),
        meta.get("modelLink"),
        meta.get("sourceLink"),
    ]
    if isinstance(inst, dict):
        value_pool.extend([inst.get("apiUrl"), inst.get("downloadUrl")])
    for value in value_pool:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if "makerworld.com.cn" in text or "mw_cn" in text or text == "cn":
            return "cn"
        if "makerworld.com" in text or "mw_global" in text or text == "global":
            return "global"
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


def now_iso() -> str:
    return datetime.now().isoformat()


def is_model_dir(path: Path) -> bool:
    return path.is_dir() and path.name.startswith(MODEL_DIR_PREFIXES)


def build_gallery_entry(model_dir: Path) -> Optional[dict]:
    meta_path = model_dir / "meta.json"
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    images = data.get("images") if isinstance(data.get("images"), dict) else {}
    cover_name = str(images.get("cover") or "").strip()
    cover_file = (model_dir / "images" / cover_name).name if cover_name else ""
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    raw_summary = summary_data.get("text") or summary_data.get("raw") or summary_data.get("html") or ""
    instances = data.get("instances") if isinstance(data.get("instances"), list) else []
    published_at = None
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        ts = inst.get("publishTime")
        if ts and (published_at is None or ts < published_at):
            published_at = ts
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    meta_stat = meta_path.stat()
    return {
        "baseName": data.get("baseName") or model_dir.name,
        "title": data.get("title"),
        "id": data.get("id"),
        "cover": cover_file,
        "dir": model_dir.name,
        "source": normalize_model_source(data, model_dir.name),
        "tags": data.get("tags") if isinstance(data.get("tags"), list) else [],
        "summary": strip_html(str(raw_summary or "")),
        "author": {
            "name": author.get("name"),
            "url": author.get("url"),
            "avatarRelPath": author.get("avatarRelPath"),
        },
        "stats": data.get("stats") if isinstance(data.get("stats"), dict) else {},
        "instanceCount": len(instances),
        "publishedAt": published_at,
        "collectedAt": resolve_collect_iso(data, meta_path),
        "meta_mtime": meta_stat.st_mtime,
        "meta_mtime_ns": meta_stat.st_mtime_ns,
        "indexedAt": now_iso(),
    }


def build_gallery_index_payload(root: str | Path) -> dict:
    root_path = Path(root).resolve()
    items = []
    if root_path.exists():
        for item in root_path.iterdir():
            if not is_model_dir(item):
                continue
            if item.name.startswith(".") or item.name.startswith("_"):
                continue
            entry = build_gallery_entry(item)
            if entry:
                items.append(entry)
    items.sort(key=lambda x: str(x.get("dir") or "").lower())
    return {
        "_meta": {
            "version": 1,
            "generatedAt": now_iso(),
            "itemCount": len(items),
            "root": str(root_path),
            "fullRebuildAt": now_iso(),
        },
        "items": items,
    }


def _write_payload(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    stat = path.stat()
    _CACHE.update(path=path, mtime_ns=stat.st_mtime_ns, payload=payload)


@index_transaction
def load_gallery_index_payload(index_path: Optional[Path] = None) -> Optional[dict]:
    path = index_path or GALLERY_INDEX_PATH
    if not path.exists():
        return None
    stat = path.stat()
    cached = _CACHE.get("payload")
    if cached is not None and _CACHE.get("path") == path and _CACHE.get("mtime_ns") == stat.st_mtime_ns:
        return cached
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return None
    _CACHE.update(path=path, mtime_ns=stat.st_mtime_ns, payload=payload)
    return payload


@index_transaction
def get_gallery_items(root: str | Path, index_path: Optional[Path] = None) -> List[dict]:
    path = index_path or GALLERY_INDEX_PATH
    payload = load_gallery_index_payload(path)
    if payload is None:
        payload = rebuild_gallery_index(root, index_path=path)
    return payload.get("items") if isinstance(payload.get("items"), list) else []


@index_transaction
def rebuild_gallery_index(root: str | Path, index_path: Optional[Path] = None) -> dict:
    path = index_path or GALLERY_INDEX_PATH
    payload = build_gallery_index_payload(root)
    _write_payload(path, payload)
    return payload


@index_transaction
def upsert_gallery_index_entry(root: str | Path, model_dir: str | Path, index_path: Optional[Path] = None) -> Optional[dict]:
    path = index_path or GALLERY_INDEX_PATH
    model_path = Path(model_dir)
    if not model_path.is_absolute():
        model_path = Path(root).resolve() / model_path
    entry = build_gallery_entry(model_path.resolve())
    payload = load_gallery_index_payload(path)
    if payload is not None:
        payload = dict(payload)
    if payload is None:
        payload = build_gallery_index_payload(root)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    filtered = [item for item in items if str(item.get("dir") or "") != model_path.name]
    if entry:
        filtered.append(entry)
    filtered.sort(key=lambda x: str(x.get("dir") or "").lower())
    payload["items"] = filtered
    payload["_meta"] = {
        "version": 1,
        "generatedAt": now_iso(),
        "itemCount": len(filtered),
        "root": str(Path(root).resolve()),
        "fullRebuildAt": ((payload.get("_meta") or {}).get("fullRebuildAt") or ""),
    }
    _write_payload(path, payload)
    return entry


@index_transaction
def remove_gallery_index_entries(root: str | Path, model_dirs: List[str], index_path: Optional[Path] = None) -> dict:
    path = index_path or GALLERY_INDEX_PATH
    cleaned = []
    for item in model_dirs or []:
        value = str(item or "").strip()
        if value and value not in cleaned:
            cleaned.append(value)
    payload = load_gallery_index_payload(path)
    if payload is not None:
        payload = dict(payload)
    if payload is None:
        payload = build_gallery_index_payload(root)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    remained = [item for item in items if str(item.get("dir") or "") not in cleaned]
    removed_count = len(items) - len(remained)
    payload["items"] = remained
    payload["_meta"] = {
        "version": 1,
        "generatedAt": now_iso(),
        "itemCount": len(remained),
        "root": str(Path(root).resolve()),
        "fullRebuildAt": ((payload.get("_meta") or {}).get("fullRebuildAt") or ""),
    }
    _write_payload(path, payload)
    return {"removed": removed_count, "items": remained}

