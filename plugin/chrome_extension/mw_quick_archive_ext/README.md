# 快速归档助手（Chrome 扩展）

## 功能
- 配置后端 API 地址（默认 `http://127.0.0.1:8000`）
- 在 `https://makerworld.com.cn/zh/models/*` 和 `https://makerworld.com/zh/models/*` 页面显示「归档模型」按钮
- 点击扩展图标弹出菜单：保存地址、测试连接、归档当前模型、本地模型主页
- 点击归档后会弹出明显的开始和完成提示

## 安装
1. 打开 `chrome://extensions/`
2. 开启右上角「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择本目录：`plugin/chrome_extension/mw_quick_archive_ext`

## 使用
1. 打开扩展弹窗，设置后端地址并保存
2. 在模型页面点击右下角「归档模型」或弹窗中的「归档当前模型」
3. 如需查看本地归档页面，点击「本地模型主页」

## 后端接口
- `POST /api/archive` body: `{ "url": "https://makerworld.com.cn/zh/models/..." }`
- `GET /api/config`（测试连接）
