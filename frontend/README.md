# Home Library Frontend

Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router 前端基础框架。

## 环境变量

在 `frontend/` 下创建 `.env.local` 可覆盖 API 地址：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

未设置时默认使用 `/api`。

## 本地启动

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：

```text
http://127.0.0.1:5173
```

## 常用命令

```bash
npm run typecheck
npm run build
npm run preview
```
