import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Tuple

from archiver import sanitize_filename


MANUAL_COUNTER_FILE = "_manual_import_counter.json"
MANUAL_COUNTER_LOCK = threading.Lock()


def manual_counter_path(download_dir: str | Path) -> Path:
    root = Path(download_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / MANUAL_COUNTER_FILE


def read_manual_counter(download_dir: str | Path) -> int:
    path = manual_counter_path(download_dir)
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


def write_manual_counter(download_dir: str | Path, counter: int):
    path = manual_counter_path(download_dir)
    payload = {
        "counter": max(int(counter), 0),
        "updated_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_manual_counter_file(download_dir: str | Path):
    path = manual_counter_path(download_dir)
    if path.exists():
        return
    write_manual_counter(download_dir, 0)


def build_local_model_dir(download_dir: str | Path, title: str) -> Tuple[str, Path]:
    root = Path(download_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    safe_title = sanitize_filename(title).strip() or "model"
    with MANUAL_COUNTER_LOCK:
        counter = read_manual_counter(root)
        while True:
            counter += 1
            base_name = f"LocalModel_{counter:06d}_{safe_title}"
            candidate = root / base_name
            if candidate.exists():
                continue
            write_manual_counter(root, counter)
            return base_name, candidate
