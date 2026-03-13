function setStatus(text) {
  const el = document.getElementById("status");
  el.textContent = text;
}

function send(msg) {
  return chrome.runtime.sendMessage(msg);
}

function normalizeApiBase(raw) {
  return String(raw || "").trim().replace(/\/+$/, "");
}

async function getActiveTabUrl() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs && tabs[0];
  return tab && tab.url ? tab.url : "";
}

function isModelUrl(url) {
  return /^https:\/\/makerworld\.(com|com\.cn)\/zh\/models\/.+/i.test(url || "");
}

let noticeTimer = null;

function showPopupNotice(title, text, tone = "info") {
  let notice = document.getElementById("popupNotice");
  if (!notice) {
    notice = document.createElement("div");
    notice.id = "popupNotice";
    notice.className = "popup-notice hidden";
    notice.innerHTML = `
      <div class="popup-notice-card">
        <div id="popupNoticeTitle" class="popup-notice-title"></div>
        <div id="popupNoticeText" class="popup-notice-text"></div>
        <button id="popupNoticeClose" class="popup-notice-close" type="button">知道了</button>
      </div>
    `;
    document.body.appendChild(notice);
    notice.addEventListener("click", (event) => {
      if (event.target === notice) {
        hidePopupNotice();
      }
    });
    notice.querySelector("#popupNoticeClose").addEventListener("click", hidePopupNotice);
  }
  const titleEl = document.getElementById("popupNoticeTitle");
  const textEl = document.getElementById("popupNoticeText");
  titleEl.textContent = title;
  textEl.textContent = text;
  notice.dataset.tone = tone;
  notice.classList.remove("hidden");
  if (noticeTimer) {
    clearTimeout(noticeTimer);
    noticeTimer = null;
  }
  if (tone === "loading") {
    noticeTimer = setTimeout(() => {
      hidePopupNotice();
    }, 1600);
  }
}

function hidePopupNotice() {
  const notice = document.getElementById("popupNotice");
  if (!notice) return;
  notice.classList.add("hidden");
  if (noticeTimer) {
    clearTimeout(noticeTimer);
    noticeTimer = null;
  }
}

async function init() {
  const res = await send({ action: "getApiBase" });
  if (res && res.ok) {
    document.getElementById("apiBase").value = res.apiBase || "";
  }
  setStatus("准备就绪");
}

document.getElementById("saveBtn").addEventListener("click", async () => {
  const apiBase = normalizeApiBase(document.getElementById("apiBase").value);
  const res = await send({ action: "setApiBase", apiBase });
  if (res && res.ok) {
    setStatus(`已保存: ${res.apiBase}`);
    document.getElementById("apiBase").value = res.apiBase || "";
  } else {
    setStatus((res && res.message) || "保存失败");
  }
});

document.getElementById("testConnBtn").addEventListener("click", async () => {
  let apiBase = normalizeApiBase(document.getElementById("apiBase").value);
  if (!apiBase) {
    const apiBaseRes = await send({ action: "getApiBase" });
    apiBase = apiBaseRes && apiBaseRes.ok ? normalizeApiBase(apiBaseRes.apiBase || "") : "";
  }
  if (!apiBase) {
    setStatus("请先配置后端 API 地址");
    return;
  }
  setStatus(`测试连接中: ${apiBase}`);
  try {
    const resp = await fetch(`${apiBase}/api/config`, { method: "GET", cache: "no-store" });
    if (!resp.ok) {
      setStatus(`连接失败: HTTP ${resp.status}`);
      return;
    }
    setStatus(`连接成功: ${apiBase}`);
  } catch (e) {
    setStatus(`连接失败: ${e && e.message ? e.message : e}`);
  }
});

document.getElementById("openHomeBtn").addEventListener("click", async () => {
  const inputVal = normalizeApiBase(document.getElementById("apiBase").value);
  let apiBase = inputVal;
  if (!apiBase) {
    const apiBaseRes = await send({ action: "getApiBase" });
    apiBase = apiBaseRes && apiBaseRes.ok ? normalizeApiBase(apiBaseRes.apiBase || "") : "";
  }
  if (!apiBase) {
    setStatus("请先配置后端 API 地址");
    return;
  }
  await chrome.tabs.create({ url: apiBase });
});

document.getElementById("archiveBtn").addEventListener("click", async () => {
  const url = await getActiveTabUrl();
  if (!isModelUrl(url)) {
    setStatus("当前标签不是 MakerWorld 模型页");
    return;
  }
  showPopupNotice("开始归档", "已开始归档当前模型，请等待完成提示。", "loading");
  setStatus("正在归档...");
  const res = await send({ action: "archiveModel", url });
  if (res && res.ok) {
    const base = res.data && res.data.base_name ? `\n${res.data.base_name}` : "";
    setStatus(`${res.message}${base}`);
    showPopupNotice("归档完成", `${res.message}${base}`, "success");
  } else {
    const message = (res && res.message) || "归档失败";
    setStatus(message);
    showPopupNotice("归档失败", message, "error");
  }
});

init().catch((e) => setStatus(`初始化失败: ${e && e.message ? e.message : e}`));
