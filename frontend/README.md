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
npm run test
npm run test:e2e
npm run build
npm run preview
```

## 系统设置与账号权限

登录账号均可访问“设置”，管理当前账号 AI 偏好、外部检索和本地偏好。管理员另有“服务器 AI 配置”区域，通过当前管理员密码和服务器升级专用密码保存或恢复全局配置。服务器配置变化后，页面先重载账号运行参数，再清除旧状态并刷新非生成健康检查；连接异常会保留已成功保存的配置，藏书等页面可继续使用。

Task 6 隔离浏览器验收使用受控 API 和合成凭据，覆盖管理员保存、重载、故障隔离、恢复，普通账号路由与菜单可达性，以及 390px 移动布局：

```bash
E2E_BASE_URL=http://127.0.0.1:5179 E2E_BROWSER_CHANNEL=chrome E2E_NO_ARTIFACTS=1 npm run test:e2e -- ../e2e/system-ai-settings.spec.ts --workers=1
```

`E2E_BASE_URL` 同时控制测试地址和 Vite 严格监听端口；本地安装 Chrome 时可指定 `E2E_BROWSER_CHANNEL=chrome`。此用例关闭 trace、video、screenshot 和失败 DOM 快照；`E2E_NO_ARTIFACTS=1` 禁止保留测试输出产物，不影响其他用例默认的诊断产物设置。该浏览器测试验证真实前端及 Element Plus 交互，后端持久化与认证由独立后端测试验证。
