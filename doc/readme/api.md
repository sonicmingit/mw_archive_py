# MakerWorld Archive - 后端 API 接口文档

本文档描述了 MakerWorld Archive 后端服务的主要 API 接口，包括模型归档、Cookie 同步、画廊数据获取、缺失文件管理以及手动导入等相关的接口定义和调用的示例。

---

## 目录
1. [核心流程 API](#1-核心流程-api)
   - 1.1 [提交模型归档任务](#11-提交模型归档任务)
   - 1.2 [同步浏览器 Cookie](#12-同步浏览器-cookie)
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

---

## 1. 核心流程 API

### 1.1 提交模型归档任务
用于触发脚本向后端发送指令，让后端开始抓取并下载指定 MakerWorld 模型的全部文件和元数据。

- **URL:** `/api/archive`
- **Method:** `POST`
- **Content-Type:** `application/json`

**请求参数 (Body):**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| url      | string | 是 | 当前模型详情页的完整 URL |

**请求示例:**
```json
{
  "url": "https://makerworld.com/zh/models/12345"
}
```

**响应示例:**
```json
{
  "status": "ok",
  "message": "归档任务已开始"
}
```

### 1.2 同步浏览器 Cookie
用于把当前浏览器的 Cookie 状态同步到后端环境，使后端的爬虫或请求下载可以携带鉴权信息并规避登录限制。

- **URL:** `/api/cookie`
- **Method:** `POST`
- **Content-Type:** `application/json`

**请求参数 (Body):**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| cookie   | string| 是 | 从浏览器获取的 `document.cookie` 完整字符串 |

**请求示例:**
```json
{
  "cookie": "sid=xxxxxx; locale=zh_CN; sess=yyyyyy;"
}
```

**响应示例:**
```json
{
  "status": "ok",
  "message": "Cookie 同步成功"
}
```

---

## 2. 画廊及展示层 API

### 2.1 获取已归档模型列表
获取所有已下载和归档在本地目录中的模型信息，用于前端画廊页面 (Gallery) 展示。

- **URL:** `/api/gallery`
- **Method:** `GET`

**响应示例:**
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

**响应示例:**
```json
{
  "favorites": ["MW_12345_ModelName"],
  "printed": ["MW_54321_AnotherModel"]
}
```

### 2.3 保存画廊标记状态
更新和持久化保存模型在画廊中的标记状态。

- **URL:** `/api/gallery/flags`
- **Method:** `POST`
- **Content-Type:** `application/json`

**请求示例:**
```json
{
  "favorites": ["MW_12345_ModelName", "MW_99999_NewModel"],
  "printed": []
}
```

---

## 3. 模型管理与维护 API

### 3.1 重建归档静态页面
当更新了主模板或者需要批量维护历史归档页面时使用。  
当前版本还会同步扫描 `instances/`，尝试修正 `meta.json` 中实例 `fileName` 映射。

- **URL:** `/api/archive/rebuild-pages`
- **Method:** `POST`
- **Content-Type:** `application/json`

**请求参数 (Body) [可全空]:**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| force    | bool | 否 | 强制重建 |
| backup   | bool | 否 | 备份旧 index.html |
| dry_run  | bool | 否 | 仅预览，不实际写文件 |

**响应关键字段:**
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

**路径参数 (Path Variables):**
| 字段名称 | 类型 | 说明 |
|----------|------|------|
| model_dir| string | 目标模型的目录名，例如 `MW_12345_ModelA` |

**响应示例:**
```json
{
  "status": "success",
  "message": "Model deleted successfully."
}
```

### 3.3 获取/上传模型附件
访问和覆盖指定模型的补充附件。

- **获取已有附件列表 URL:** `/api/models/{model_dir}/attachments` (Method: `GET`)
- **上传附件 URL:** `/api/models/{model_dir}/attachments` (Method: `POST`, 表单类型: `multipart/form-data`)

**POST 请求参数 (Form-Data):**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| file     | file | 是 | 需要上传的附件二进制文件流 |

### 3.4 获取/上传模型实打图片
类似于附件，获取或上传用户自己打印出来的实物照片记录。

- **获取实打图列表 URL:** `/api/models/{model_dir}/printed` (Method: `GET`)
- **上传实打图片 URL:** `/api/models/{model_dir}/printed` (Method: `POST`, 表单类型: `multipart/form-data`)

**POST 请求参数同 3.3，上传字段名为 `file`。**

### 3.5 按实例 ID 下载 3MF
用于模型详情页稳定下载 3MF，避免前端按标题/文件名拼接导致错链。

- **URL:** `/api/models/{model_dir}/instances/{inst_id}/download`
- **Method:** `GET`

**路径参数 (Path Variables):**
| 字段名称 | 类型 | 说明 |
|----------|------|------|
| model_dir | string | 模型目录名，例如 `MW_12345_ModelA` |
| inst_id | int | 实例 ID（`meta.instances[*].id`） |

说明:
- 接口会按实例信息自动匹配真实文件并返回下载。
- 若匹配成功且 `fileName` 不一致，会自动回填 `meta.json`（运行时自愈）。

---

## 4. 手动导入与解析 API

### 4.1 解析本地 3MF 草稿
通过上传单个或多个 3MF 文件，解析出内部配置以帮助填充手动导入表单。

- **URL:** `/api/manual/3mf/parse`
- **Method:** `POST`
- **Content-Type:** `multipart/form-data`

**请求参数 (Form-Data):**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| files    | file array | 是 | 多个 .3mf 文件上传 |

### 4.2 提交手动导入模型
当平台不属于 MakerWorld 或因为某些特殊原因无法由后端直爬时，通过手动填表提交并生成一致的归档格式。

- **URL:** `/api/models/manual`
- **Method:** `POST`
- **Content-Type:** `multipart/form-data`

**请求参数 (Form-Data):**
| 字段名称 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| title    | string | 是 | 模型标题 |
| modelLink| string | 否 | 原文/模型链接 |
| summary  | string | 否 | 模型介绍 |
| tags     | string | 否 | 标签 |
| cover    | file   | 否 | 模型封面图 |
| design_images | file array | 否 | 其他设计渲染图 |
| _(及其它如3mf草稿ID等配置项)_ | | | |

### 4.3 删除手动导入草稿缓存
用于清理 `app/tmp/manual_drafts/{session_id}` 的草稿目录（识别后不保存场景）。

- **URL:** `/api/manual/drafts/{session_id}`
- **Method:** `DELETE`

**路径参数 (Path Variables):**
| 字段名称 | 类型 | 说明 |
|----------|------|------|
| session_id | string | 32 位十六进制草稿 ID |

### 4.4 草稿缓存丢弃（Beacon）
与 4.3 功能相同，主要用于前端 `navigator.sendBeacon` 在页面离开时触发清理。

- **URL:** `/api/manual/drafts/{session_id}/discard`
- **Method:** `POST`

---

## 5. 重试与记录修补 API

针对于 MakerWorld 文件下载经常因为限流或者接口变更导致的 3MF 文件未成功下载，相关的修补接口：

### 5.1 获取缺失 3MF 文件的日志列表
- **URL:** `/api/logs/missing-3mf`
- **Method:** `GET`

### 5.2 批量重试下载缺失文件
- **URL:** `/api/logs/missing-3mf/redownload`
- **Method:** `POST`

### 5.3 针对单个模型/实例重试
- **重试单模型:** `/api/models/{model_id}/redownload` (POST)
- **重试单实例:** `/api/instances/{inst_id}/redownload` (POST)

_注意路径内的 `{model_id}` 及 `{inst_id}` 必须是纯数字标识。_
