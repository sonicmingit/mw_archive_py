# meta.json 字段说明（含来源差异与使用位置）

本文用于说明 `app/data/*/meta.json` 的字段含义、作用、主要读写位置，以及 **归档模型（MW）** 与 **本地导入模型（LocalModel/Others）** 的差异规则。

## 1. 文件定位与用途

- 位置：`app/data/<模型目录>/meta.json`
- 作用：
  - 作为模型详情页（`/v2/files/{model_dir}`）的核心数据源
  - 作为模型库（`/api/gallery`）列表聚合的数据源
  - 作为实例下载、附件管理、打印记录管理的索引源

## 2. 数据来源类型

当前数据目录中可见三类目录：

- `MW_*`：在线归档（MakerWorld 抓取）
- `LocalModel_*`：手动导入（本地模型）
- `Others_*`：手动导入（旧版遗留）

### 2.1 类型判定规则（运行时）

后端在模型库聚合时会结合目录名和 `source` 字段判定来源：

- `MW_*` -> `makerworld`
- `LocalModel_*` / `Others_*` 或 `source in {localmodel, others}` -> `localmodel`

主要位置：`app/server.py` 的 `scan_gallery(...)`

## 3. 顶层字段说明

> 说明：
> - “归档(MW)”表示在线归档写入
> - “本地导入”表示 `LocalModel_*` / `Others_*` 写入
> - “使用位置”列写的是主要逻辑入口（非穷举）

| 字段 | 类型 | 归档(MW) | 本地导入 | 作用 | 主要使用位置 |
|---|---|---:|---:|---|---|
| `baseName` | string | 必有 | 必有 | 模型目录基名，关联文件命名 | `app/archiver.py`、`app/server.py` |
| `source` | string | 通常无 | 常有（`LocalModel`/`others`） | 来源标识，辅助前端隐藏在线统计 | `app/server.py::scan_gallery`、`app/static/js/model.js` |
| `url` | string | MakerWorld链接 | `modelLink/sourceLink` 或空 | 原文链接展示 | `app/static/js/model.js::renderTitle` |
| `id` | number/null | MakerWorld模型ID | 通常 `null` | 模型唯一标识（在线模型） | `app/server.py::scan_gallery`、重下载相关 API |
| `slug` | string | 通常有 | 常为空 | 在线模型 slug | 主要用于留存兼容 |
| `title` | string | 必有 | 必有 | 模型标题 | 前后端普遍使用 |
| `titleTranslated` | string | 可空 | 可空 | 预留翻译标题 | 当前主要做兼容保留 |
| `coverUrl` | string | 通常有 | 常为空 | 封面原始 URL | 数据留存、兼容 |
| `tags` | array[string] | 常有 | 常为空或手工输入 | 标签展示/筛选 | `app/server.py::scan_gallery`、前端筛选 |
| `tagsOriginal` | array[string] | 常有 | 常与 `tags` 相同 | 原始标签备份 | 兼容保留 |
| `stats` | object | 常有真实值 | 一般为 0 | 统计信息（点赞/下载等） | `app/static/js/model.js::renderStats` |
| `cover` | object | 必有 | 必有 | 封面本地映射信息 | `model.js::normalizeImages` |
| `author` | object | 必有 | 必有 | 作者信息与头像路径 | `model.js::normalizeAuthor`、`scan_gallery` |
| `images` | object | 必有 | 必有 | 设计图/封面/简介图文件名索引 | `model.js::normalizeImages` |
| `designImages` | array[object] | 常有 | 常有 | 设计图结构化记录（含 `relPath`） | 回退兼容、页面渲染 |
| `summaryImages` | array[object] | 常有 | 常有 | 简介图结构化记录 | 回退兼容、简介渲染 |
| `summary` | object | 必有 | 必有 | 简介文本（raw/html/text） | `model.js::renderSummary`、`scan_gallery` 摘要 |
| `instances` | array[object] | 必有 | 必有 | 打印实例配置与下载信息 | 详情页实例卡、实例下载 API |
| `collectDate` | int (Unix秒) | 必有 | 必有 | 采集/导入时间 | `model.js::renderCollectDate`、gallery 时间显示 |
| `offlineFiles` | object | 必有 | 必有 | 附件/打印成品索引 | 附件 API、打印记录 API、详情页附件区 |
| `update_time` | string(ISO) | 常有（老数据可能缺失） | 常有 | 最近更新时间 | `/api/v2/models/{dir}/meta` 会补齐 |
| `generatedAt` | string | 常有 | 常有 | 生成时工作目录信息（调试留存） | 主要为留存 |
| `note` | string | 常有 | 常有 | 说明性文本 | 留存 |
| `importMeta` | object | 无 | 批量导入模型可有 | 本地批量导入标记，仅用于 `LocalModel_*` 聚合与追踪 | `app/batch_import_service.py` |

