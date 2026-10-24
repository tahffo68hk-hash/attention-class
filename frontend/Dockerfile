# ---------- 构建阶段 ----------
FROM node:22-alpine AS builder

WORKDIR /app

# 只拷贝依赖清单，最大化命中缓存；优先 npm ci（严格按 lock 安装），
# lock 与 package.json 不同步时回落到 npm install。
ARG NPM_REGISTRY=https://registry.npmmirror.com
COPY package.json package-lock.json* ./
RUN npm config set registry "${NPM_REGISTRY}" \
    && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund)

COPY . .
RUN npm run build

# ---------- 运行阶段 ----------
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
