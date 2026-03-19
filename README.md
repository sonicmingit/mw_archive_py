# 3D打印本地模型管理工具

![mw_archive](https://aliyun-wb-h9vflo19he.oss-cn-shanghai.aliyuncs.com/use/makerworld_archive.png)

一个面向本地模型管理的工具，支持模型归档、本地 3MF 解析导入、模型库浏览与维护。

## 当前版本
- `v5.6.0`
- 更新说明见 [doc/logs/v5.6.0_update_log.md](doc/logs/v5.6.0_update_log.md)
- 本次重点：
  - 首页图库列表改为读取索引，模型数量多时后续加载速度显著提升；
  - 新增图库“刷新索引”入口，支持手动全量重建首页列表索引；
  - 归档、手动导入、批量导入、编辑、删除后会自动增量更新索引；
  - 首次打开图库或首次重建索引时会扫描历史数据，可能比后续加载稍慢。
- 升级提醒：
  - 升级到 `v5.6.0` 后，首次进入首页会自动建立 `app/config/gallery_index.json`；
  - 首次建立索引可能较慢，属于预期行为，后续首页加载会明显提速。

## 核心能力
- 支持本地上传 3MF 后自动解析并入库，快速建立个人模型库
- 支持本地 `3MF` 目录批量导入，自动识别同模型不同配置并聚合到同一个 `LocalModel_*`
- 支持监控目录定时扫描，自动移动已处理文件并输出批量导入汇总
- 支持固定目录一键整理本地 `3MF` 文件，按模型归类、按配置重命名，并分离重复文件
- 支持模型库浏览、搜索、筛选与状态标记（如收藏、已打印）
- 支持首页图库索引缓存与手动全量重建，减少大模型库下的列表等待时间
- 支持手动导入本地模型与附件管理，便于整理历史文件
- 支持缺失文件记录与重试机制，降低导入失败后的手工处理成本
- 支持从归档模型、图片、实例 3MF、说明等内容到本地
- 支持一键重建历史归档页面，版本升级后同步旧数据展示效果
- 支持 Telegram 成功通知、失败告警与机器人链接归档
- 支持 Telegram 命令重试缺失 3MF 下载
- 支持国内 / 国际平台分别配置 Cookie

## 项目结构
```text
mw_archive/
├─ app/
│  ├─ archiver.py
│  ├─ server.py
│  ├─ tg_push.py
│  ├─ notify_dispatcher.py
│  ├─ config/
│  │  ├─ config.json
│  │  ├─ cookie.json
│  │  ├─ gallery_flags.json
│  │  ├─ gallery_index.json
│  │  └─ local_batch_import_state.json
│  ├─ data/
│  ├─ logs/
│  ├─ organize/
│  ├─ static/
│  ├─ templates/
│  └─ watch/
├─ plugin/
│  ├─ chrome_extension/
│  │  ├─ mw_quick_archive_ext/
│  │  └─ 使用说明.md
│  └─ tampermonkey/
│     ├─ mw_quick_archive.user.js
│     └─ 使用说明.md
├─ scripts/
├─ doc/
├─ Dockerfile
├─ docker_build.sh
└─ update.sh
```

## 页面
![主页](doc/screenshot/主页.png)
![模型详情](doc/screenshot/模型详情.png)

## 运行环境
- Python `3.10+`（建议 `3.11`）
- 依赖见 [app/requirements.txt](app/requirements.txt)
- 可选：Docker

## 本地启动
```bash
cd app
python -m venv .venv
# Windows
. .venv/Scripts/activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

默认地址：
- 模型库：`http://127.0.0.1:8000/`
- 配置页：`http://127.0.0.1:8000/config`

## Docker 启动
推荐先在宿主机创建目录：
- `app/data`
- `app/logs`
- `app/config`
- `app/watch`
- `app/organize`

注意：
- `app/config` 现在是推荐挂载项；
- 即使这个目录是空的，容器首次启动后也会自动生成默认配置文件；
- `app/watch` 用于本地批量导入监控目录，推荐单独挂载到宿主机；
- `app/organize` 用于本地 3MF 整理目录，推荐单独挂载到宿主机；

### 直接拉取
```bash

 docker run -d \
  --name mw-archiver \
  -p 8000:8000 \
  -v $PWD/app/data:/app/data \
  -v $PWD/app/logs:/app/logs \
  -v $PWD/app/config:/app/config \
  -v $PWD/app/watch:/app/watch \
  -v $PWD/app/organize:/app/organize \
  sonicming/mw-archiver:latest
```

如果网络问题可以更换镜像源 `docker.1ms.run/sonicming/mw-archiver:latest`

### 本地构建
```bash
bash docker_build.sh

docker run -d \
  --name mw-archiver \
  -p 8000:8000 \
  -v $PWD/app/data:/app/data \
  -v $PWD/app/logs:/app/logs \
  -v $PWD/app/config:/app/config \
  -v $PWD/app/watch:/app/watch \
  -v $PWD/app/organize:/app/organize \
  mw-archiver
```

### Docker 参数详细说明
- `-d`：后台运行容器。
- `--name mw-archiver`：为容器指定名称，便于 `docker logs`、`docker stop` 管理。
- `-p 8000:8000`：映射容器 `8000` 端口到宿主机 `8000`。
- `-v $PWD/app/data:/app/data`：持久化归档数据目录。
- `-v $PWD/app/logs:/app/logs`：持久化日志目录，便于排查失败、缺失下载等问题。
- `-v $PWD/app/config:/app/config`：持久化配置目录，保存通知配置、Cookie 配置、模型库状态配置。空目录也可自动初始化。
- `-v $PWD/app/watch:/app/watch`：持久化本地批量导入监控目录，适合宿主机直接投放 `3MF` 文件。
- `-v $PWD/app/organize:/app/organize`：持久化本地 3MF 整理目录，适合配置页点击“开始整理”后统一处理。
- `sonicming/mw-archiver:latest`：使用的镜像及版本标签。

## Docker Compose 启动
创建 `docker-compose.yml` 文件：

```yaml
version: '3.8'

services:
  mw-archiver:
    image: sonicming/mw-archiver:latest
    container_name: mw-archiver
    ports:
      - "8000:8000"
    volumes:
      - ./app/data:/app/data
      - ./app/logs:/app/logs
      - ./app/config:/app/config
      - ./app/watch:/app/watch
      - ./app/organize:/app/organize
    restart: unless-stopped
```

然后执行：

```bash
docker-compose up -d
```

## 配置说明
### 配置文件
一般不用手动修改，程序会自动维护。

当前配置目录：`app/config/`

主要文件：
- [app/config/config.json](app/config/config.json)
- [app/config/cookie.json](app/config/cookie.json)
- [app/config/gallery_flags.json](app/config/gallery_flags.json)
- [app/config/local_batch_import_state.json](app/config/local_batch_import_state.json)
- `app/config/local_3mf_organizer_state.json`（运行后自动生成）

`config.json` 示例：

```json
{
  "download_dir": "./data",
  "cookie_file": "./config/cookie.json",
  "logs_dir": "./logs",
  "local_batch_import": {
    "enabled": false,
    "watch_dirs": ["./watch"],
    "processed_dir_name": "_imported",
    "failed_dir_name": "_failed",
    "scan_interval_seconds": 300,
    "max_parse_workers": 2,
    "notify_on_finish": true,
    "duplicate_policy": "skip"
  },
  "local_3mf_organizer": {
    "root_dir": "./organize",
    "mode": "move"
  },
  "notifications": {
    "telegram": {
      "enable_push": false,
      "bot_token": "",
      "chat_id": "",
      "web_base_url": "http://127.0.0.1:8000"
    },
    "wecom": {
      "enable_push": false,
      "enable_command": false
    }
  }
}
```

### 本地批量导入
- 监控目录默认是 `app/watch/`
- 只处理本地导入模型，生成或更新 `LocalModel_*`
- 不会和在线归档 `MW_*` 混合
- 导入成功或判重跳过后，源文件会移动到 `watch/_imported/`
- 导入失败后，源文件会移动到 `watch/_failed/`
- 移动完成后会自动清理原路径上的空文件夹
- 配置页会显示：
  - 最新扫描记录
  - 最近 5 次成功记录
  - 每次处理的耗时、处理数量、成功 / 跳过 / 失败统计
- 推送标题区分：
  - 监控目录导入完成
  - 手动目录导入完成

推荐使用方式：
- 少量文件：手动导入弹窗里直接“选择目录批量导入”
- 大量文件：先把文件放进 `watch` 目录，再到配置页手动点击“立即扫描并导入”
- 如果是 Docker 部署，推荐把宿主机目录映射到 `app/watch`

### 本地 3MF 整理
- 固定整理目录默认是 `app/organize/`
- 入口在配置页“其他功能”中的“本地 3MF 整理”
- 配置项包括：
  - 整理目录
  - 处理模式：`move` / `copy`
- 点击“开始整理”后会在目标目录下自动生成：
  - `整理完成/`
  - `重复文件/`
  - `整理失败/`
  - `整理报告/`
- 模型目录命名规则：
  - 有 `DesignModelId`：`MW_<作者名>_<模型名>`
  - 无 `DesignModelId`：`Others_<作者名>_<模型名>`
  - 若缺少作者信息，则不拼接作者段
- 配置文件命名优先使用 `ProfileTitle`，若标题过弱则回退到原始文件名
- 配置页会显示最近一次整理记录、耗时和最近报告路径
- Docker 部署时建议把宿主机目录映射到 `app/organize`

### 国内 / 国际平台 Cookie
`cookie.json` 当前按平台分组：

```json
{
  "cn": [],
  "global": [],
  "_meta": {
    "rr_index": {
      "cn": 0,
      "global": 0
    }
  }
}
```

### 完整 Cookie 获取
随便打开一个模型，按 `F12`，选择 `Network`，然后刷新页面，找到请求，复制完整 `Cookie`。

![cookie](doc/screenshot/完整cookie获取.png)

### Tampermonkey 油猴脚本
- 说明文档：[plugin/tampermonkey/使用说明.md](plugin/tampermonkey/使用说明.md)
- 当前菜单项包括：
  - `⚙️ 设置后端地址与手动 Cookie`
  - `归档当前模型`
  - `重新下载缺失 3MF 文件`
  - `🍪 手动 Cookie 同步到后端`

### Telegram 机器人命令
- `/help`：查看命令说明
- `/cookies`：查看当前 Cookie 状态
- `/count`：查看已归档模型数
- `/search 关键词`：搜索本地模型
- `/url`：查看在线地址前缀
- `/seturl 地址`：设置在线地址前缀
- `/redl`：重新下载缺失的 3MF 文件

**Cookie 失效问题：**
有时候 Cookie 并不是真的失效，而是触发了验证，需要先手动下载一个模型完成验证。

![cookie手动验证](doc/screenshot/cookie手动验证.png)

之后尽快在控制台重新下载模型：

![重新下载](doc/screenshot/重新下载.png)

## 常用流程
1. 在 `/config` 设置国内 / 国际平台 Cookie 与通知配置。
2. 在 `配置/模型归档` 页面输入模型链接执行归档，或通过 Telegram 发送模型链接触发归档。
3. 如果要批量导入本地文件：
   - 少量文件可在手动导入弹窗中选择目录直接导入
   - 大量文件建议先放到 `watch` 目录，再到配置页点击“立即扫描并导入”
4. 若同模型再次归档，系统自动执行更新。
5. 归档历史样式升级时，点击“其他功能”中的“一键更新历史归档”。
6. 在 `/` 模型库查看、筛选、标记和打开本地模型页面。

注：为减少触发验证，目前同一时间仍建议一次归档一个模型。

## API 清单
> 详细的接口、传参示例和返回说明，请参见完整的 [API 接口文档 (doc/api.md)](doc/readme/api.md)

## 插件说明
Chrome 插件：
- 一键归档
- 目录：`plugin/chrome_extension/mw_quick_archive_ext`
- 说明：[plugin/chrome_extension/使用说明.md](plugin/chrome_extension/使用说明.md)

油猴脚本：
- 一键归档
- 文件：`plugin/tampermonkey/mw_quick_archive.user.js`
- 说明：[plugin/tampermonkey/使用说明.md](plugin/tampermonkey/使用说明.md)
- 直接安装插件地址 [地址](https://github.com/sonicmingit/mw_archive_py/raw/refs/heads/main/plugin/tampermonkey/mw_quick_archive.user.js)

## 文档目录
- [api.md (API 接口文档)](doc/readme/api.md)
- [meta.json 字段说明](doc/readme/meta_json_fields.md)
- [Bug 跟踪说明与模板](doc/bugs/README.md)
- [需求开发记录说明与模板](doc/plan/README.md)
- [版本日志说明与模板索引](doc/logs/README.md)
- [update.sh 使用说明](doc/readme/update_sh_usage.md)
- [项目架构与功能文档.md](doc/archives项目架构与功能文档.md)

## License
本项目采用 [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) 开源协议。
