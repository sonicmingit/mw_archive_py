# 附件补丁脚本说明

用途：为已下载模型的 `index.html` / `style.css` 补齐附件上传与下载列表功能。

脚本：`scripts/patch_attachments.py`

使用方式：
1) 扫描整个下载目录：
   `python3 scripts/patch_attachments.py`
2) 只修复单个模型目录：
   `python3 scripts/patch_attachments.py app/data/MW_1878105_迷你奶酪豆铲`

说明：
- 已存在附件功能的页面会自动跳过，不会重复插入。
- 脚本会同步修复路径解码问题（避免出现“目录不存在”）。
