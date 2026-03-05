# MakerWorld Archive 项目开发规则

## 技术栈
- **后端**: Python 3.10+ / FastAPI / Uvicorn
- **前端**: 原生 HTML + CSS + JavaScript（无框架）
- **样式**: 使用 `static/css/variables.css` 中定义的 CSS 变量，所有颜色、字号、间距等必须引用变量
- **浏览器插件**: Chrome Extension (Manifest V3) + Tampermonkey 油猴脚本
- **包管理**: pip / requirements.txt

## 项目结构约定
```
mw_archive/
├─ app/                    # 后端服务（FastAPI 应用）
│  ├─ server.py            # 主服务入口与 API 路由
│  ├─ archiver.py          # 归档核心逻辑
│  ├─ three_mf_parser.py   # 3MF 文件解析
│  ├─ config.json           # 运行时配置
│  ├─ cookie.txt            # Cookie 持久化文件
│  ├─ static/              # 前端静态资源 (css/js/imgs)
│  ├─ templates/           # HTML 模板
│  ├─ data/                # 归档数据目录（运行时产生，不入库）
│  └─ logs/                # 日志目录（运行时产生，不入库）
├─ plugin/                 # 浏览器插件
│  ├─ chrome_extension/    # Chrome 扩展
│  └─ tampermonkey/        # 油猴脚本
├─ scripts/                # 维护脚本（补丁、重建索引等）
├─ doc/                    # 项目文档
│  ├─ readme.md            # 项目说明文档
│     └─ api.md               # API 接口文档
│  ├─ logs/                # 版本更新日志
│  ├─ archives/            # 存档文档
│  └─ screenshot/          # 截图
└─ README.md
```

## 代码风格
- Python: 遵循 PEP 8，函数和变量使用 `snake_case`，类使用 `PascalCase`
- JavaScript: 函数使用 `camelCase`，常量使用 `UPPER_SNAKE_CASE`
- HTML/CSS: class 命名采用 `kebab-case`，组件级前缀（如 `manual-`、`config-`）
- 所有文件使用 UTF-8 编码
- 中文注释优先，关键逻辑必须写注释
- 脚本规范（适用于 `.sh` / `.ps1` / `.py` 等脚本文件）：
  - 脚本顶部必须包含“脚本说明”（用途、输入参数、执行流程/注意事项）
  - 脚本内部必须添加详细中文注释，说明关键步骤、分支逻辑和异常处理意图

## 开发流程规则
- 修改代码前，必须先阅读 `.agents/dev_logic_map.md` 中的代码逻辑说明，确认改动入口与影响范围
- 代码修改完成后，必须同步更新 `.agents/dev_logic_map.md`，补充或修正对应逻辑说明，保证文档与代码一致
- 需求协作流程约定：
  - 统一在 `doc/plan/` 记录需求，必须使用 `doc/plan/README.md` 内的标准模板
  - 每个需求使用独立文件：`REQ-YYYYMMDD-序号.md`
  - 需求文档必须包含三段：
    - 用户需求记录（原始描述 + 初步思路）
    - AI 分析（实现难度 / 实现思路 / 大体改动内容）
    - AI 实现记录（实际改动与验证）
  - 当用户只给需求描述时，先由 AI 新建需求文档并补全“需求记录 + AI分析”
  - 用户后续补充后，AI 按指定需求编号读取文档并执行开发，完成后回写“AI实现记录”
- Bug 协作流程约定：
  - 统一在 `doc/bugs/` 记录 Bug，必须使用 `doc/bugs/README.md` 内的标准模板
  - 状态字段统一使用 emoji 标记：`🟡 待确认`、`🛠️ 处理中`、`🧪 待验证`、`✅ 已解决`、`⚪ 已关闭`
  - 每个 Bug 使用独立文件：`BUG-YYYYMMDD-序号.md`
  - `doc/bugs/README.md` 的“当前 Bug 列表”索引必须使用“编号 + 标题”格式，便于快速检索
  - 当用户仅提供问题描述时，先由 AI 按模板新增独立 Bug 文档并分配 Bug 编号
  - 用户后续补充细节后，AI 仅根据指定 Bug 编号进行定位、修复与状态更新
  - 修复完成后，必须回写对应 Bug 文档：更新状态、解决时间、修复记录、验证记录
- 版本日志协作流程约定：
  - 统一在 `doc/logs/` 记录发布日志，必须使用 `doc/logs/README.md` 内置模板
  - 每个版本使用独立文件：`vX.Y.Z_update_log.md`
  - `doc/logs/README.md` 维护日志说明、模板入口和日志索引
  - 每次同步根 `README.md` 的「## 当前版本」后，必须在 `doc/logs/README.md` 的“README 当前版本同步记录”中增加一条记录

