from typing import Dict, Optional


class NotificationDispatcher:
    def __init__(self, logger):
        self._logger = logger
        self._channels: Dict[str, object] = {}

    def register(self, name: str, service: object):
        key = str(name or "").strip().lower()
        if not key or service is None:
            return
        self._channels[key] = service

    def notify_success(self, payload: Dict):
        for name, service in self._channels.items():
            try:
                notify = getattr(service, "notify_success", None)
                if callable(notify):
                    notify(payload or {})
            except Exception as e:
                self._logger.warning("通知渠道 %s 发送成功消息失败: %s", name, e)

    def notify_alert(self, alert, detail: Optional[str] = None):
        for name, service in self._channels.items():
            try:
                notify = getattr(service, "notify_alert", None)
                if callable(notify):
                    notify(alert, detail)
            except Exception as e:
                self._logger.warning("通知渠道 %s 发送告警失败: %s", name, e)

    def send_test_connection(self) -> Dict:
        results = {}
        success_count = 0
        for name, service in self._channels.items():
            try:
                fn = getattr(service, "send_test_connection", None)
                if not callable(fn):
                    continue
                result = fn() or {}
                results[name] = result
                if result.get("status") == "ok":
                    success_count += 1
            except Exception as e:
                results[name] = {"status": "error", "message": str(e)}
        if not results:
            return {"status": "error", "message": "未配置可用的通知渠道", "channels": {}}
        return {
            "status": "ok" if success_count > 0 else "error",
            "success_count": success_count,
            "total_channels": len(results),
            "channels": results,
        }

    def start(self):
        for name, service in self._channels.items():
            try:
                should_run = getattr(service, "should_run", None)
                start = getattr(service, "start", None)
                stop = getattr(service, "stop", None)
                if callable(should_run) and callable(start):
                    if should_run():
                        start()
                    elif callable(stop):
                        stop()
            except Exception as e:
                self._logger.warning("通知渠道 %s 启动失败: %s", name, e)

    def stop(self):
        for name, service in self._channels.items():
            try:
                stop = getattr(service, "stop", None)
                if callable(stop):
                    stop()
            except Exception as e:
                self._logger.warning("通知渠道 %s 停止失败: %s", name, e)
