# 部署与运维

本文档说明 Home Library 的 Docker Compose 部署、NAS 部署、数据持久化、备份恢复和常见故障处理。

## 快速启动

前提条件：

- Docker Engine 24+
- Docker Compose v2
- 可选：本机或容器内 Ollama

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
curl http://localhost/api/health
```

默认服务：

| 服务 | 说明 |
|---|---|
| `backend` | FastAPI 后端，容器内监听 `8000` |
| `frontend` | Nginx 托管前端并反向代理 `/api/` |

默认访问地址：`http://localhost`。如果宿主机 80 端口已被占用，在 `.env` 中设置：

```env
HTTP_PORT=8080
```

然后访问 `http://localhost:8080`。

## 数据持久化

Compose 使用命名卷保存数据：

| 卷 | 容器路径 | 用途 |
|---|---|---|
| `db_data` | `/data` | SQLite 数据库 |
| `uploads` | `/uploads` | 上传文件、封面等 |
| `backups` | `/backups` | 备份输出 |

Docker 内默认数据库地址：

```env
DATABASE_URL=sqlite:////data/home_library.sqlite3
```

不要把生产数据库放在容器可写层中；应使用命名卷或 NAS 挂载目录。

## 环境变量

| 变量 | 示例 | 说明 |
|---|---|---|
| `HTTP_PORT` | `80` | Nginx 对外端口 |
| `APP_ENV` | `production` | 运行环境 |
| `APP_SECRET_KEY` | 随机长字符串 | JWT 签名密钥，生产必须修改 |
| `DATABASE_URL` | `sqlite:////data/home_library.sqlite3` | 数据库连接 |
| `CORS_ORIGINS` | `http://localhost` | 允许访问的前端地址 |
| `INITIAL_ADMIN_USERNAME` | `admin` | 首次初始化管理员 |
| `INITIAL_ADMIN_PASSWORD` | `change-me` | 首次初始化管理员密码 |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | 本地开发 Ollama 地址 |
| `DOCKER_OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Docker Compose 中后端容器访问 Ollama 的地址 |
| `OLLAMA_DEFAULT_MODEL` | `qwen2.5` | 默认模型 |
| `OLLAMA_TIMEOUT_SECONDS` | `60` | AI 请求超时秒数 |
| `OLLAMA_OPTIONAL` | `true` | Ollama 不可用时是否降级 |
| `POSTGRES_DB` | `home_library` | PostgreSQL 可选 profile 数据库名 |
| `POSTGRES_USER` | `home_library` | PostgreSQL 用户 |
| `POSTGRES_PASSWORD` | `change-me` | PostgreSQL 密码 |

生产环境至少修改：

```env
APP_ENV=production
APP_SECRET_KEY=replace-with-a-long-random-secret
INITIAL_ADMIN_PASSWORD=replace-this-password
CORS_ORIGINS=http://your-host-or-domain
```

## 备份

容器内提供备份脚本：

```bash
docker compose exec backend /app/scripts/backup.sh
```

脚本行为：

- 优先使用 `sqlite3 .backup` 做 SQLite 在线备份，减少文件锁风险。
- 将上传目录打包为 `uploads_YYYYmmdd_HHMMSS.tar.gz`。
- 输出到 `/backups` 卷。
- 自动删除超过 `KEEP_DAYS` 的旧备份，默认 7 天。

可指定保留天数：

```bash
docker compose exec -e KEEP_DAYS=30 backend /app/scripts/backup.sh
```

## 恢复

停止服务：

```bash
docker compose down
```

恢复 SQLite：

```bash
docker run --rm -v home-library_db_data:/data -v home-library_backups:/backups alpine sh -c \
  "gzip -dc /backups/home_library_YYYYmmdd_HHMMSS.sqlite3.gz > /data/home_library.sqlite3"
```

恢复 uploads：

```bash
docker run --rm -v home-library_uploads:/uploads -v home-library_backups:/backups alpine sh -c \
  "rm -rf /uploads/* && tar -xzf /backups/uploads_YYYYmmdd_HHMMSS.tar.gz -C /uploads"
```

然后重启：

```bash
docker compose up -d
```

卷名前缀取决于项目目录名。可用 `docker volume ls` 查看实际名称。

## Ollama

### 使用宿主机 Ollama

macOS / Windows Docker Desktop 可使用：

```env
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Linux 服务器可改为宿主机网关 IP，或使用 Compose 内置 profile。

### 使用 Compose Ollama

```bash
docker compose --profile ollama up -d
docker compose exec ollama ollama pull qwen2.5
```

同时将 `.env` 调整为：

```env
DOCKER_OLLAMA_BASE_URL=http://ollama:11434
```

### GPU 加速

NVIDIA GPU 主机需先安装 NVIDIA Container Toolkit。然后可在 `ollama` 服务上按主机环境补充 GPU 配置，例如：

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

不同 NAS 和 Linux 发行版的 GPU 配置差异较大，建议先确认 `docker run --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` 可用。

## PostgreSQL 可选配置

启动 PostgreSQL profile：

```bash
docker compose --profile postgres up -d postgres
```

将 `.env` 中数据库地址改为：

```env
DATABASE_URL=postgresql+psycopg://home_library:change-me@postgres:5432/home_library
```

当前项目以 SQLite 为 MVP 默认数据库。切换 PostgreSQL 前，应确认后端依赖中已有相应驱动，并完成一次完整测试。

## NAS 部署建议

以群晖为例：

1. 在 File Station 中建立项目目录，例如 `/volume1/docker/home-library`。
2. 上传仓库文件或通过 Git 拉取。
3. 复制 `.env.example` 为 `.env`，修改 `HTTP_PORT`、`APP_SECRET_KEY`、`CORS_ORIGINS`。
4. 在 Container Manager 中使用项目目录的 `docker-compose.yml` 创建项目。
5. 如 80 端口被 DSM 占用，设置 `HTTP_PORT=8080`。
6. 定期执行备份脚本，或在 DSM 任务计划中添加定时命令。

跨服务器迁移时，至少迁移：

- `.env`
- `db_data` 卷中的 SQLite 数据库
- `uploads` 卷
- `backups` 卷或离线备份文件

## 故障排查

### 前端可以打开，但 API 报错

检查后端健康状态：

```bash
docker compose ps
docker compose logs backend
curl http://localhost/api/health
```

### 登录后立刻退出

检查 `APP_SECRET_KEY` 是否在重启后变化。生产环境必须固定该值。

### 跨域错误

Docker 内前端通过 Nginx 同源代理访问 `/api`，一般不需要浏览器跨域。若直接访问后端端口，需在 `.env` 中设置：

```env
CORS_ORIGINS=http://localhost,http://你的域名
```

### Ollama 超时

AI 接口在 Nginx 中已设置 120 秒超时。仍超时时可调大：

```env
OLLAMA_TIMEOUT_SECONDS=120
```

并确认模型已下载：

```bash
docker compose exec ollama ollama list
```

### 首次构建较慢

当前前端没有提交 `package-lock.json`，Dockerfile 使用 `npm install`。首次构建会下载依赖，后续会利用 Docker 缓存。
