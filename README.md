# 3D打印本地模型管理工具

![mw_archive](https://aliyun-wb-h9vflo19he.oss-cn-shanghai.aliyuncs.com/use/makerworld_archive.png)

一个面向本地模型管理的工具，支持 MakerWorld 模型归档、本地 3MF 解析导入、模型库浏览与维护。

## 当前版本
- `v5.3`
- 更新说明见 [doc/logs/v5.3_update_log.md](doc/logs/v5.3_update_log.md)
- 本次重点：
  - 新增 Telegram 推送与机器人交互；
  - 新增国内 / 国际平台 Cookie 支持；
  - Docker 部署配置目录统一迁移到 `app/config/`。
  
### v5.3 Docker 升级注意事项
如果你是从旧版本 Docker 升级到 `v5.3`，重点注意这次配置结构已经变化：
- 旧版常见挂载：
  - `./app/cookie.txt:/app/cookie.txt`
  - `./app/config.json:/app/config.json`
- `v5.3` 推荐改为直接挂载整个配置目录：
  - `./app/config:/app/config`
- 新目录下的关键文件：
  - `app/config/config.json`
  - `app/config/cookie.json`
  - `app/config/gallery_flags.json`
- 升级前建议先备份：
  - `app/data/`
  - `app/logs/`
  - `app/config/` 或旧的 `app/config.json`、`app/cookie.txt`

### Docker 升级步骤（推荐）
1. 停止并删除旧容器。
2. 备份宿主机上的 `app/data`、`app/logs`、`app/config`（如果没有 `app/config`，就备份旧的 `app/config.json` 和 `app/cookie.txt`）。
3. 将挂载方式改为：
   - `./app/data:/app/data`
   - `./app/logs:/app/logs`
   - `./app/config:/app/config`
4. 启动新版本容器。
5. 首次启动后检查 `app/config/` 目录：如果为空，程序会自动生成默认配置文件；如果存在旧配置，程序会自动迁移到新目录。
6. 打开 `/config` 页面确认：
   - Cookie 是否正常显示；
   - Telegram 配置是否保留；
   - 国内 / 国际平台 Cookie 是否分组正常。

## 核心能力
- 支持本地上传 3MF 后自动解析并入库，快速建立个人模型库
- 支持模型库浏览、搜索、筛选与状态标记（如收藏、已打印）
- 支持手动导入本地模型与附件管理，便于整理历史文件
- 支持缺失文件记录与重试机制，降低导入失败后的手工处理成本
- 支持从归档模型、图片、实例 3MF、说明等内容到本地
- 支持一键重建历史归档页面，版本升级后同步旧数据展示效果
- 支持 Telegram 成功通知、失败告警与机器人链接归档
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
│  │  └─ gallery_flags.json
│  ├─ data/
│  ├─ logs/
│  ├─ static/
│  └─ templates/
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

注意：
- `app/config` 现在是推荐挂载项；
- 即使这个目录是空的，容器首次启动后也会自动生成默认配置文件；

### 直接拉取
```bash

 docker run -d \
  --name mw-archiver \
  -p 8000:8000 \
  -v $PWD/app/data:/app/data \
  -v $PWD/app/logs:/app/logs \
  -v $PWD/app/config:/app/config \
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
  mw-archiver
```

### Docker 参数详细说明
- `-d`：后台运行容器。
- `--name mw-archiver`：为容器指定名称，便于 `docker logs`、`docker stop` 管理。
- `-p 8000:8000`：映射容器 `8000` 端口到宿主机 `8000`。
- `-v $PWD/app/data:/app/data`：持久化归档数据目录。
- `-v $PWD/app/logs:/app/logs`：持久化日志目录，便于排查失败、缺失下载等问题。
- `-v $PWD/app/config:/app/config`：持久化配置目录，保存通知配置、Cookie 配置、模型库状态配置。空目录也可自动初始化。
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

`config.json` 示例：

```json
{
  "download_dir": "./data",
  "cookie_file": "./config/cookie.json",
  "logs_dir": "./logs",
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

说明：
- `cn` 用于 `makerworld.com.cn`
- `global` 用于 `makerworld.com`
- 当前 README 只强调“支持国内 / 国际平台分组配置”
- 多 Cookie 轮询能力由内部版本开关控制，默认关闭

### 完整 Cookie 获取
随便打开一个模型，按 `F12`，选择 `Network`，然后刷新页面，找到请求，复制完整 `Cookie`。

![cookie](doc/screenshot/完整cookie获取.png)

**Cookie 失效问题：**
有时候 Cookie 并不是真的失效，而是触发了验证，需要先手动下载一个模型完成验证。

![cookie手动验证](doc/screenshot/cookie手动验证.png)

之后尽快在控制台重新下载模型：

![重新下载](doc/screenshot/重新下载.png)

## 常用流程
1. 在 `/config` 设置国内 / 国际平台 Cookie 与通知配置。
2. 在 `/config` 输入模型链接执行归档，或通过 Telegram 发送模型链接触发归档。
3. 若同模型再次归档，系统自动执行更新。
4. 归档历史样式升级时，点击“其他功能”中的“一键更新历史归档”。
5. 在 `/` 模型库查看、筛选、标记和打开本地模型页面。

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

## 脚本说明
- `update.sh`：更新与部署编排脚本，支持 `git pull` 无更新时确认是否继续重部署。详细用法与“快速本地构建更新”配置见 [doc/readme/update_sh_usage.md](doc/readme/update_sh_usage.md)。
- `app/version.yml`：统一版本源（项目、油猴、Chrome 扩展版本）。
- `scripts/sync_version.py`：将 `app/version.yml` 的版本同步到项目文件。
- `scripts/release_tag.ps1`：一键执行“版本同步 -> commit -> 打 tag -> push”；推送 `v*` tag 后会由 GitHub Actions 自动创建 Release。
- `scripts/rebuild_index_from_meta.py`：根据 `meta.json` 重建归档页面（兼容场景）。

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
