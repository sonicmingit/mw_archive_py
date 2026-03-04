import html
from datetime import datetime
from typing import Dict, Tuple

import requests


DEFAULT_TELEGRAM_CONFIG: Dict[str, object] = {
    "enabled": False,
    "bot_token": "",
    "chat_id": "",
    "notify_archive_success": True,
    "notify_archive_failed": True,
    "notify_cookie_alert": True,
}


def normalize_telegram_config(raw: object) -> Dict[str, object]:
    data = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_TELEGRAM_CONFIG)
    out["enabled"] = bool(data.get("enabled", out["enabled"]))
    out["bot_token"] = str(data.get("bot_token") or "").strip()
    out["chat_id"] = str(data.get("chat_id") or "").strip()
    out["notify_archive_success"] = bool(data.get("notify_archive_success", out["notify_archive_success"]))
    out["notify_archive_failed"] = bool(data.get("notify_archive_failed", out["notify_archive_failed"]))
    out["notify_cookie_alert"] = bool(data.get("notify_cookie_alert", out["notify_cookie_alert"]))
    return out


def mask_bot_token(token: str) -> str:
    t = str(token or "").strip()
    if not t:
        return ""
    if len(t) <= 8:
        return "*" * len(t)
    return f"{t[:4]}***{t[-4:]}"


def _escape(v: object) -> str:
    return html.escape(str(v or ""))


def send_telegram_message(cfg: Dict[str, object], text: str, parse_mode: str = "HTML") -> Tuple[bool, str]:
    tg = normalize_telegram_config((cfg or {}).get("telegram"))
    if not tg.get("enabled"):
        return False, "telegram disabled"
    token = str(tg.get("bot_token") or "").strip()
    chat_id = str(tg.get("chat_id") or "").strip()
    if not token or not chat_id:
        return False, "missing bot_token/chat_id"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text or "",
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=12)
        if resp.status_code >= 400:
            return False, f"http {resp.status_code}: {(resp.text or '')[:200]}"
        body = resp.json() if resp.content else {}
        if not body.get("ok", False):
            return False, f"telegram error: {(body.get('description') or '')[:200]}"
        return True, "ok"
    except Exception as e:
        return False, str(e)


def is_probable_cookie_issue(err_text: str) -> bool:
    s = (err_text or "").lower()
    keys = [
        "cookie",
        "cf_clearance",
        "cloudflare",
        "验证",
        "拦截",
        "unauthorized",
        "forbidden",
        "403",
        "401",
    ]
    return any(k in s for k in keys)


def format_archive_success_message(url: str, result: Dict[str, object]) -> str:
    base_name = _escape((result or {}).get("base_name") or "")
    work_dir = _escape((result or {}).get("work_dir") or "")
    action = _escape((result or {}).get("action") or "created")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        "✅ <b>归档成功</b>\n"
        f"时间: <code>{_escape(now)}</code>\n"
        f"动作: <code>{action}</code>\n"
        f"模型: <code>{base_name}</code>\n"
        f"链接: {_escape(url)}\n"
        f"目录: <code>{work_dir}</code>"
    )


def format_archive_failed_message(url: str, err_text: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    short_err = _escape((err_text or "")[:500])
    return (
        "❌ <b>归档失败</b>\n"
        f"时间: <code>{_escape(now)}</code>\n"
        f"链接: {_escape(url)}\n"
        f"错误: <code>{short_err}</code>"
    )


def format_cookie_alert_message(url: str, err_text: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    short_err = _escape((err_text or "")[:500])
    return (
        "⚠️ <b>Cookie 可能失效/触发验证</b>\n"
        f"时间: <code>{_escape(now)}</code>\n"
        f"链接: {_escape(url)}\n"
        f"提示: 请更新 Cookie 后重试\n"
        f"详情: <code>{short_err}</code>"
    )

