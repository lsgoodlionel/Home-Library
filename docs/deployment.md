# 部署指南

本文档介绍如何将 **Home Library** 部署到生产环境，包括 Docker Compose 标准部署、NAS 部署、数据持久化、备份恢复和 Ollama AI 集成。

---

## 目录

1. [快速开始（Docker Compose）](#快速开始docker-compose)
2. [NAS 部署（群晖 / QNAP）](#nas-部署)
3. [环境变量参考](#环境变量参考)
4. [数据持久化](#数据持久化)
5. [备份与恢复](#备份与恢复)
6. [Ollama AI 集成](#ollama-ai-集成)
7. [PostgreSQL（可选）](#postgresql可选)
8. [故障排查](#故障排查)

---

## 快速开始（Docker Compose）

### 前置条件

- Docker Engine ≥ 24.0
- Docker Compose Plugin v2（随 Docker Desktop 附带；Linux 单独安装：`apt install docker-compose-plugin`）

### 第一次部署

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/home-library.git
cd home-library

# 2. 复制并编辑环境变量
cp .env.example .env
# 必须修改的项：APP_SECRET_KEY、INITIAL_ADMIN_PASSWORD

# 3. 构建镜像并启动
docker compose up -d --build

# 4. 查看日志确认启动正常
docker compose logs -f
```

启动完成后，浏览器访问 `http://localhost`（或服务器 IP）即可看到登录页面。

默认管理员账号由 `.env` 中的 `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` 决定，**首次登录后请立即修改密码**。

### 日常管理命令

```bash
# 停止服务（保留数据卷）
docker compose down

# 更新到新版本
git pull
docker compose up -d --build

# 查看实时日志
docker compose logs -f backend
docker compose logs -f frontend

# 进入后端容器调试
docker compose exec backend bash
```

---

## NAS 部署

以群晖 DSM 7.x 为例（QNAP 操作类似）。

### 群晖 Container Manager（推荐）

1. 在 File Station 中创建目录，例如 `/volume1/docker/home-library`
2. 将项目文件上传到该目录（可用 SSH `scp` 或 File Station）
3. 编辑 `.env`，将 `DATABASE_URL` 改为绝对路径或保持使用 Docker 命名卷（推荐）
4. 打开 Container Manager → Project → 新建 → 从 `docker-compose.yml` 导入
5. 点击"构建并运行"

### 通过 SSH

```bash
# 在群晖上安装 Docker Compose Plugin
# （DSM 7.2+ 已内置，无需手动安装）

ssh admin@nas-ip
cd /volume1/docker/home-library
docker compose up -d --build
```

### 端口映射

默认监听 `80` 端口。如需更改（避免与 DSM Web 界面冲突），在 `.env` 中设置：

```
HTTP_PORT=8080
```

然后通过 `http://nas-ip:8080` 访问。

---

## 环境变量参考

所有变量均在项目根目录的 `.env` 文件中配置。以下列出 Docker 部署中的关键项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_SECRET_KEY` | `change-this-secret-in-production` | **必须修改**，JWT 签名密钥，建议 32 字节以上随机串 |
| `INITIAL_ADMIN_USERNAME` | `admin` | 首次初始化时创建的管理员账号 |
| `INITIAL_ADMIN_PASSWORD` | `change-me` | **必须修改**，首次初始化的管理员密码 |
| `DATABASE_URL` | `sqlite:////data/home_library.sqlite3` | Docker 内数据库路径，使用命名卷时无需修改 |
| `CORS_ORIGINS` | `http://localhost` | 前端域名，多个用逗号分隔 |
| `HTTP_PORT` | `80` | Nginx 对外监听端口 |
| `VITE_APP_TITLE` | `家藏书库` | 网页标题（构建时写入，运行时不生效） |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama 服务地址 |
| `OLLAMA_DEFAULT_MODEL` | `qwen2.5` | 默认 AI 模型 |
| `OLLAMA_OPTIONAL` | `true` | `true` = Ollama 不可用时 AI 功能降级而非崩溃 |
| `LOG_LEVEL` | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |

生成安全密钥：

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 数据持久化

项目使用三个 Docker 命名卷：

| 卷名 | 挂载点（容器内） | 内容 |
|------|----------------|------|
| `db_data` | `/data`（后端） | SQLite 数据库文件 |
| `uploads` | `/app/uploads`（后端）、`/app/uploads`（Nginx 只读） | 封面图片及上传文件 |
| `backups` | `/app/backups`（后端） | 备份文件 |

命名卷的物理路径通常位于 `/var/lib/docker/volumes/`，无需手动管理路径。

### 迁移数据到新服务器

```bash
# 在旧服务器上导出卷
docker run --rm -v home-library_db_data:/data -v $(pwd):/out \
  alpine tar -czf /out/db_data.tar.gz -C /data .

docker run --rm -v home-library_uploads:/uploads -v $(pwd):/out \
  alpine tar -czf /out/uploads.tar.gz -C /uploads .

# 将压缩包传输到新服务器后，在新服务器上导入
docker run --rm -v home-library_db_data:/data -v $(pwd):/in \
  alpine tar -xzf /in/db_data.tar.gz -C /data

docker run --rm -v home-library_uploads:/uploads -v $(pwd):/in \
  alpine tar -xzf /in/uploads.tar.gz -C /uploads
```

---

## 备份与恢复

### 手动备份

```bash
# 在宿主机上执行（备份文件写入 backups 卷）
docker compose exec backend /app/scripts/backup.sh
```

备份文件将写入 `backups` 卷，命名格式：
- `db_YYYYMMDD_HHMMSS.sqlite3` — 数据库快照
- `uploads_YYYYMMDD_HHMMSS.tar.gz` — 上传文件压缩包

默认保留最近 7 天的备份（通过 `KEEP_DAYS` 环境变量调整）。

### 定时备份（cron）

在宿主机上添加 crontab（每天凌晨 3:00 备份）：

```bash
crontab -e
# 添加以下行（根据实际项目路径修改）：
0 3 * * * cd /path/to/home-library && docker compose exec -T backend /app/scripts/backup.sh >> /var/log/home-library-backup.log 2>&1
```

### 恢复数据库

```bash
# 停止后端服务
docker compose stop backend

# 找到最新备份文件（在 backups 卷内）
docker run --rm -v home-library_backups:/backups alpine ls /backups

# 从备份恢复（替换 TIMESTAMP 为实际时间戳）
docker run --rm \
  -v home-library_db_data:/data \
  -v home-library_backups:/backups \
  alpine cp /backups/db_YYYYMMDD_HHMMSS.sqlite3 /data/home_library.sqlite3

# 重启后端
docker compose start backend
```

### 恢复上传文件

```bash
docker run --rm \
  -v home-library_uploads:/uploads \
  -v home-library_backups:/backups \
  alpine sh -c "cd /uploads && tar -xzf /backups/uploads_YYYYMMDD_HHMMSS.tar.gz --strip-components=1"
```

---

## Ollama AI 集成

Ollama 服务以可选 profile 提供，默认不启动。

### 启用 Ollama 服务

```bash
# 同时启动 Ollama 容器
docker compose --profile ollama up -d --build
```

首次启动后，需要拉取模型（以 `qwen2.5` 为例）：

```bash
docker compose exec ollama ollama pull qwen2.5
```

拉取完成后，应用的书籍分类和智能推荐功能即可使用。

### GPU 加速（NVIDIA）

如果宿主机已安装 NVIDIA 驱动和 `nvidia-container-toolkit`，取消 `docker-compose.yml` 中 `ollama` 服务的 GPU 注释：

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

### 使用宿主机已运行的 Ollama

如果 Ollama 已在宿主机上以 `http://localhost:11434` 运行，在 `.env` 中修改：

```
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

（Linux 上需要在 `docker-compose.yml` 的 `backend` 服务中添加 `extra_hosts: ["host.docker.internal:host-gateway"]`）

---

## PostgreSQL（可选）

SQLite 适合家庭/小团队使用。如需使用 PostgreSQL（多并发写入、更大数据量），启用 postgres profile：

```bash
# .env 中设置数据库连接串
DATABASE_URL=postgresql+psycopg2://library:change-me@postgres:5432/home_library
POSTGRES_USER=library
POSTGRES_PASSWORD=change-me    # 必须修改
POSTGRES_DB=home_library

# 启动 postgres profile
docker compose --profile postgres up -d --build
```

注意：切换数据库后需重新初始化，现有 SQLite 数据需要手动迁移。

---

## 故障排查

### 容器启动失败

```bash
# 查看详细日志
docker compose logs backend
docker compose logs frontend
```

### 数据库迁移报错

```bash
# 手动运行迁移
docker compose exec backend alembic upgrade head
```

### 无法访问 API（502 Bad Gateway）

1. 确认后端容器正常运行：`docker compose ps`
2. 查看后端日志：`docker compose logs backend`
3. 确认健康检查通过（`STATUS` 应为 `healthy`）

### 上传文件 404

Nginx 通过 `/uploads/` 路径直接提供文件服务，后端和 Nginx 共享同一个 `uploads` 卷。如果文件仍然 404，检查卷挂载：

```bash
docker compose exec frontend ls /app/uploads
```

### 重置管理员密码

```bash
docker compose exec backend python -c "
from app.db.session import SessionLocal
from app.models import User
from app.core.security import get_password_hash
db = SessionLocal()
u = db.query(User).filter(User.username == 'admin').first()
u.hashed_password = get_password_hash('new-password')
db.commit()
print('密码已重置')
"
```

### 完全重置（删除所有数据）

```bash
# ⚠ 不可撤销！删除所有数据卷
docker compose down -v
docker compose up -d --build
```
