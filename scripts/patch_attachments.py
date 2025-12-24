from pathlib import Path
import re
import sys


ATTACH_HTML = """
  <div class="section-title">\u9644\u4ef6</div>
  <div class="attachments">
    <div class="attach-upload">
      <input type="file" id="attachInput">
      <button class="attach-btn" type="button" id="attachUploadBtn">\u4e0a\u4f20\u9644\u4ef6</button>
      <span class="attach-msg" id="attachMsg"></span>
    </div>
    <ul class="attach-list" id="attachList"></ul>
  </div>
""".strip("\n")

ATTACH_JS = """
(function() {
  const listEl = document.getElementById('attachList');
  const msgEl = document.getElementById('attachMsg');
  const inputEl = document.getElementById('attachInput');
  const btnEl = document.getElementById('attachUploadBtn');
  if (!listEl) return;

  function setMsg(text, isError) {
    if (!msgEl) return;
    msgEl.textContent = text || '';
    if (isError) msgEl.classList.add('error');
    else msgEl.classList.remove('error');
  }

  function getModelDir() {
    const path = window.location.pathname || '';
    const parts = path.split('/').filter(Boolean);
    const filesIdx = parts.indexOf('files');
    if (filesIdx >= 0 && parts.length > filesIdx + 1) return decodeURIComponent(parts[filesIdx + 1]);
    if (parts.length >= 2) return decodeURIComponent(parts[parts.length - 2]);
    return '';
  }

  const modelDir = getModelDir();
  if (!modelDir) {
    setMsg('\u65e0\u6cd5\u8bc6\u522b\u6a21\u578b\u76ee\u5f55', true);
    return;
  }

  function renderList(files) {
    listEl.innerHTML = '';
    if (!files || files.length === 0) {
      const li = document.createElement('li');
      li.className = 'attach-empty';
      li.textContent = '\u6682\u65e0\u9644\u4ef6';
      listEl.appendChild(li);
      return;
    }
    files.forEach((name) => {
      const li = document.createElement('li');
      const link = document.createElement('a');
      link.href = './file/' + encodeURIComponent(name);
      link.textContent = name;
      link.setAttribute('download', name);
      li.appendChild(link);
      listEl.appendChild(li);
    });
  }

  function loadList() {
    if (location.protocol === 'file:') {
      renderList([]);
      setMsg('\u8bf7\u901a\u8fc7\u672c\u5730\u670d\u52a1\u6253\u5f00\u9875\u9762\u4ee5\u67e5\u770b\u9644\u4ef6\u5217\u8868', true);
      return;
    }
    fetch('/api/models/' + encodeURIComponent(modelDir) + '/attachments')
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data) => {
        renderList((data && data.files) || []);
        setMsg('');
      })
      .catch(() => {
        renderList([]);
        setMsg('\u9644\u4ef6\u5217\u8868\u52a0\u8f7d\u5931\u8d25', true);
      });
  }

  loadList();

  if (!btnEl || !inputEl) return;
  btnEl.addEventListener('click', () => {
    const file = inputEl.files && inputEl.files[0];
    if (!file) {
      setMsg('\u8bf7\u9009\u62e9\u9644\u4ef6', true);
      return;
    }
    if (location.protocol === 'file:') {
      setMsg('\u8bf7\u901a\u8fc7\u672c\u5730\u670d\u52a1\u6253\u5f00\u9875\u9762\u4ee5\u4fbf\u4e0a\u4f20', true);
      return;
    }
    const fd = new FormData();
    fd.append('file', file);
    btnEl.disabled = true;
    setMsg('\u4e0a\u4f20\u4e2d...');
    fetch('/api/models/' + encodeURIComponent(modelDir) + '/attachments', {
      method: 'POST',
      body: fd,
    })
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then(() => {
        inputEl.value = '';
        setMsg('\u4e0a\u4f20\u6210\u529f');
        loadList();
      })
      .catch(() => {
        setMsg('\u4e0a\u4f20\u5931\u8d25', true);
      })
      .finally(() => {
        btnEl.disabled = false;
      });
  });
})();
""".strip("\n")

ATTACH_CSS = """
.attachments {
  margin-bottom: 10px;
}

.attach-upload {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.attach-upload input[type="file"] {
  font-size: 13px;
}

.attach-btn {
  background: #1976d2;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 13px;
}

.attach-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.attach-msg {
  font-size: 12px;
  color: #666;
}

.attach-msg.error {
  color: #b00020;
}

.attach-list {
  list-style: none;
  padding-left: 0;
  margin: 10px 0 0;
}

.attach-list li {
  margin: 4px 0;
  font-size: 13px;
}

.attach-list a {
  color: #1976d2;
  text-decoration: none;
}

.attach-list a:hover {
  text-decoration: underline;
}

.attach-empty {
  color: #888;
}
""".strip("\n")


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def insert_attachments_html(text: str) -> str | None:
    if 'id="attachList"' in text:
        return None
    m = re.search(r"</div>\s*\n\s*<div class=\"lightbox\"", text)
    if not m:
        return None
    nl = detect_newline(text)
    block = ATTACH_HTML.replace("\n", nl)
    insert_at = m.start()
    return text[:insert_at] + nl + block + nl + nl + text[insert_at:]


def insert_attachments_js(text: str) -> str | None:
    if "attachUploadBtn" in text:
        return None
    idx = text.rfind("</script>")
    if idx == -1:
        return None
    nl = detect_newline(text)
    block = ATTACH_JS.replace("\n", nl)
    return text[:idx] + nl + block + nl + text[idx:]


def insert_attachments_css(text: str) -> str | None:
    if ".attachments" in text:
        return None
    nl = detect_newline(text)
    block = ATTACH_CSS.replace("\n", nl)
    m = re.search(r"\n\.instances \.inst-card", text)
    if m:
        idx = m.start()
        return text[:idx] + nl + block + nl + text[idx:]
    return text + nl + nl + block + nl


def patch_get_model_dir(text: str) -> str:
    text = text.replace("return parts[filesIdx + 1];", "return decodeURIComponent(parts[filesIdx + 1]);")
    text = text.replace("return parts[parts.length - 2];", "return decodeURIComponent(parts[parts.length - 2]);")
    return text


def patch_index(index_path: Path) -> bool:
    original = index_path.read_text(encoding="utf-8")
    updated = insert_attachments_html(original) or original
    updated = insert_attachments_js(updated) or updated
    updated = patch_get_model_dir(updated)
    if updated != original:
        index_path.write_text(updated, encoding="utf-8")
        return True
    return False


def patch_style(style_path: Path) -> bool:
    original = style_path.read_text(encoding="utf-8")
    updated = insert_attachments_css(original) or original
    if updated != original:
        style_path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("app/data")
    if not root.exists():
        print(f"root not found: {root}")
        return 1

    changed_indexes = []
    changed_styles = []
    if root.is_dir() and root.name.startswith("MW_") and (root / "index.html").exists():
        model_dirs = [root]
    else:
        model_dirs = sorted(root.glob("MW_*"))
    for model_dir in model_dirs:
        if not model_dir.is_dir():
            continue
        index_path = model_dir / "index.html"
        if index_path.exists() and patch_index(index_path):
            changed_indexes.append(str(index_path))
        style_path = model_dir / "style.css"
        if style_path.exists() and patch_style(style_path):
            changed_styles.append(str(style_path))

    print(f"updated index.html: {len(changed_indexes)}")
    for p in changed_indexes:
        print(f" - {p}")
    print(f"updated style.css: {len(changed_styles)}")
    for p in changed_styles:
        print(f" - {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
