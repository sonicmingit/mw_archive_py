(function () {
  "use strict";

  var STORAGE_KEY = "mw_theme";
  var THEME_LIGHT = "light";
  var THEME_DARK = "dark";

  function normalizeTheme(raw) {
    return raw === THEME_DARK ? THEME_DARK : THEME_LIGHT;
  }

  function getCurrentTheme() {
    var attr = document.documentElement.getAttribute("data-theme");
    if (attr) return normalizeTheme(attr);
    try {
      return normalizeTheme(localStorage.getItem(STORAGE_KEY));
    } catch (_) {
      return THEME_LIGHT;
    }
  }

  function persistTheme(theme) {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (_) {
      // ignore storage errors
    }
  }

  function applyTheme(theme) {
    var t = normalizeTheme(theme);
    document.documentElement.setAttribute("data-theme", t);
    return t;
  }

  function syncToggleButton(btn, theme) {
    if (!btn) return;
    var icon = btn.querySelector("i");
    var label = btn.querySelector(".theme-toggle-label");
    if (theme === THEME_DARK) {
      if (icon) icon.className = "fas fa-sun";
      if (label) label.textContent = "浅色";
      btn.title = "切换到浅色模式";
      btn.setAttribute("aria-label", "切换到浅色模式");
    } else {
      if (icon) icon.className = "fas fa-moon";
      if (label) label.textContent = "暗黑";
      btn.title = "切换到暗黑模式";
      btn.setAttribute("aria-label", "切换到暗黑模式");
    }
  }

  function syncAllButtons(theme) {
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    buttons.forEach(function (btn) {
      syncToggleButton(btn, theme);
    });
  }

  function toggleTheme() {
    var current = getCurrentTheme();
    var next = current === THEME_DARK ? THEME_LIGHT : THEME_DARK;
    var applied = applyTheme(next);
    persistTheme(applied);
    syncAllButtons(applied);
  }

  function init() {
    var applied = applyTheme(getCurrentTheme());
    syncAllButtons(applied);
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", toggleTheme);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
