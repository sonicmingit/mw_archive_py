# MakerWorld 本地归档小应用

一键采集 MakerWorld 模型，落地 meta/index 及图片/3MF，本地浏览与归档复用。

## 亮点
- 全文件化存储：每个模型独立 `MW_<id>_<title>/`，包含 `meta.json`、`index.html`、`images/`、`instances/`
- 稳定实例下载路径：实例 3MF 固定为 `./instances/<实例标题>.3mf`，重试或补下无需再次改页面
- 缺失 3MF 追踪与补救：自动记录 `logs/missing_3mf.log`，支持列表重试、实例重下、模型重下
- Cookie/目录在线配置，实时日志回显
- Docker 支持，开箱运行

## 目录结构
```
mw_archive/
├─ app/                  # 主程序（Docker 仅复制此目录）
│  ├─ archiver.py        # 采集/归档核心
│  ├─ server.py          # FastAPI 入口
│  ├─ config.json        # 默认 ./data ./logs ./cookie.txt
│  ├─ cookie.txt         # 当前 Cookie（可挂载覆盖）
│  ├─ requirements.txt   # 依赖
│  ├─ templates/         # 前端页面（gallery/config）
│  ├─ imgs/              # 前端资源
│  ├─ data/              # 归档输出（建议挂载）
│  └─ logs/              # 运行日志、缺失记录（建议挂载）
├─ others/               # 历史资料
│  ├─ tampermonkey/      # 旧油猴脚本
│  ├─ mw_fetch/          # 单文件 Python 采集脚本
│  └─ index_only/        # 单页面导航/示例
├─ Dockerfile            # 基于 app/ 构建镜像
├─ docker_build.sh       # 简单构建脚本
├─ .gitignore
└─ README.md
```

## 快速启动（本地）
```bash
cd app
python -m venv .venv
. .venv/Scripts/activate  # Windows
pip install -r requirements.txt
python server.py  # 默认 0.0.0.0:8000
```
浏览器打开：http://localhost:8000 （模型库）或 http://localhost:8000/config （配置/归档）。

## 使用指引
1) 配置 Cookie：在 `/config` 粘贴完整 Cookie（含 cf_clearance 等），或 `POST /api/cookie`。  
2) 归档模型：输入模型链接或调用 `POST /api/archive`，生成本地页面与实例文件。  
3) 缺失 3MF 处理：在 `/config` 查看缺失记录，可用 `POST /api/logs/missing-3mf/redownload` 批量补下；也可用 `POST /api/instances/{inst_id}/redownload` 针对单实例，或 `POST /api/models/{model_id}/redownload` 针对某模型目录。  
4) 本地浏览：`/` 扫描 `data/` 下模型目录，点击卡片打开本地 `index.html`。

## API
- `POST /api/cookie`  `{ "cookie": "..." }` → 写入 cookie.txt
- `POST /api/archive` `{ "url": "模型地址" }` → 归档模型，返回 `{status, base_name, work_dir, missing_3mf}`
- `GET /api/config` → 下载目录/日志目录/cookie 文件与更新时间
- `GET /api/logs/missing-3mf` → 缺失 3MF 记录列表
- `POST /api/logs/missing-3mf/redownload` → 读取缺失记录，用最新 Cookie 重新获取下载地址并补下 3MF
- `POST /api/instances/{inst_id}/redownload` → 指定实例 ID，扫描已下载模型，重新获取原始下载地址并覆盖本地文件
- `POST /api/models/{model_id}/redownload` → 指定模型 ID（目录 `MW_{id}_*`），遍历该模型全部实例 `apiUrl` 重新下载
- `GET /api/gallery` → 扫描下载目录下 `MW_*/meta.json`，返回模型简表

## 前端
- `/config`：配置 Cookie、显示下载/日志目录，输入模型链接一键归档，实时日志，缺失 3MF 列表，重试下载按钮
- `/`：模型库卡片视图，基于下载目录下的 meta.json，支持搜索与点击打开本地页面

## 缺失 3MF 记录
- 采集阶段若实例未拿到 downloadUrl，则写入 `logs/missing_3mf.log`，状态默认 `cookie失效`
- 重试成功会更新 `meta.json`、下载到 `instances/`，并清理对应缺失记录

## Docker 部署
```bash
# 在项目根目录（包含 Dockerfile 和 app/）
docker build -t mw-archiver:latest .
docker run -d \
  -p 8000:8000 \
  -v $PWD/app/data:/app/data \
  -v $PWD/app/logs:/app/logs \
  -v $PWD/app/cookie.txt:/app/cookie.txt \
  --name mw-archiver mw-archiver
```
- 如需自定义下载/日志目录，修改 `app/config.json`，并相应调整挂载路径

## 更新日志
- 2025-12-11 v2.1
  - 新增 `POST /api/models/{model_id}/redownload`，按目录 ID 批量重下模型内全部实例
  - 实例下载路径固定为 `./instances/<实例标题>.3mf`，补下文件无需改页面
  - 缺失 3MF 重试与实例/模型级重下共用最新 Cookie，成功后自动清理缺失记录
- 2025-12-10 v2.0
  - 支持缺失记录批量重试接口 `POST /api/logs/missing-3mf/redownload`
  - 增加实例级重下接口 `POST /api/instances/{inst_id}/redownload`
- 2025-12-09 v1.0
  - 初始版本：采集归档、生成本地页面、模型库/配置前端、Docker 支持


## 待开发

- [ ] 型库页面优化,添加分类/标签/首页详细信息/分页等功能;
- [ ] 优化配置页