FROM node:20-slim AS h5-builder

WORKDIR /web

COPY h5/package*.json ./
RUN npm install
COPY h5/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

# 系统依赖：curl 用于归档流程的兜底抓取
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 仅复制必要的应用文件，减少构建上下文
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
COPY --from=h5-builder /web/dist ./h5/dist

# 准备默认数据/日志/配置/监控/整理目录（可通过挂载覆盖）
RUN mkdir -p /app/data /app/logs /app/config /app/watch /app/organize

EXPOSE 8000
VOLUME ["/app/data", "/app/logs", "/app/config", "/app/watch", "/app/organize"]
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
