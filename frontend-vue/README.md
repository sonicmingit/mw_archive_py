# frontend-vue

独立的 Vue 3 + Vite 前端工程。

## 启动

```bash
npm install
npm run dev
```

默认前端开发地址:

- `http://127.0.0.1:5173`

默认会把 `/api/*` 代理到:

- `http://127.0.0.1:8000`

## 环境变量

复制 `.env.example` 为 `.env.local` 后可调整:

- `VITE_API_BASE_URL`
- `VITE_DEV_BACKEND_TARGET`

常见场景:

1. 本地联调后端
   - `VITE_API_BASE_URL=/api`
   - `VITE_DEV_BACKEND_TARGET=http://127.0.0.1:8000`

2. 直接请求远端后端
   - `VITE_API_BASE_URL=http://your-backend-host:8000/api`

## 页面

- `/` 模型库
- `/detail/:id` 模型详情
- `/config` 配置页

## 说明

- 该目录是完全独立前端，不依赖原始模板页和原始前端脚本。
- 接口直接调用已启动的后端服务。
- logo 使用 `public/fav.png`。
