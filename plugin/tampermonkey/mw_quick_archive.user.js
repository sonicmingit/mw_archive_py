// ==UserScript==
// @name         快速归档助手
// @namespace    https://makerworld.com/
// @version      1.0.3
// @description  在 MW 模型页一键归档，支持后端地址与手动 Cookie 配置
// @author       sonic
// @match        https://makerworld.com.cn/zh/models/*
// @match        https://makerworld.com/zh/models/*
// @icon         https://aliyun-wb-h9vflo19he.oss-cn-shanghai.aliyuncs.com/use/makerworld_archive.png
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @grant        GM_xmlhttpRequest
// @grant        GM_notification
// @connect      *
// @noframes
// ==/UserScript==

(function () {
  'use strict';
  if (window.top !== window.self) return;
  if (window.__MW_QUICK_ARCHIVE_LOADED__) return;
  window.__MW_QUICK_ARCHIVE_LOADED__ = true;

  const KEY_API_BASE = 'mw_archive_api_base';
  const KEY_MANUAL_COOKIE = 'mw_archive_manual_cookie';
  const DEFAULT_API_BASE = 'http://127.0.0.1:8000';
  const BTN_ID = 'mw-quick-archive-btn';
  const MODAL_ID = 'mw-quick-archive-modal';
  const NOTICE_ID = 'mw-quick-archive-notice';
  const REQUEST_DEDUP_MS = 2000;
  let archiveInFlight = false;
  let lastArchiveAt = 0;

  function getApiBase() {
    const raw = GM_getValue(KEY_API_BASE, DEFAULT_API_BASE);
    return String(raw || DEFAULT_API_BASE).trim().replace(/\/+$/, '');
  }

  function setApiBase(url) {
    const normalized = String(url || '').trim().replace(/\/+$/, '');
    GM_setValue(KEY_API_BASE, normalized || DEFAULT_API_BASE);
  }

  function getManualCookie() {
    return String(GM_getValue(KEY_MANUAL_COOKIE, '') || '').trim();
  }

  function setManualCookie(cookie) {
    GM_setValue(KEY_MANUAL_COOKIE, String(cookie || '').trim());
  }

  function notify(text, title = '归档助手') {
    try {
      GM_notification({ title, text, timeout: 2500 });
    } catch (_) {
      // no-op
    }
    console.log(`[MW-ARCHIVER] ${text}`);
  }

  function showNotice(title, text, tone = 'loading') {
    const old = document.getElementById(NOTICE_ID);
    if (old) {
      try { old.remove(); } catch (_) {}
    }
    const overlay = document.createElement('div');
    overlay.id = NOTICE_ID;
    overlay.style.cssText = [
      'position:fixed',
      'inset:0',
      'z-index:2147483647',
      'background:rgba(15,23,42,.4)',
      'display:flex',
      'align-items:center',
      'justify-content:center',
      'padding:20px',
    ].join(';');
    const colors = tone === 'success'
      ? { bg: '#ecfeff', border: '#06b6d4', title: '#155e75', text: '#164e63' }
      : tone === 'error'
        ? { bg: '#fff1f2', border: '#f43f5e', title: '#9f1239', text: '#881337' }
        : { bg: '#f0fdf4', border: '#22c55e', title: '#166534', text: '#14532d' };
    const panel = document.createElement('div');
    panel.style.cssText = [
      'width:min(92vw,420px)',
      `background:${colors.bg}`,
      `border:3px solid ${colors.border}`,
      'border-radius:18px',
      'box-shadow:0 24px 60px rgba(15,23,42,.28)',
      'padding:22px 24px',
      'text-align:center',
      'font-family:system-ui,-apple-system,Segoe UI,Roboto,Microsoft YaHei,sans-serif',
    ].join(';');
    panel.innerHTML = `
      <div style="font-size:24px;font-weight:800;color:${colors.title};margin-bottom:10px;">${title}</div>
      <div style="font-size:15px;line-height:1.7;color:${colors.text};white-space:pre-wrap;">${text}</div>
    `;
    overlay.appendChild(panel);
    overlay.addEventListener('click', () => {
      try { overlay.remove(); } catch (_) {}
    });
    document.body.appendChild(overlay);
    setTimeout(() => {
      if (tone === 'loading') {
        try { overlay.remove(); } catch (_) {}
      }
    }, 1600);
  }

  function requestJson(method, url, bodyObj) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method,
        url,
        headers: {
          'Content-Type': 'application/json',
        },
        data: bodyObj ? JSON.stringify(bodyObj) : undefined,
        timeout: 30000,
        onload: (resp) => {
          const text = resp.responseText || '';
          if (resp.status >= 200 && resp.status < 300) {
            try {
              resolve(text ? JSON.parse(text) : {});
            } catch (_) {
              resolve({});
            }
            return;
          }
          reject(new Error(`HTTP ${resp.status}: ${text.slice(0, 300)}`));
        },
        onerror: () => reject(new Error('网络请求失败')),
        ontimeout: () => reject(new Error('请求超时')),
      });
    });
  }

  function parseCookieNames(cookieStr) {
    const names = [];
    const parts = String(cookieStr || '').split(';').map(s => s.trim()).filter(Boolean);
    for (const p of parts) {
      const idx = p.indexOf('=');
      if (idx <= 0) continue;
      names.push(p.slice(0, idx).trim());
    }
    return names;
  }

  function ensureModelPage() {
    return /^https:\/\/makerworld\.(com|com\.cn)\/zh\/models\/.+/i.test(location.href);
  }

  async function syncManualCookieToBackend(cookieText) {
    const cookie = String(cookieText || '').trim();
    if (!cookie) {
      notify('请先手动填写 Cookie');
      return;
    }
    const api = getApiBase();
    const count = parseCookieNames(cookie).length;
    notify(`正在同步手动 Cookie (项数: ${count})...`);
    await requestJson('POST', `${api}/api/cookie`, { cookie });
    notify('手动 Cookie 同步成功');
  }

  async function archiveCurrentModel() {
    const now = Date.now();
    if (archiveInFlight || now - lastArchiveAt < REQUEST_DEDUP_MS) {
      notify('归档请求进行中，请勿重复触发');
      return;
    }
    archiveInFlight = true;
    lastArchiveAt = now;
    if (!ensureModelPage()) {
      archiveInFlight = false;
      notify('当前页面不是可归档模型页');
      return;
    }
    const api = getApiBase();
    const url = location.href.split('#')[0];
    showNotice('开始归档', '当前模型已提交归档，请等待完成提示。', 'loading');
    notify('开始归档模型...');
    try {
      const data = await requestJson('POST', `${api}/api/archive`, { url });
      const msg = data.message || (data.action === 'updated' ? '模型已更新成功' : '模型归档成功');
      notify(`${msg}: ${data.base_name || ''}`);
      showNotice('归档完成', `${msg}${data.base_name ? `\n${data.base_name}` : ''}`, 'success');
    } catch (err) {
      notify(`归档失败: ${err.message}`);
      showNotice('归档失败', err.message, 'error');
    } finally {
      archiveInFlight = false;
    }
  }

  async function redownloadMissing3mf() {
    const api = getApiBase();
    notify('开始重下缺失 3MF...');
    try {
      const data = await requestJson('POST', `${api}/api/logs/missing-3mf/redownload`);
      const processed = Number(data.processed || 0);
      const success = Number(data.success || 0);
      const failed = Number(data.failed || 0);
      if (processed <= 0) {
        notify('缺失 3MF 列表为空，无需重下');
        return;
      }
      notify(`缺失 3MF 重下完成: 成功 ${success}，失败 ${failed}，共 ${processed}`);
    } catch (err) {
      notify(`缺失 3MF 重下失败: ${err.message}`);
    }
  }

  function openSettingsModal() {
    let modal = document.getElementById(MODAL_ID);
    if (!modal) {
      modal = document.createElement('div');
      modal.id = MODAL_ID;
      modal.style.cssText = [
        'position:fixed',
        'inset:0',
        'z-index:2147483647',
        'background:rgba(0,0,0,.45)',
        'display:flex',
        'align-items:center',
        'justify-content:center',
      ].join(';');

      const panel = document.createElement('div');
      panel.style.cssText = [
        'width:min(92vw,480px)',
        'background:#fff',
        'border-radius:10px',
        'padding:16px',
        'box-shadow:0 8px 24px rgba(0,0,0,.25)',
        'font-family:system-ui,-apple-system,Segoe UI,Roboto,Microsoft YaHei,sans-serif',
        'color:#222',
      ].join(';');

      panel.innerHTML = `
        <div style="font-size:16px;font-weight:700;margin-bottom:10px;">归档助手配置</div>
        <div style="font-size:13px;color:#666;margin-bottom:8px;">后端 API 地址</div>
        <input id="mw-quick-api-input" type="text"
          style="width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #ddd;border-radius:8px;font-size:13px;margin-bottom:10px;"
          placeholder="http://127.0.0.1:8000" />
        <div style="font-size:13px;color:#666;margin-bottom:8px;">手动 Cookie</div>
        <textarea id="mw-quick-cookie-input"
          style="width:100%;min-height:100px;box-sizing:border-box;padding:8px 10px;border:1px solid #ddd;border-radius:8px;font-size:12px;font-family:Consolas,'Courier New',monospace;"
          placeholder="请粘贴完整 Cookie（建议从请求头复制）"></textarea>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px;">
          <button id="mw-quick-cancel" style="padding:7px 12px;border:1px solid #ddd;background:#fff;border-radius:8px;cursor:pointer;">取消</button>
          <button id="mw-quick-save-cookie" style="padding:7px 12px;border:0;background:#007b55;color:#fff;border-radius:8px;cursor:pointer;">保存并同步 Cookie</button>
          <button id="mw-quick-save" style="padding:7px 12px;border:0;background:#0ea5e9;color:#fff;border-radius:8px;cursor:pointer;">保存</button>
        </div>
      `;

      modal.appendChild(panel);
      document.body.appendChild(modal);

      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
      });

      panel.querySelector('#mw-quick-cancel').addEventListener('click', () => {
        modal.remove();
      });

      panel.querySelector('#mw-quick-save').addEventListener('click', () => {
        const input = panel.querySelector('#mw-quick-api-input');
        setApiBase(input.value);
        notify(`已保存后端地址: ${getApiBase()}`);
        modal.remove();
      });

      panel.querySelector('#mw-quick-save-cookie').addEventListener('click', async () => {
        try {
          const cookieInput = panel.querySelector('#mw-quick-cookie-input');
          const cookieText = String(cookieInput.value || '').trim();
          if (!cookieText) {
            notify('手动 Cookie 不能为空');
            return;
          }
          setManualCookie(cookieText);
          await syncManualCookieToBackend(cookieText);
          modal.remove();
        } catch (err) {
          notify(`手动 Cookie 同步失败: ${err.message}`);
        }
      });
    }

    const input = modal.querySelector('#mw-quick-api-input');
    if (input) input.value = getApiBase();
    const cookieInput = modal.querySelector('#mw-quick-cookie-input');
    if (cookieInput) cookieInput.value = getManualCookie();
  }

  function injectArchiveButton() {
    if (!ensureModelPage()) return;
    if (document.getElementById(BTN_ID)) return;

    const btn = document.createElement('button');
    btn.id = BTN_ID;
    btn.type = 'button';
    btn.innerHTML = '<span style="font-size:14px;line-height:1;display:inline-block;">📦</span><span>归档模型</span>';
    btn.style.cssText = [
      'position:fixed',
      'right:18px',
      'bottom:18px',
      'z-index:2147483646',
      'padding:10px 18px',
      'border:none',
      'border-radius:999px',
      'background:#00b800',
      'color:#fff',
      'font-size:13px',
      'font-weight:700',
      'line-height:1',
      'display:inline-flex',
      'align-items:center',
      'gap:8px',
      'white-space:nowrap',
      'font-family:system-ui,-apple-system,Segoe UI,Roboto,Microsoft YaHei,sans-serif',
      'cursor:pointer',
      'box-shadow:0 6px 16px rgba(0,0,0,.25)',
    ].join(';');

    btn.addEventListener('mouseenter', () => { btn.style.background = '#00a800'; });
    btn.addEventListener('mouseleave', () => { btn.style.background = '#00b800'; });
    btn.addEventListener('click', archiveCurrentModel);
    document.body.appendChild(btn);
  }

  GM_registerMenuCommand('⚙️ 设置后端地址与手动 Cookie', openSettingsModal);
  GM_registerMenuCommand('归档当前模型', archiveCurrentModel);
  GM_registerMenuCommand('重新下载缺失 3MF 文件', redownloadMissing3mf);
  GM_registerMenuCommand('🍪 手动 Cookie 同步到后端', async () => {
    const manual = getManualCookie();
    if (!manual) {
      notify('未找到已保存的手动 Cookie，请先在设置中保存');
      openSettingsModal();
      return;
    }
    try {
      await syncManualCookieToBackend(manual);
    } catch (err) {
      notify(`手动同步失败: ${err.message}`);
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectArchiveButton);
  } else {
    injectArchiveButton();
  }
})();