## 4. 嵌套字段说明

## 4.1 `cover`

```json
"cover": {
  "url": "...",
  "localName": "design_01.jpg",
  "relPath": "images/design_01.jpg"
}
```

- `url`：原始封面 URL（本地导入通常为空）
- `localName`：本地文件名
- `relPath`：相对模型目录路径

主要使用：前端详情页封面回退逻辑（`images.cover` 不可用时）

## 4.2 `author`

```json
"author": {
  "name": "...",
  "url": "...",
  "avatarUrl": "...",
  "avatarLocal": "author_avatar.jpg",
  "avatarRelPath": "images/author_avatar.jpg"
}
```

- 详情页与模型库主要依赖 `name/url/avatarRelPath`
- `avatarUrl/avatarLocal` 主要用于来源留存与兼容回退

主要使用：`model.js::normalizeAuthor`、`gallery.js`、`scan_gallery`

## 4.3 `images`

```json
"images": {
  "cover": "design_01.jpg",
  "design": ["design_01.jpg", "..."],
  "summary": ["summary_ext_01.jpg", "..."]
}
```

- `cover`：主封面文件名
- `design`：设计图文件名列表
- `summary`：简介图文件名列表

主要使用：`model.js::normalizeImages`、轮播图与详情图渲染

## 4.4 `summary`

```json
"summary": {
  "raw": "<p>...</p>",
  "html": "<p>...</p>",
  "text": "..."
}
```

- `raw/html`：富文本内容（含图片）
- `text`：纯文本摘要（用于列表摘要和检索友好）

主要使用：
- `model.js::renderSummary`（详情页）
- `server.py::scan_gallery`（摘要提取）

## 4.5 `offlineFiles`

```json
"offlineFiles": {
  "attachments": ["a.zip", "..."],
  "printed": ["p1.jpg", "..."]
}
```

- `attachments`：`file/` 目录下附件索引
- `printed`：`printed/` 目录下打印成品图索引

更新方式：
- 上传/删除附件、打印图时通过后端同步写回
- `/api/v2/models/{dir}/meta` 会在缺失时动态补齐

主要逻辑：`server.py::sync_offline_files_to_meta`

## 4.6 `instances`

实例是数组，每一项代表一个打印配置（3MF）：

常见字段：

- 标识与标题：`id`, `profileId(归档常见)`, `title`, `titleTranslated`
- 时间与统计：`publishTime`, `downloadCount`, `printCount`
- 耗材与估算：`prediction`, `weight`, `materialCnt`, `materialColorCnt`, `needAms`
- 内容：`summary`, `summaryTranslated`
- 下载相关：`name`, `fileName`, `sourceFileName(本地导入常见)`, `downloadUrl`, `apiUrl`
- 媒体：`plates[]`, `pictures[]`, `instanceFilaments[]`
- 本地批量导入附加：`importMeta`


### `instances[] 中的名称`

`title`
含义：给用户看的“实例名称/配置标题”（展示名）
作用：详情页实例卡标题显示、人工识别用
特点：可读性优先，不保证是合法文件名，也不保证唯一

`name`
含义：来源侧返回的原始 3MF 名称（偏“来源名”）
作用：历史兼容与回填候选（当 fileName 缺失时会拿它猜文件名）
特点：可能和 title 一样，也可能是 API 返回名；不应作为最终落盘文件唯一标识

`fileName`
含义：本地 instances/ 目录里的真实文件名（落盘名）
作用：下载接口定位文件、前端下载链接构建、重建页面与自愈逻辑的主字段
特点：应稳定、可落盘、尽量唯一；你这次修复后冲突会自动改成唯一名（如 _id 后缀）


title = 展示名，name = 来源原名，fileName = 本地真实文件名（实际应以它为准）。

### `importMeta`

仅本地批量导入写入，在线归档 `MW_*` 不使用该结构。

顶层示例：

```json
"importMeta": {
  "modelKey": "design_model:123456",
  "keySource": "DesignModelId"
}
```

