# 本地模型管理工具 开发快速定位手册

> 目的：后续修改时先读本文件，快速定位代码入口与逻辑分层，避免反复全量扫描。
> 适用版本：v5.3（当前代码状态）

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
  - 配置目录统一为 `app/config/`
  - 运行时配置文件：`app/config/config.json`
  - 画廊状态文件：`app/config/gallery_flags.json`
  - Cookie 存储文件：`app/config/cookie.json`
  - 若新路径文件不存在，会优先尝试从旧路径迁移：
    - `app/config.json`
    - `app/gallery_flags.json`
    - `app/cookie.txt`
  - `app/config/config.json` 保留用户写的相对路径（不会因打开配置页而回写为绝对路径）
  - 运行时返回绝对路径给程序使用
  - Docker 若只挂载空的 `app/config/` 目录，服务启动后会自动生成：
    - `config.json`
    - `gallery_flags.json`
    - `cookie.json`
- 相关接口：
  - `GET /api/config`
  - `GET /config`（模板渲染）
- 版本展示规则：
  - `/config` 页面版本由 `server.py` 读取 `app/version.yml` 的 `project_version` 注入模板
  - 版本文件查找顺序：
    1. `app/version.yml`
  - `app/templates/config.html` 内使用模板变量 `project_version` / `project_version_short`

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

- Telegram 推送与命令交互已接入：
  - 模块：`app/tg_push.py`
  - 统一通知分发：`app/notify_dispatcher.py`
  - 配置来源：`app/config/config.json -> notifications.telegram`
  - 配置接口：`GET/POST /api/notify-config`
  - 触发点：`POST /api/archive` 成功推送、失败/限流/Cookie 异常告警
  - 命令支持：`/help`、`/cookies`、`/count`、`/search 关键词`、发送模型链接触发归档
  - 成功消息地址：使用 `notifications.telegram.web_base_url + /v2/files/{model_dir}`
  - 线程启停规则：
    - 启动入口：`app/server.py -> sync_telegram_service_state()`
    - 实际由 `NotificationDispatcher.start()` 分发到已注册渠道
    - `startup` 时不再无条件启动轮询线程，而是由 `TelegramPushService.should_run()` 判断
    - 当前判断条件：`enable_push = true` 且 `bot_token` 非空
    - 保存 `/api/notify-config` 后会立即同步启停线程，无需重启服务
  - 排障重点：
    - 若 Telegram 开关关闭，项目启动时不应出现“Telegram 命令轮询线程已启动”
    - 若看到相同日志重复输出，优先检查 `app/server.py` 的 logger handler 是否重复挂载
- Cookie 存储当前为 JSON 结构：
  - 文件：`app/config/cookie.json`
  - 结构：
    - `{"cn": [{"value":"...","status":"active"}], "global": [...], "_meta": {"rr_index": {"cn": 0, "global": 0}}}`
  - 旧 `app/cookie.txt` 会在首次启动时迁移为 `cn[0]`
  - 现阶段 `read_cookie(CFG)` 默认仍取指定平台的第一个 Cookie，保持旧接口兼容
  - 平台识别：
    - `makerworld.com.cn` -> `cn`
    - `makerworld.com` -> `global`
  - 关键后端函数：
    - `detect_cookie_platform()`
    - `build_cookie_candidate_order()`
    - `run_with_cookie_failover()`
    - `mark_cookie_result()`
  - 状态切换：
    - `401/403/Cloudflare` -> `invalid`
    - `429` -> `cooldown`
    - 成功请求 -> `active`
    - 冷却超时后自动恢复 `active`
  - 多 Cookie 开关：
    - 来源：`app/version.yml -> multi_cookie_enabled`
    - 关闭时仅使用各平台第一个 Cookie
    - 开启时配置页展示“添加 Cookie”按钮，后端启用轮询切换
  - `POST /api/cookie` 已兼容：
    - 旧写法：`{"cookie": "..."}`
    - 新写法：`{"platform":"cn","cookies":["a","b"]}`
  - 新接口：
    - `GET /api/cookies`
    - `POST /api/cookies`
  - 配置页：
    - 不再展示下载目录、日志目录
    - 不再提供独立“测试可用性”按钮
    - Cookie 状态仅基于真实归档 / 补下载 / 重下载链路更新，避免站点主页 403 造成误判
    - 多 Cookie 关闭时标题显示为 `Cookie`，开启时才显示 `Cookie 1/2/...`
  - Telegram 告警规则：
    - 归档入口异常不再直接发送“Cookie 失效告警”
    - 仅真实模型下载失败相关链路发送 Cookie 告警：
      - 初次归档出现 `missing_3mf`
      - 缺失 3MF 重试
      - 实例重下
      - 模型重下
    - 告警内容包含平台与 Cookie 序号
    - 告警格式统一为：
      - 标题
      - 摘要
      - 平台
      - Cookie 序号
      - 状态
      - 说明
      - 错误/建议
  - 业务代码不再直接调用 `TG_SERVICE.notify_*`
    - 统一走 `NOTIFIER.notify_success(...)`
    - 统一走 `NOTIFIER.notify_alert(...)`
    - 后续新增企微等渠道时，只需注册到 `NotificationDispatcher`


