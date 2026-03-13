(function () {
  "use strict";
  if (window.__MW_ARCHIVE_EXT_LOADED__) return;
  window.__MW_ARCHIVE_EXT_LOADED__ = true;

  const BTN_ID = "mw-archive-ext-btn";
  const NOTICE_ID = "mw-archive-ext-notice";
  let inFlight = false;

  function isTargetPage() {
    return /^https:\/\/makerworld\.(com|com\.cn)\/zh\/models\/.+/i.test(location.href);
  }

  function toast(text) {
    const el = document.createElement("div");
    el.textContent = text;
    el.style.cssText = [
      "position:fixed",
      "right:18px",
      "bottom:70px",
      "z-index:2147483647",
      "background:rgba(0,0,0,.78)",
      "color:#fff",
      "padding:8px 12px",
      "border-radius:8px",
      "font-size:12px",
      "font-weight:600",
      "font-family:system-ui,-apple-system,Segoe UI,Roboto,Microsoft YaHei,sans-serif"
    ].join(";");
    document.body.appendChild(el);
    setTimeout(() => {
      try { el.remove(); } catch (_) {}
    }, 2600);
  }

  function showNotice(title, text, tone) {
    const old = document.getElementById(NOTICE_ID);
    if (old) {
      try { old.remove(); } catch (_) {}
    }
    const overlay = document.createElement("div");
    overlay.id = NOTICE_ID;
    overlay.style.cssText = [
      "position:fixed",
      "inset:0",
      "z-index:2147483647",
      "background:rgba(15,23,42,.38)",
      "display:flex",
      "align-items:center",
      "justify-content:center",
      "padding:20px"
    ].join(";");
    const colors = tone === "success"
      ? { bg: "#ecfeff", border: "#06b6d4", title: "#155e75", text: "#164e63" }
      : tone === "error"
        ? { bg: "#fff1f2", border: "#f43f5e", title: "#9f1239", text: "#881337" }
        : { bg: "#f0fdf4", border: "#22c55e", title: "#166534", text: "#14532d" };
    const panel = document.createElement("div");
    panel.style.cssText = [
      "width:min(92vw,420px)",
      `background:${colors.bg}`,
      `border:3px solid ${colors.border}`,
      "border-radius:18px",
      "box-shadow:0 24px 60px rgba(15,23,42,.28)",
      "padding:22px 24px",
      "text-align:center",
      'font-family:system-ui,-apple-system,Segoe UI,Roboto,Microsoft YaHei,sans-serif'
    ].join(";");
    panel.innerHTML = `
      <div style="font-size:24px;font-weight:800;color:${colors.title};margin-bottom:10px;">${title}</div>
      <div style="font-size:15px;line-height:1.7;color:${colors.text};white-space:pre-wrap;">${text}</div>
    `;
    overlay.appendChild(panel);
    overlay.addEventListener("click", () => {
      try { overlay.remove(); } catch (_) {}
    });
    document.body.appendChild(overlay);
    setTimeout(() => {
      if (tone === "loading") {
        try { overlay.remove(); } catch (_) {}
      }
    }, 1600);
  }

  async function sendMessage(payload) {
    return chrome.runtime.sendMessage(payload);
  }

  async function onArchiveClick() {
    if (inFlight) {
      toast("归档进行中，请稍后");
      return;
    }
    inFlight = true;
    try {
      showNotice("开始归档", "当前模型已提交归档，请等待完成提示。", "loading");
      const res = await sendMessage({
        action: "archiveModel",
        url: location.href.split("#")[0]
      });
      if (res && res.ok) {
        const message = res.message || "归档成功";
        toast(message);
        showNotice("归档完成", message, "success");
      } else {
        const message = (res && res.message) || "归档失败";
        toast(message);
        showNotice("归档失败", message, "error");
      }
    } catch (err) {
      const message = `归档失败: ${err && err.message ? err.message : err}`;
      toast(message);
      showNotice("归档失败", message, "error");
    } finally {
      inFlight = false;
    }
  }

  function injectButton() {
    if (!isTargetPage()) return;
    if (document.getElementById(BTN_ID)) return;

    const btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.type = "button";
    btn.innerHTML = '<span style="font-size:14px;line-height:1;display:inline-block;">📦</span><span>归档模型</span>';
    btn.style.cssText = [
      "position:fixed",
      "right:18px",
      "bottom:18px",
      "z-index:2147483646",
      "padding:10px 18px",
      "border:none",
      "border-radius:999px",
      "background:#00b800",
      "color:#fff",
      "font-size:13px",
      "font-weight:700",
      "line-height:1",
      "display:inline-flex",
      "align-items:center",
      "gap:8px",
      "white-space:nowrap",
      "font-family:system-ui,-apple-system,Segoe UI,Roboto,Microsoft YaHei,sans-serif",
      "cursor:pointer",
      "box-shadow:0 6px 16px rgba(0,0,0,.25)"
    ].join(";");
    btn.addEventListener("mouseenter", () => { btn.style.background = "#00a800"; });
    btn.addEventListener("mouseleave", () => { btn.style.background = "#00b800"; });
    btn.addEventListener("click", onArchiveClick);
    document.body.appendChild(btn);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectButton);
  } else {
    injectButton();
  }
})();