实例示例：

```json
"importMeta": {
  "configFingerprint": "design_profile:654321",
  "fingerprintSource": "DesignProfileId",
  "fileHash": "sha256...",
  "designModelId": "123456",
  "designProfileId": "654321"
}
```

字段说明：
- `modelKey`
  - 仅用于本地批量导入内部聚合
  - 用来识别“同一个模型”
- `keySource`
  - `modelKey` 来源说明
  - 可能来自 `DesignModelId` 或标题 / 作者回退规则
- `configFingerprint`
  - 仅用于识别“同模型下的不同配置”
- `fingerprintSource`
  - `configFingerprint` 来源说明
- `fileHash`
  - 本地文件哈希，作为回退去重和问题追踪辅助信息
- `designModelId` / `designProfileId`
  - 原始 `3MF` 解析出的设计模型 / 配置标识

### `plates[]`

常见字段：`index`, `prediction`, `weight`, `filaments[]`, `thumbnailUrl`, `thumbnailRelPath`, `thumbnailFile`

### `pictures[]`

常见字段：`index`, `url`, `relPath`, `fileName`, `isRealLifePhoto`

### `instanceFilaments[]`

常见字段：`type`, `color`, `usedM`, `usedG`

主要使用：
- 详情页实例卡渲染：`app/static/js/model.js`
- 实例下载接口：`/api/models/{model_dir}/instances/{inst_id}/download`
- 重下载修复：`/api/instances/{inst_id}/redownload`、`/api/models/{id}/redownload`




## 5. 归档模型 vs 本地导入差异

## 5.1 顶层字段差异

- `source`：
  - 归档 `MW_*`：通常没有该字段
  - 本地导入：有，典型值 `LocalModel` / `others`
- `importMeta`：
  - 归档：没有
  - 本地批量导入：可能有，仅用于批量导入聚合与追踪
- `id`：
  - 归档：MakerWorld 数值 ID
  - 本地导入：通常 `null`
- `stats`：
  - 归档：真实统计
  - 本地导入：通常初始化为 0
- `url`：
  - 归档：MakerWorld 详情 URL
  - 本地导入：`modelLink/sourceLink` 或空

## 5.2 `instances` 字段差异

- 归档实例常见：`profileId`
- 本地导入实例常见：`sourceFileName`
- 本地批量导入实例可额外包含 `importMeta`
- 两者都建议保留 `fileName`，确保下载与文件定位稳定

## 6. 兼容与回退规则（重要）

## 6.1 `collectDate` 回退

- 若缺失或非法，后端会使用 `meta.json` 文件 mtime 回填
- 相关：`server.py::ensure_collect_date`、`scripts/fix_collect_date.py`

## 6.2 `update_time` 回退

- 若缺失，`/api/v2/models/{dir}/meta` 会用 `meta.json` mtime 补齐

## 6.3 实例文件名解析回退

后端解析实例文件名时会按以下候选顺序尝试：

- `fileName` -> `name` -> `sourceFileName` -> `localName` -> `title`
- 并兼容自动补 `.3mf` 与历史双后缀情况

相关：`server.py::_candidate_instance_names` / `resolve_instance_filename`

## 6.4 前端字段兼容

前端 `model.js` 对历史数据做了多层兼容：

- `author`：兼容旧命名 `avatar_local_path` 等
- `images`：既支持新结构对象，也支持旧数组回退
- `summaryImages/designImages`：作为 `images` 缺失时的回退来源

## 7. 写入入口（谁会改 meta.json）

- 在线归档生成：`app/archiver.py::build_meta(...)`
- 手动导入生成：`app/server.py::api_manual_import(...)`
- 附件/打印索引同步：`app/server.py::sync_offline_files_to_meta(...)`
- 实例导入更新：`app/server.py::/api/models/{model_dir}/instances/import-3mf`
- 本地批量导入写入：`app/batch_import_service.py`
- 历史修复脚本：
  - `scripts/fix_collect_date.py`
  - `scripts/rebuild_index_from_meta.py`

## 8. 建议维护规范

- 任何新增字段应满足：
  - 写入逻辑明确（归档、本地导入、还是运行时补齐）
  - 前端读取有兼容处理（避免旧数据崩溃）
  - 在本文档补充字段说明与使用位置
- 若字段可能缺失，优先在 API 层补齐，而非让前端猜测。
