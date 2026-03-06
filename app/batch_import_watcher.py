import threading
from typing import Callable, Dict, Optional


class LocalBatchImportWatcher:
    def __init__(
        self,
        cfg_getter: Callable[[], Dict],
        runner: Callable[[Dict], Dict],
        logger,
        on_report: Optional[Callable[[Dict], None]] = None,
    ):
        self._cfg_getter = cfg_getter
        self._runner = runner
        self._logger = logger
        self._on_report = on_report
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def should_run(self) -> bool:
        cfg = self._cfg_getter() or {}
        local_cfg = cfg.get("local_batch_import") if isinstance(cfg.get("local_batch_import"), dict) else {}
        if not local_cfg.get("enabled"):
            return False
        return bool(local_cfg.get("watch_dirs"))

    def start(self):
        if not self.should_run():
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="local-batch-import-watcher", daemon=True)
        self._thread.start()
        self._logger.info("本地批量导入 watcher 已启动")
        return True

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=2)
            self._logger.info("本地批量导入 watcher 已停止")

    def _loop(self):
        while not self._stop_event.is_set():
            cfg = self._cfg_getter() or {}
            local_cfg = cfg.get("local_batch_import") if isinstance(cfg.get("local_batch_import"), dict) else {}
            interval = max(int(local_cfg.get("scan_interval_seconds") or 300), 30)
            try:
                report = self._runner(cfg) or {}
                if callable(self._on_report):
                    self._on_report(report)
            except Exception as e:
                self._logger.warning("本地批量导入 watcher 执行失败: %s", e)
            if self._stop_event.wait(interval):
                break
