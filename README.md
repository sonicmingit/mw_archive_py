# MakerWorld 本地归档小应用

![MakerWorld Archive](https://aliyun-wb-h9vflo19he.oss-cn-shanghai.aliyuncs.com/use/makerworld_archive.png)

一个用于归档 MakerWorld 模型到本地的项目，支持模型采集、离线页面生成、模型库浏览、缺失 3MF 重试，以及浏览器插件一键归档。

## 当前版本
- `v5.1`（2026-03-03）
- 更新说明见 [doc/logs/v5.1_update_log.md](doc/logs/v5.1_update_log.md)
- 本次重点：手动导入识别回显增强、打印配置改为弹窗识别保存、手动导入来源统一为“手动导入（LocalModel）”、导入编号改为 data 目录独立持久化。

## 核心能力
- 归档模型并落盘为独立目录：`MW_<id>_<title>/`
- 目录内包含：`meta.json`、`index.html`、`images/`、`instances/`
- 复用在线模板生成本地归档页，支持后续统一重建
- 同模型二次归档自动按“更新”处理，避免重复目录
- `meta.json` 增加 `update_time` 字段
- 配置页支持“更新已归档页面”（`/api/archive/rebuild-pages`）
- 缺失 3MF 记录与重试下载
- 模型库页面支持收藏、打印状态、手动导入、附件管理
- Chrome 插件与油猴脚本支持一键归档流程

## 项目结构
```text
mw_archive/
├─ app/
│  ├─ archiver.py
│  ├─ server.py
│  ├─ config.json
│  ├─ cookie.txt
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
在当前目录下，**先创建 `app/data`、`app/logs` 目录和 `app/cookie.txt` 空文件**

> 注: logs和cookie.txt不是必须的，可以不挂载

```bash
# 直接拉取
docker run -d \
  --name mw-archiver \
  -p 8000:8000 \
  -v $PWD/app/data:/app/data \
  -v $PWD/app/logs:/app/logs \
  -v $PWD/app/cookie.txt:/app/cookie.txt \
  sonicming/mw-archiver:latest
```

如果网络问题可以更换镜像源 `docker.1ms.run/sonicming/mw-archiver:latest`

```bash
# 本地构建
bash docker_build.sh

docker run -d \
  --name mw-archiver \
  -p 8000:8000 \
  -v $PWD/app/data:/app/data \
  -v $PWD/app/logs:/app/logs \
  -v $PWD/app/cookie.txt:/app/cookie.txt \
  mw-archiver
```

### Docker 参数详细说明

* **`-d`**：后台运行容器（detach 模式），容器启动后不会阻塞当前终端。
* **`--name mw-archiver`**：为容器指定一个自定义名称标识（即 `mw-archiver`），方便后续使用 `docker logs mw-archiver` 或 `docker stop mw-archiver` 进行管理。
* **`-p 8000:8000`**：端口映射，格式为 `宿主机端口:容器内端口`。将容器内部的 `8000` 端口映射给宿主机的 `8000` 端口，启动后即可通过 `http://localhost:8000` 访问网页服务。
* **`-v $PWD/app/data:/app/data`**：数据目录映射（Volume）。将宿主机当前目录下的 `app/data` 挂载到容器内的 `/app/data`，使得所有归档下载的模型（3MF 文件、图片等数据）持久化保存在宿主机中，**防止容器重启或重建时数据丢失**。
* **`-v $PWD/app/logs:/app/logs`**(非必须)：日志目录映射。将运行日志和错误信息（如缺失 3MF 的记录日志）保存到宿主机，方便排查使用。
* **`-v $PWD/app/cookie.txt:/app/cookie.txt`**(非必须)：Cookie 凭证文件映射。此文件用于 MakerWorld 下载模型所需的认证信息。挂载出来便于配置持久化（即使在网页后端自动更新或重写了它的内容，宿主机上的文件也会同步更新）。*[注意：在首次执行 docker run 之前，如果 `app/cookie.txt` 在宿主机不存在，可能会被 Docker 错误识别并创建为目录，可以先在本地执行 `touch app/cookie.txt` 创建空文件]*。
* **`sonicming/mw-archiver:latest`**：启动使用的 Docker 镜像名称以及对应的版本标签（latest）。

## Docker Compose 启动

创建 `docker-compose.yml` 文件：

> 注: logs和cookie.txt不是必须的，可以不挂载

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
      - ./app/cookie.txt:/app/cookie.txt
    restart: unless-stopped
```

在同级目录下，**确保已经创建了 `app/data`、`app/logs` 目录和 `app/cookie.txt` 空文件**，然后执行以下命令将服务放置在后台启动：

```bash
docker-compose up -d
```


## 配置说明
### 配置文件
一般不用修改

配置文件为 [app/config.json](app/config.json)：

```json
{
  "download_dir": "./data",
  "cookie_file": "./cookie.txt",
  "logs_dir": "./logs"
}
```

### 完整cookie获取
随便打开一个模型，按f12，选择network，然后刷新页面，找到请求，复制cookie

![cookie](doc/screenshot/完整cookie获取.png)


**cookie失效问题：**
有时候cookie并不是失效了，而是触发了验证，需要手动下载一个模型解决验证

![cookie手动验证](doc/screenshot/cookie手动验证.png)

之后尽快在控制台重新下载模型
![重新下载](doc/screenshot/重新下载.png)

## 常用流程
http://127.0.0.1:8000
1. 在 `/config` 设置 Cookie（或调用 `POST /api/cookie`）。
2. 在 `/config` 输入模型链接执行归档（或调用 `POST /api/archive`）。
3. 若同模型再次归档，系统自动执行更新。
4. 归档历史样式升级时，点击“更新已归档页面”或调用 `POST /api/archive/rebuild-pages`。
5. 在 `/` 模型库查看、筛选、标记和打开本地模型页面。

注: 为减少触发验证,目前只能一次归档一个模型.

## API 清单
> 详细的接口、传参示例和返回说明，请参见完整的 [API 接口文档 (doc/api.md)](doc/readme/api.md)

- `GET /api/config`
- `POST /api/cookie`
- `POST /api/archive`
- `POST /api/archive/rebuild-pages`
- `GET /api/logs/missing-3mf`
- `POST /api/logs/missing-3mf/redownload`
- `DELETE /api/logs/missing-3mf/{index}`
- `GET /api/bambu/download/{hex_path}.3mf`
- `POST /api/instances/{inst_id}/redownload`
- `POST /api/models/{model_id}/redownload`
- `GET /api/gallery`
- `GET /api/gallery/flags`
- `POST /api/gallery/flags`
- `POST /api/models/manual`
- `POST /api/models/{model_dir}/delete`
- `GET /api/models/{model_dir}/attachments`
- `POST /api/models/{model_dir}/attachments`
- `GET /api/models/{model_dir}/printed`
- `POST /api/models/{model_dir}/printed`
- `GET /v2/files/{model_dir}`
- `GET /api/v2/models/{model_dir}/meta`

## 插件说明
Chrome 插件：
- 一键归档，快速更新cookie
- 目录：`plugin/chrome_extension/mw_quick_archive_ext`
- 说明：[plugin/chrome_extension/使用说明.md](plugin/chrome_extension/使用说明.md)

油猴脚本：
- 一键归档，手动更新cookie
- 文件：`plugin/tampermonkey/mw_quick_archive.user.js`
- 说明：[plugin/tampermonkey/使用说明.md](plugin/tampermonkey/使用说明.md)

## 脚本说明
- `update.sh`：服务器更新部署脚本，支持 `git pull` 无更新时确认是否继续重部署。
- `scripts/rebuild_index_from_meta.py`：根据 `meta.json` 重建归档页面（兼容场景）。
- `scripts/patch_attachments.py`、`scripts/patch_printed.py`：历史数据补丁脚本。

## 文档目录
- [api.md (API 接口文档)](doc/readme/api.md)
- [v5.1_update_log.md](doc/logs/v5.1_update_log.md)
- [v5.0_update_log.md](doc/logs/v5.0_update_log.md)
- [v4.5_update_log.md](doc/logs/v4.5_update_log.md)
- [v4.0_update_log.md](doc/logs/v4.0_update_log.md)
- [项目架构与功能文档.md](doc/archives项目架构与功能文档.md)
