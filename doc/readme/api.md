# MakerWorld Archive - 后端 API 接口文档

本文档描述了 MakerWorld Archive 后端服务的主要 API 接口，包括模型归档、国内 / 国际平台 Cookie 配置、通知配置、画廊数据获取、历史归档维护、缺失文件重试以及手动导入等能力。

---

## 目录
1. [核心流程 API](#1-核心流程-api)
   - 1.1 [提交模型归档任务](#11-提交模型归档任务)
   - 1.2 [同步浏览器 Cookie（兼容接口）](#12-同步浏览器-cookie兼容接口)
   - 1.3 [国内 / 国际平台 Cookie 配置](#13-国内--国际平台-cookie-配置)
   - 1.4 [通知配置（Telegram）](#14-通知配置telegram)
   - 1.5 [获取运行配置](#15-获取运行配置)
2. [画廊及展示层 API](#2-画廊及展示层-api)
   - 2.1 [获取已归档模型列表](#21-获取已归档模型列表)
   - 2.2 [获取画廊标记状态](#22-获取画廊标记状态)
   - 2.3 [保存画廊标记状态](#23-保存画廊标记状态)
3. [模型管理与维护 API](#3-模型管理与维护-api)
   - 3.1 [重建归档静态页面](#31-重建归档静态页面)
   - 3.2 [删除模型](#32-删除模型)
   - 3.3 [获取/上传模型附件](#33-获取上传模型附件)
   - 3.4 [获取/上传模型实打图片](#34-获取上传模型实打图片)
   - 3.5 [按实例 ID 下载 3MF](#35-按实例-id-下载-3mf)
4. [手动导入与解析 API](#4-手动导入与解析-api)
   - 4.1 [解析本地 3MF 草稿](#41-解析本地-3mf-草稿)
   - 4.2 [提交手动导入模型](#42-提交手动导入模型)
   - 4.3 [删除手动导入草稿缓存](#43-删除手动导入草稿缓存)
   - 4.4 [草稿缓存丢弃（Beacon）](#44-草稿缓存丢弃beacon)
5. [重试与记录修补 API](#5-重试与记录修补-api)
   - 5.1 [获取缺失 3MF 文件的日志列表](#51-获取缺失-3mf-文件的日志列表)
   - 5.2 [批量重试下载缺失文件](#52-批量重试下载缺失文件)
   - 5.3 [针对单个模型/实例重试](#53-针对单个模型实例重试)
6. [配置文件路径说明](#6-配置文件路径说明)

---

## 1. 核心流程 API

### 1.1 提交模型归档任务
用于触发后端开始抓取并下载指定 MakerWorld 模型的全部文件和元数据。

- **URL:** `/api/archive`
- **Method:** `POST`
- **Content-Type:** `application/json`

**请求参数 (Body)：**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| url | string | 是 | MakerWorld 模型详情页完整 URL |

**请求示例：**
```json
{
  "url": "https://makerworld.com/zh/models/12345"
}
```

**响应示例：**
```json
{
  "status": "ok",
  "message": "归档任务已开始"
}
```

说明：
- 后端会根据链接域名自动选择国内或国际平台 Cookie。
- 通知成功/失败消息统一通过通知分发层发送，当前默认渠道为 Telegram。

### 1.2 同步浏览器 Cookie（兼容接口）
用于把当前浏览器 Cookie 同步到后端环境。当前版本推荐使用 `/api/cookies`，本接口保留为兼容入口。

- **URL:** `/api/cookie`
- **Method:** `POST`
- **Content-Type:** `application/json`

**请求参数 (Body)：**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| cookie | string | 是 | 浏览器导出的完整 Cookie 字符串 |
| platform | string | 否 | `cn` 或 `global`，默认 `cn` |
| append | bool | 否 | 是否追加到该平台列表末尾，默认 `false` |

**请求示例：**
```json
{
  "cookie": "sid=xxxxxx; cf_clearance=yyyyyy;",
  "platform": "cn",
  "append": false
}
```

**响应示例：**
```json
{
  "status": "ok",
  "message": "Cookie 同步成功"
}
```

### 1.3 国内 / 国际平台 Cookie 配置
用于读取和保存国内 / 国际平台 Cookie 列表及其运行状态。

- **读取 URL:** `/api/cookies` (Method: `GET`)
- **保存 URL:** `/api/cookies` (Method: `POST`)
- **Content-Type:** `application/json`

**GET 响应示例：**
```json
{
  "success": true,
  "multi_cookie_enabled": false,
  "cookies": {
    "cn": [
      {
        "value": "sid=xxxxxx; cf_clearance=yyyyyy;",
        "status": "active",
        "last_error": "",
        "cooldown_until": ""
      }
    ],
    "global": []
  }
}
```

**POST 请求示例（简写）：**
```json
{
  "cn": [
    "sid=xxxxxx; cf_clearance=yyyyyy;"
  ],
  "global": []
}
```

**POST 请求示例（完整结构）：**
```json
{
  "cookies": {
    "cn": [
      {
        "value": "sid=xxxxxx; cf_clearance=yyyyyy;",
        "status": "active"
      }
    ],
    "global": []
  }
}
```

**响应示例：**
```json
{
  "success": true
}
```

说明：
- 国内链接 `makerworld.com.cn` 使用 `cn`。
- 国际链接 `makerworld.com` 使用 `global`。
- Cookie 状态仅在真实归档 / 补下载 / 重下载链路中更新，不提供独立测试接口。
- 当前状态值：`active`、`cooldown`、`invalid`。
- `multi_cookie_enabled` 由 `app/version.yml` 控制页面是否开放多条输入。

### 1.4 通知配置（Telegram）
用于读取和保存 Telegram 推送配置。

- **读取 URL:** `/api/notify-config` (Method: `GET`)
- **保存 URL:** `/api/notify-config` (Method: `POST`)
- **Content-Type:** `application/json`

**POST 请求参数 (Body)：**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| telegram.enable_push | bool | 否 | 是否启用通知与机器人命令服务 |
| telegram.bot_token | string | 否 | Telegram Bot Token |
| telegram.chat_id | string | 否 | 默认推送目标 chat id，支持多个（逗号/空格分隔） |
| telegram.web_base_url | string | 否 | 生成在线模型地址的访问前缀 |

Telegram 命令说明：
- `/help`：查看命令列表
- `/cookies`：查看 Cookie 状态
- `/count`：查看已归档模型数
- `/search 关键词`：搜索本地模型并返回在线地址
- `/url`：查看当前在线地址前缀
- `/seturl 地址`：设置在线地址前缀
- 直接发送 MakerWorld 模型链接：触发归档

测试连接接口：
- **URL:** `/api/notify-test`
- **Method:** `POST`
- **说明:** 按当前已启用通知渠道发送测试消息。当前版本仅接入 Telegram，但业务代码已经统一走通知分发层，后续可扩展到企微等其他渠道。

### 1.5 获取运行配置
用于读取当前运行时配置。

- **URL:** `/api/config`
- **Method:** `GET`

**响应示例：**
```json
{
  "download_dir": "./data",
  "logs_dir": "./logs",
  "cookie_file": "./config/cookie.json"
}
```

说明：
- 配置文件位于 `app/config/config.json`。
- 接口返回的是当前生效配置，运行时会自动解析为绝对路径给程序使用。

---

## 2. 画廊及展示层 API

### 2.1 获取已归档模型列表
获取所有已归档模型信息，用于前端画廊页面展示。

- **URL:** `/api/gallery`
- **Method:** `GET`

**响应示例：**
```json
{
  "models": [
    {
      "model_dir": "MW_12345_ModelName",
      "title": "测试模型",
      "cover": "./images/cover.png",
      "collectDate": 1714521600,
      "summary": "模型简介..."
    }
  ]
}
```

### 2.2 获取画廊标记状态
获取已保存的画廊标记（如收藏、已打印等）。

- **URL:** `/api/gallery/flags`
- **Method:** `GET`

**响应示例：**
```json
{
  "favorites": ["MW_12345_ModelName"],
  "printed": ["MW_54321_AnotherModel"]
}
```

### 2.3 保存画廊标记状态
更新并持久化保存模型在画廊中的标记状态。

- **URL:** `/api/gallery/flags`
- **Method:** `POST`
- **Content-Type:** `application/json`

**请求示例：**
```json
{
  "favorites": ["MW_12345_ModelName", "MW_99999_NewModel"],
  "printed": []
}
```

---

## 3. 模型管理与维护 API

### 3.1 重建归档静态页面
当更新主模板或需要批量维护历史归档页面时使用。当前版本还会同步扫描 `instances/`，尝试修正 `meta.json` 中实例 `fileName` 映射。

- **URL:** `/api/archive/rebuild-pages`
- **Method:** `POST`
- **Content-Type:** `application/json`

**请求参数 (Body) [可全空]：**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| force | bool | 否 | 强制重建 |
| backup | bool | 否 | 备份旧 `index.html` |
| dry_run | bool | 否 | 仅预览，不实际写文件 |

**响应关键字段：**
| 字段名称 | 类型 | 说明 |
|----------|------|------|
| processed | int | 扫描到的模型目录数 |
| updated | int | 实际更新的目录数 |
| skipped | int | 跳过目录数 |
| failed | int | 失败目录数 |
| fixed_instance_files | int | 已修正实例 `fileName` 映射数量 |
| unresolved_instance_files | int | 未能定位实例文件的数量 |

### 3.2 删除模型
在本地彻底删除对应的模型目录及其附带的所有文件。

- **URL:** `/api/models/{model_dir}/delete`
- **Method:** `POST`

### 3.3 获取/上传模型附件
访问和覆盖指定模型的补充附件。

- **获取已有附件列表 URL:** `/api/models/{model_dir}/attachments` (Method: `GET`)
- **上传附件 URL:** `/api/models/{model_dir}/attachments` (Method: `POST`, `multipart/form-data`)

### 3.4 获取/上传模型实打图片
获取或上传用户打印实物照片。

- **获取实打图列表 URL:** `/api/models/{model_dir}/printed` (Method: `GET`)
- **上传实打图片 URL:** `/api/models/{model_dir}/printed` (Method: `POST`, `multipart/form-data`)

### 3.5 按实例 ID 下载 3MF
用于模型详情页稳定下载 3MF，避免前端按展示标题拼接导致错链。

- **URL:** `/api/models/{model_dir}/instances/{inst_id}/download`
- **Method:** `GET`

说明：
- 接口会按实例信息自动匹配真实文件并返回下载。
- 若匹配成功且 `fileName` 不一致，会自动回填 `meta.json`。

---

## 4. 手动导入与解析 API

### 4.1 解析本地 3MF 草稿
通过上传单个或多个 3MF 文件，解析出内部配置帮助填充手动导入表单。

- **URL:** `/api/manual/3mf/parse`
- **Method:** `POST`
- **Content-Type:** `multipart/form-data`

### 4.2 提交手动导入模型
当平台不属于 MakerWorld 或无法直爬时，通过手动填表提交并生成一致的归档格式。

- **URL:** `/api/models/manual`
- **Method:** `POST`
- **Content-Type:** `multipart/form-data`

### 4.3 删除手动导入草稿缓存
用于清理 `app/tmp/manual_drafts/{session_id}` 草稿目录。

- **URL:** `/api/manual/drafts/{session_id}`
- **Method:** `DELETE`

### 4.4 草稿缓存丢弃（Beacon）
与 4.3 功能相同，主要供前端 `navigator.sendBeacon` 在页面离开时触发。

- **URL:** `/api/manual/drafts/{session_id}/discard`
- **Method:** `POST`

---

## 5. 重试与记录修补 API

针对于 3MF 文件缺失或历史记录未补全时使用。

### 5.1 获取缺失 3MF 文件的日志列表
- **URL:** `/api/logs/missing-3mf`
- **Method:** `GET`

### 5.2 批量重试下载缺失文件
- **URL:** `/api/logs/missing-3mf/redownload`
- **Method:** `POST`

说明：
- 会根据模型来源自动选择国内 / 国际平台 Cookie。
- 真实下载失败时会更新 Cookie 状态，并根据已启用通知渠道发送限流或失效告警。

### 5.3 针对单个模型/实例重试
- **重试单模型:** `/api/models/{model_dir}/redownload` (POST)
- **重试单实例:** `/api/models/{model_dir}/instances/{instance_id}/redownload` (POST)

说明：
- 同样按平台自动选择 Cookie。
- Cookie 状态只在真实下载链路中更新。

---

## 6. 配置文件路径说明

当前版本运行时配置目录统一为 `app/config/`：

- `app/config/config.json`
- `app/config/cookie.json`
- `app/config/gallery_flags.json`

兼容说明：
- 若检测到旧版 `app/config.json`、`app/cookie.txt`、`app/gallery_flags.json`
- 系统会在启动时自动迁移到 `app/config/` 下的新文件结构
- Docker 部署建议直接持久化整个 `app/config/` 目录
