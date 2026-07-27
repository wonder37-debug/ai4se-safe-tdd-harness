# stage 1: build TypeScript + static frontend
FROM node:20-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build
# public 静态资源由 build 脚本 cpSync 带入 dist/web/public；下方 cp 为冗余兜底
RUN cp -r src/web/public dist/web/public 2>/dev/null || true

# stage 2: 生产镜像（仅运行时依赖）
FROM node:20-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist
# 非 root 运行：node:20-bookworm-slim 自带 node 用户（uid 1000），降低容器逃逸面
USER node
EXPOSE 8080
# 容器必须直接起 web 面板，故显式带 --web
CMD ["node", "dist/index.js", "--web"]
