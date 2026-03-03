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
- 每次更新必须同步修改 `app/templates/config.html` 中的版本号:
  ```html
  <span class="version">vX.X</span>
  ```
- 大版本号（如 v5.0 → v6.0）用于重大功能更新或架构变更
- 小版本号（如 v5.0 → v5.1）用于功能新增或较大的修复

### 版本更新日志
- 每次大的更新在 `doc/logs/` 目录下创建版本更新日志文件
  - 文件命名: `vX.X_update_log.md`
  - 内容: 包含详细的技术变更内容、涉及文件、改动细节
- 同时在根目录 `README.md` 中:
  - 更新"当前版本"区块的版本号和日期
  - 添加对应的更新日志链接
  - 写一段面向用户的简洁更新说明

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