## 前端开发规范
- 不使用前端框架，保持原生 HTML/CSS/JS
- CSS 变量统一定义在 `static/css/variables.css`，禁止在组件中硬编码颜色值
- 公共样式放 `components.css`，页面专属样式单独文件（如 `config.css`、`model.css`）
- JS 资源文件引入时带版本号参数，如 `?v=5.2`，更新时同步修改

## API 开发规范
- 所有 API 路由定义在 `server.py`
- API 路径统一以 `/api/` 开头
- 请求体使用 JSON（`application/json`），文件上传使用 `multipart/form-data`
- 错误响应使用 FastAPI 的 `HTTPException`
- 新增或修改 API 后，同步更新 `doc/api.md` 文档

## 版本管理规则

### 版本号更新
- 版本号唯一来源为 `app/version.yml`，禁止手动分散修改各文件版本号
- 版本字段说明:
  - `project_version`: 项目主版本（用于 README、配置页展示、发布 tag）
  - `tampermonkey_version`: 油猴脚本版本（同步到 `@version`）
  - `chrome_extension_version`: Chrome 扩展版本（同步到 `manifest.json`）
- 每次版本更新后，必须执行:
  ```bash
  python3 scripts/sync_version.py
  ```
- `scripts/sync_version.py` 负责把 `app/version.yml` 同步到以下文件:
  - `README.md`（当前版本）
  - `plugin/tampermonkey/mw_quick_archive.user.js`（`@version`）
  - `plugin/chrome_extension/mw_quick_archive_ext/manifest.json`（`version`）
- 配置页版本展示说明：
  - `/config` 页面版本由后端在渲染时从 `app/version.yml` 读取（不再由 `sync_version.py` 替换 `config.html`）
- 大版本号（如 v5.0 → v6.0）用于重大功能更新或架构变更
- 小版本号（如 v5.0 → v5.1）用于功能新增或较大的修复
- 补丁版本号（如 v5.1 → v5.1.1）用于兼容性修复、文案优化、界面微调等不改变整体架构的更新
- 版本统一使用三段式版本号（`vX.Y.Z`）

### 版本更新日志
- 每次大的更新在 `doc/logs/` 目录下创建版本更新日志文件
  - 文件命名: `vX.X.X_update_log.md`
  - 内容: 包含详细的技术变更内容、涉及文件、改动细节
- `doc/logs/` 目录维护要求:
  - `README.md`：说明、标准模板、日志索引、README 当前版本同步记录
- 索引可读性要求：
  - `doc/bugs/README.md` 与 `doc/plan/README.md` 的列表索引均需包含“编号 + 标题”
- 同时在根目录 `README.md` 中:
  - 更新"当前版本"区块内容（由 `sync_version.py` 同步版本号）
  - 添加对应的更新日志链接
  - 写一段面向用户的简洁更新说明
- GitHub Release 正文来自 `README.md` 的 `## 当前版本` 区块（由工作流自动提取）

### 发布流程（标准）
1. 功能开发完成
2. 人工确认要发布的版本号（修改 `app/version.yml`）
3. AI 负责:
   - 总结本次更新内容
   - 更新/创建 `doc/logs/vX.X.X_update_log.md`
   - 同步根 `README.md` 的「## 当前版本」（版本号、日志链接、重点说明）
   - 在 `doc/logs/README.md` 的“README 当前版本同步记录”追加一条记录
   - 运行 `scripts/sync_version.py` 同步版本到项目文件
   - 输出改动清单供人工确认（不自动执行 git commit）
4. 用户手动执行:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\release_tag.ps1
   ```
   或（Git Bash / Linux / macOS）:
   ```bash
   bash ./scripts/release_tag.sh
   ```
5. 发布脚本负责 tag 与 push；推送 `v*` tag 后，GitHub Actions 自动创建 Release

### 更新日志模板
```markdown
# vX.X 更新日志

> 更新日期: YYYY-MM-DD

## 更新概述
简要描述本次更新的主要内容

## 详细变更

### 新增功能
- ...

### 优化改进
- ...

### Bug 修复
- ...

## 涉及文件
- `path/to/file` — 变更说明
```

## Git 规范
- 提交信息使用中文，格式: `类型: 简述`
  - 类型: `feat`(新功能) / `fix`(修复) / `docs`(文档) / `style`(样式) / `refactor`(重构) / `chore`(杂项)
- `data/`、`logs/`、`cookie.txt`、`__pycache__/`、`.venv/` 不入库

## 安全注意事项
- `model_dir` 路径参数必须校验，禁止路径穿越
- Cookie 文件和 `config.json` 中不存储敏感信息到版本库
- 上传文件需校验类型和大小
