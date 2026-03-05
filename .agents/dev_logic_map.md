# MakerWorld Archive 开发快速定位手册

> 目的：后续修改时先读本文件，快速定位代码入口与逻辑分层，避免反复全量扫描。
> 适用版本：v5.2（当前代码状态）

## 1. 入口与运行模式

### 1.1 后端入口
- 文件：`app/server.py`
- 初始化：
  - `CFG = load_config()` 读取配置并生成运行时绝对路径
  - `app.mount("/files", StaticFiles(directory=CFG["download_dir"], html=True), name="files")`
  - `app.mount("/static", ...)`

### 1.2 三种页面运行模式（同一套模型详情逻辑）
- 在线详情页：`/v2/files/{model_dir}`
  - 模板：`app/templates/model.html`
  - JS：`app/static/js/model.js`
  - 可调用后端 API（下载、打印）
- 本地服务离线页：`/files/{model_dir}/index.html`
  - 是归档生成的静态页面（内联了 CSS + JS + `window.__OFFLINE_META__`）
  - 由 `app/archiver.py -> build_index_html()` 生成
- 文件直开离线页：`file:///.../index.html`
  - 同样依赖页面内联脚本与 `__OFFLINE_META__`

## 2. 关键逻辑总览

### 2.1 实例下载与打印按钮（前端）
- 文件：`app/static/js/model.js`
- 关键函数：`buildInstanceHtml(inst, baseName)`
- 核心判定：
  - `isFileProtocol = location.protocol === 'file:'`
  - `isOfflineMetaPage = !isFileProtocol && !!window.__OFFLINE_META__`
  - `showBambuButton = !isFileProtocol && !isOfflineMetaPage`
- 结果：
  - 仅在线页显示“打印”按钮
  - `/files/...` 和 `file://` 默认隐藏“打印”按钮
  - 下载链接优先走后端实例接口（HTTP 场景）

### 2.2 实例文件名选择（前端）
- 宽松函数：`pickInstanceFilename()`
- 严格函数：`pickInstanceFilenameStrict()`
- 离线场景（`file://` + `__OFFLINE_META__`）使用严格模式，避免回退到 `title` 造成错链。

### 2.3 实例下载解析（后端）
- 文件：`app/server.py`
- 关键接口：
  - `GET /api/models/{model_dir}/instances/{inst_id}/download`
  - `GET /api/models/{model_dir}/file/{file_path:path}`
  - `GET /api/bambu/model/{model_dir}/instance/{inst_id}.3mf`
- 关键函数：
  - `_candidate_instance_names()`
  - `resolve_instance_filename()`
- 规则：
  - 候选字段顺序：`fileName -> name -> sourceFileName -> localName -> title`
  - 对候选名补 `.3mf` 时使用 `endswith(".3mf")`，避免 `0.28mm` 误判
  - 兼容历史错误文件名：会同时尝试 `xxx.3mf.3mf`

### 2.4 归档页面生成与重建
- 文件：`app/archiver.py`
- 关键函数：
  - `pick_instance_filename()`：避免生成 `xxx.3mf.3mf`
  - `build_index_html(meta, assets)`：把模板 + CSS + JS 内联到 `index.html`，并注入 `window.__OFFLINE_META__`
- 重建入口：
  - `POST /api/archive/rebuild-pages`（`server.py`）
  - 会扫描 `meta.json`，尝试修复实例 `fileName`，并重建 `index.html`

### 2.5 配置文件行为（重点）
- 文件：`app/server.py -> load_config()`
- 当前规则：
  - `app/config.json` 保留用户写的相对路径（不会因打开配置页而回写为绝对路径）
  - 运行时返回绝对路径给程序使用
- 相关接口：
  - `GET /api/config`

### 2.6 手动导入草稿缓存清理
- 草稿目录：`app/tmp/manual_drafts`
- 关键点：
  - 识别产生草稿后可通过接口主动丢弃：
    - `DELETE /api/manual/drafts/{session_id}`
    - `POST /api/manual/drafts/{session_id}/discard`
  - 手动导入成功后会清理对应草稿目录（server 侧兜底）

### 2.7 主题切换（亮色 / 暗黑）
- 共享脚本：`app/static/js/theme.js`
- 存储键：`localStorage["mw_theme"]`，取值 `light` / `dark`
- 页面入口：
  - `app/templates/gallery.html`
  - `app/templates/config.html`
  - `app/templates/model.html`（在线详情页 `/v2/files/{model_dir}`）
  - 以上页面都在 `<head>` 先写入 `data-theme`，减少首屏闪烁
  - 两页都使用 `[data-theme-toggle]` 按钮触发切换
- 样式层：
  - `app/static/css/variables.css`
  - 通过 `:root[data-theme="dark"]` 覆盖变量实现暗黑
  - `@media (prefers-color-scheme: dark)` 仅在未显式设置 `data-theme` 时生效
- 当前范围：
  - 适配主页（模型库）、配置页、在线详情页（`/v2/files/...`）
  - 在线详情页始终跟随主页主题（无单独开关）

## 3. 高频改动定位（按需求找入口）

### 3.1 “下载地址错了 / 404 / 文件名不对”
优先看：
1. `app/static/js/model.js -> buildInstanceHtml()`
2. `app/server.py -> _candidate_instance_names(), resolve_instance_filename()`
3. 对历史模型执行：`POST /api/archive/rebuild-pages`

### 3.2 “离线页和在线页行为不一致”
优先看：
1. `app/static/js/model.js` 的 `isFileProtocol` / `isOfflineMetaPage` 分支
2. 归档页是否使用最新内联脚本（必要时重建 `index.html`）

### 3.3 “打印按钮显示策略调整”
直接改：
- `app/static/js/model.js -> showBambuButton`

### 3.4 “归档结果文件命名异常（如 .3mf.3mf）”
直接改：
- `app/archiver.py -> pick_instance_filename()`
- `app/server.py -> pick_instance_filename()`（兼容重下载/补下载链路）

### 3.5 “主题按钮/暗黑配色要调整”
直接改：
1. `app/static/js/theme.js`（切换行为、文案、图标）
2. `app/static/css/variables.css`（主题变量）
3. `app/static/css/gallery.css`、`app/static/css/config.css`、`app/static/css/model.css`（页面级适配）
4. `app/templates/gallery.html`、`app/templates/config.html`、`app/templates/model.html`（按钮位置与脚本引入）

## 4. 快速排障流程（建议顺序）

1. 先判断页面模式：
   - `/v2/files/...`（在线）
   - `/files/.../index.html`（本地服务离线）
   - `file://`（文件直开）
2. 浏览器悬停“下载/打印”按钮，确认实际链接是否符合预期。
3. 若页面逻辑看起来“没生效”，先强刷（`Ctrl+F5`）再测。
4. 若是历史归档页，执行 `POST /api/archive/rebuild-pages` 后再测。
5. 若接口仍 404，检查对应模型 `instances/` 目录真实文件名与 `meta.json` 的 `instances[*]`。

## 5. 当前状态备注

- 当前项目未启用独立 `app/tg_push.py`（文件不存在）。
- 若后续恢复 Telegram 推送，请在本文件补充“配置字段 + 触发时机 + 接口入口”。
