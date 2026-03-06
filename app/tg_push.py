import re
import threading
import time
from typing import Callable, Dict, Optional

import requests


# 兼容两种域名，统一提取可归档的模型链接
MODEL_URL_RE = re.compile(
    r"(https?://(?:www\.)?makerworld\.com(?:\.cn)?/zh/models/[^\s#]+)",
    re.IGNORECASE,
)


def extract_makerworld_model_url(text: str) -> str:
    raw = str(text or "")
    m = MODEL_URL_RE.search(raw)
    if not m:
        return ""
    return m.group(1).strip()


def _split_ids(raw: str) -> set[str]:
    text = str(raw or "").strip()
    if not text:
        return set()
    parts = re.split(r"[\s,;|]+", text)
    return {p.strip() for p in parts if p.strip()}


class TelegramPushService:
    """
    Telegram 推送与命令服务（可选启用）：
    - 推送：归档成功/失败/告警
    - 命令：/cookies、/count、发送模型链接触发归档
    """

    def __init__(
        self,
        cfg_getter: Callable[[], Dict],
        logger,
        on_archive_url: Callable[[str], Dict],
        on_cookie_status: Callable[[], str],
        on_count: Callable[[], str],
        on_search: Callable[[str], str],
        on_get_base_url: Callable[[], str],
        on_set_base_url: Callable[[str], str],
    ):
        self._cfg_getter = cfg_getter
        self._logger = logger
        self._on_archive_url = on_archive_url
        self._on_cookie_status = on_cookie_status
        self._on_count = on_count
        self._on_search = on_search
        self._on_get_base_url = on_get_base_url
        self._on_set_base_url = on_set_base_url
        self._offset = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._commands_token = ""

    def should_run(self) -> bool:
        cfg = self._cfg_getter()
        if not cfg.get("enable_push"):
            return False
        token = str(cfg.get("bot_token") or "").strip()
        return bool(token)

    def start(self):
        if not self.should_run():
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="tg-poll", daemon=True)
        self._thread.start()
        self._logger.info("Telegram 命令轮询线程已启动")
        return True

    def set_archive_handler(self, handler: Callable[[str], Dict]):
        self._on_archive_url = handler

    def stop(self):
        was_alive = bool(self._thread and self._thread.is_alive())
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        if was_alive:
            self._logger.info("Telegram 命令轮询线程已停止")

    def notify_success(self, payload: Dict):
        cfg = self._cfg_getter()
        if not cfg.get("enable_push"):
            return
        token = str(cfg.get("bot_token") or "").strip()
        chat_ids = self._target_chat_ids(cfg)
        if not token or not chat_ids:
            return

        text = self._format_success_text(payload)
        photo = str(payload.get("cover_url") or "").strip()
        for chat_id in chat_ids:
            if photo and photo.lower().startswith(("http://", "https://")):
                ok = self._send_photo(token, chat_id, photo, text)
                if ok:
                    continue
            self._send_message(token, chat_id, text)

    def _format_alert_text(self, alert, detail: Optional[str] = None) -> str:
        if isinstance(alert, dict):
            icon = str(alert.get("icon") or "⚠️").strip() or "⚠️"
            title = str(alert.get("title") or "通知").strip()
            summary = str(alert.get("summary") or "").strip()
            lines = alert.get("lines") if isinstance(alert.get("lines"), list) else []
            text_lines = [f"{icon} {title}"]
            if summary:
                text_lines.append(summary)
            for line in lines:
                item = str(line or "").strip()
                if item:
                    text_lines.append(item)
            return "\n".join(text_lines)
        title = str(alert or "通知").strip()
        body = str(detail or "").strip()
        return f"⚠️ {title}\n{body}".strip()

    def notify_alert(self, alert, detail: Optional[str] = None):
        cfg = self._cfg_getter()
        if not cfg.get("enable_push"):
            return
        token = str(cfg.get("bot_token") or "").strip()
        chat_ids = self._target_chat_ids(cfg)
        if not token or not chat_ids:
            return
        text = self._format_alert_text(alert, detail)
        for chat_id in chat_ids:
            self._send_message(token, chat_id, text)

    def send_test_connection(self) -> Dict:
        cfg = self._cfg_getter()
        token = str(cfg.get("bot_token") or "").strip()
        chat_ids = self._target_chat_ids(cfg)
        if not token:
            return {"status": "error", "message": "Bot Token 未配置"}
        if not chat_ids:
            return {"status": "error", "message": "默认 Chat ID 未配置"}

        text = "✅ Telegram 连接测试成功\n已收到来自 本地模型库控制台 的测试消息。"
        success = 0
        failed = []
        for chat_id in chat_ids:
            if self._send_message(token, chat_id, text):
                success += 1
            else:
                failed.append(chat_id)
        return {
            "status": "ok" if success > 0 else "error",
            "success_count": success,
            "failed_chat_ids": failed,
            "total_chat_ids": len(chat_ids),
        }

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                cfg = self._cfg_getter()
                token = str(cfg.get("bot_token") or "").strip()
                if not token:
                    time.sleep(3)
                    continue

                self._ensure_commands(token)
                updates = self._get_updates(token, self._offset, timeout=20)
                if not updates:
                    continue
                for item in updates:
                    self._offset = max(self._offset, int(item.get("update_id", 0)) + 1)
                    self._handle_update(token, cfg, item)
            except Exception as e:
                self._logger.warning("Telegram 轮询异常: %s", e)
                time.sleep(3)

    def _get_updates(self, token: str, offset: int, timeout: int = 20):
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        payload = {
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": ["message"],
        }
        r = requests.get(url, params=payload, timeout=timeout + 5)
        if not r.ok:
            self._logger.warning("Telegram getUpdates HTTP %s: %s", r.status_code, (r.text or "")[:200])
            return []
        data = r.json() if r.content else {}
        if not isinstance(data, dict) or not data.get("ok"):
            return []
        result = data.get("result")
        return result if isinstance(result, list) else []

    def _handle_update(self, token: str, cfg: Dict, item: Dict):
        msg = item.get("message") if isinstance(item, dict) else None
        if not isinstance(msg, dict):
            return
        text = str(msg.get("text") or "").strip()
        if not text:
            return

        chat = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
        user = msg.get("from") if isinstance(msg.get("from"), dict) else {}
        chat_id = str(chat.get("id") or "").strip()
        user_id = str(user.get("id") or "").strip()
        if not chat_id:
            return

        if not self._is_allowed(cfg, chat_id, user_id):
            self._send_message(token, chat_id, "无权限执行该命令。")
            return

        if text in {"/", "/help", "/start"}:
            self._send_message(token, chat_id, self._build_help_text())
            return
        if text.startswith("/cookies"):
            self._send_message(token, chat_id, self._on_cookie_status())
            return
        if text.startswith("/count"):
            self._send_message(token, chat_id, self._on_count())
            return
        if text.startswith("/search"):
            keyword = text[len("/search"):].strip()
            if not keyword:
                self._send_message(token, chat_id, "🔎 用法：/search 关键词\n例如：/search Garfield")
                return
            self._send_message(token, chat_id, self._on_search(keyword))
            return
        if text.startswith("/url"):
            curr = self._on_get_base_url()
            self._send_message(token, chat_id, f"🌐 当前在线地址前缀：\n{curr}")
            return
        if text.startswith("/seturl"):
            raw = text[len("/seturl"):].strip()
            if not raw:
                self._send_message(
                    token,
                    chat_id,
                    "⚙️ 用法：/seturl http://127.0.0.1:8000\n"
                    "示例：/seturl https://your-domain.com",
                )
                return
            msg = self._on_set_base_url(raw)
            self._send_message(token, chat_id, msg)
            return

        model_url = extract_makerworld_model_url(text)
        if not model_url:
            self._send_message(token, chat_id, self._build_invalid_link_text())
            return

        self._send_message(token, chat_id, f"📥 已收到归档请求，开始处理：\n{model_url}")
        try:
            result = self._on_archive_url(model_url)
            payload = result.get("notify_payload") if isinstance(result, dict) else None
            if isinstance(payload, dict):
                text_msg = self._format_success_text(payload)
                photo = str(payload.get("cover_url") or "").strip()
                if photo and photo.lower().startswith(("http://", "https://")):
                    if self._send_photo(token, chat_id, photo, text_msg):
                        if int(payload.get("missing_count") or 0) > 0:
                            self._send_message(token, chat_id, self._build_missing_3mf_warning(payload))
                        return
                self._send_message(token, chat_id, text_msg)
                if int(payload.get("missing_count") or 0) > 0:
                    self._send_message(token, chat_id, self._build_missing_3mf_warning(payload))
            else:
                self._send_message(token, chat_id, "归档完成。")
        except Exception as e:
            self._send_message(token, chat_id, f"❌ 归档失败：{e}")

    def _target_chat_ids(self, cfg: Dict) -> list[str]:
        chat_ids = _split_ids(cfg.get("chat_id"))
        return sorted(chat_ids)

    def _is_allowed(self, cfg: Dict, chat_id: str, user_id: str) -> bool:
        del user_id
        allow_chats = set(self._target_chat_ids(cfg))
        if not allow_chats:
            return False
        return chat_id in allow_chats

    def _send_message(self, token: str, chat_id: str, text: str) -> bool:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": text}
        try:
            r = requests.post(url, json=data, timeout=10)
            return bool(r.ok)
        except Exception as e:
            self._logger.warning("Telegram sendMessage 失败: %s", e)
            return False

    def _send_photo(self, token: str, chat_id: str, photo_url: str, caption: str) -> bool:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        data = {"chat_id": chat_id, "photo": photo_url, "caption": caption}
        try:
            r = requests.post(url, json=data, timeout=15)
            return bool(r.ok)
        except Exception as e:
            self._logger.warning("Telegram sendPhoto 失败: %s", e)
            return False

    def _ensure_commands(self, token: str):
        if self._commands_token == token:
            return
        url = f"https://api.telegram.org/bot{token}/setMyCommands"
        commands = {
            "commands": [
                {"command": "help", "description": "查看命令说明"},
                {"command": "cookies", "description": "查看 Cookie 状态"},
                {"command": "count", "description": "查看已归档模型总数"},
                {"command": "search", "description": "按关键词搜索本地模型"},
                {"command": "url", "description": "查看在线地址前缀"},
                {"command": "seturl", "description": "设置在线地址前缀"},
            ]
        }
        try:
            r = requests.post(url, json=commands, timeout=10)
            if r.ok:
                self._commands_token = token
        except Exception as e:
            self._logger.warning("Telegram setMyCommands 失败: %s", e)

    def _build_help_text(self) -> str:
        return (
            "🤖 可用命令列表\n"
            "• /help：查看命令说明\n"
            "• /cookies：查看当前 Cookie 状态和更新时间\n"
            "• /count：查看本地已归档模型总数\n"
            "• /search 关键词：搜索库中模型标题并返回在线地址\n"
            "• /url：查看当前在线地址前缀\n"
            "• /seturl 地址：设置在线地址前缀\n\n"
            "📎 也可以直接发送 MakerWorld 模型链接，机器人会自动触发归档。"
        )

    def _build_invalid_link_text(self) -> str:
        return (
            "⚠️ 未识别到有效模型链接。\n"
            "请发送 MakerWorld 模型链接，或使用以下命令：\n"
            "• /cookies：查看 Cookie 状态\n"
            "• /count：查看已归档模型总数\n"
            "• /search 关键词：按关键词搜索本地模型\n"
            "• /url：查看在线地址前缀\n"
            "• /seturl 地址：设置在线地址前缀\n"
            "• /help：查看完整命令说明"
        )

    def _build_missing_3mf_warning(self, payload: Dict) -> str:
        miss = int(payload.get("missing_count") or 0)
        return (
            "⚠️ 检测到模型下载异常\n"
            f"缺失 3MF 数量：{miss}\n"
            "可能触发了验证机制，请先在网页端手动下载任意模型完成验证，再重试缺失下载。"
        )

    def _format_success_text(self, payload: Dict) -> str:
        title = str(payload.get("title") or "")
        online_url = str(payload.get("online_url") or "")
        action = str(payload.get("action") or "created")
        action_text = "模型已更新" if action == "updated" else "模型归档成功"
        base_name = str(payload.get("base_name") or "")
        missing_count = int(payload.get("missing_count") or 0)
        lines = [f"✅ {action_text}"]
        if title:
            lines.append(f"📌 标题：{title}")
        if base_name:
            lines.append(f"📁 目录：{base_name}")
        if online_url:
            lines.append(f"🌐 在线地址：{online_url}")
        if missing_count > 0:
            lines.append(f"⚠️ 缺失 3MF：{missing_count}")
        return "\n".join(lines)
