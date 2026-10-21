# 部署与运维

本文档说明 Home Library 的 Docker Compose 部署、NAS 部署、数据持久化、备份恢复和常见故障处理。

## 快速启动

前提条件：

- Docker Engine 24+
- Docker Compose v2
- 可选：本机、容器内或 Cloudflare Access 保护的远程 Ollama

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
| `PYTHON_PACKAGE_INDEX_URL` | `https://pypi.org/simple` | 仅用于 Docker 后端构建；构建前在实际环境测速并按次覆盖，官方源保留为默认回退 |
| `DATABASE_URL` | `sqlite:////data/home_library.sqlite3` | 数据库连接 |
| `CORS_ORIGINS` | `http://localhost` | 允许访问的前端地址 |
| `INITIAL_ADMIN_USERNAME` | `admin` | 首次初始化管理员 |
| `INITIAL_ADMIN_PASSWORD` | `change-me` | 首次初始化管理员密码 |
| `OLLAMA_ENABLED` | `false` | AI 总开关，关闭时不发出 Ollama 请求 |
| `OLLAMA_BASE_URL` | `https://openclaw.lsgood.cn` | 后端直接运行时的本地或远程地址 |
| `OLLAMA_TRUSTED_BASE_URL` | `https://openclaw.lsgood.cn` | 后端与 smoke 允许携带 Access 凭据的独立 HTTPS 信任 Origin |
| `DOCKER_OLLAMA_BASE_URL` | `https://openclaw.lsgood.cn` | Compose 后端容器实际使用的地址 |
| `OLLAMA_DEFAULT_MODEL` | `qwen3.5:4b` | 默认模型 |
| `OLLAMA_CONNECT_TIMEOUT_SECONDS` | `20` | 建立连接超时秒数 |
| `OLLAMA_READ_TIMEOUT_SECONDS` | `180` | 模型读取/生成超时秒数 |
| `OLLAMA_VERIFY_TLS` | `true` | 验证 HTTPS 证书 |
| `OLLAMA_CF_ACCESS_CLIENT_ID` | 空 | Access 服务令牌 ID，环境引导 |
| `OLLAMA_CF_ACCESS_CLIENT_SECRET` | 空 | Access 服务令牌 Secret，环境引导 |
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

### 使用 Cloudflare Access 远程 Ollama

当前默认远程地址是 `https://openclaw.lsgood.cn`，`ollama.lsgood.cn` 当前会被 Access 拒绝，不能作为默认地址。生产服务器 `.env` 示例：

```env
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=https://openclaw.lsgood.cn
OLLAMA_TRUSTED_BASE_URL=https://openclaw.lsgood.cn
DOCKER_OLLAMA_BASE_URL=https://openclaw.lsgood.cn
OLLAMA_DEFAULT_MODEL=qwen3.5:4b
OLLAMA_CONNECT_TIMEOUT_SECONDS=20
OLLAMA_READ_TIMEOUT_SECONDS=180
OLLAMA_VERIFY_TLS=true
OLLAMA_CF_ACCESS_CLIENT_ID=
OLLAMA_CF_ACCESS_CLIENT_SECRET=
```

两项 Access 凭据可同时由服务器秘密管理填入，或由管理员在 HTTPS 设置页经双重认证后成对写入后端加密存储，不得写入仓库、前端 `VITE_*`、镜像 build args 或运维日志。后端只在请求 HTTPS origin 与独立的 `OLLAMA_TRUSTED_BASE_URL` 完全一致时附加 Access headers；HTTP、本地名称和 IP 地址始终不携带凭据。smoke 脚本独立比较 `OLLAMA_BASE_URL` 与 `OLLAMA_TRUSTED_BASE_URL`：协议、主机和有效端口必须一致，HTTP 80/HTTPS 443 的显式端口与默认端口等价，路径可不同；用户信息、控制字符、非 HTTP(S) 或第三方 Origin 会在调用 curl 前被拒绝。

确认环境中已经安全注入两项凭据后，可执行只读 smoke；脚本不会调用生成接口，也不会打印凭据或响应正文：

```bash
bash scripts/ollama-cloudflare-smoke-test.sh
```

发布 workflow 只接受 `vMAJOR.MINOR.PATCH` 或带合法 prerelease 的 Git tag，例如
`v1.2.3`、`v1.2.3-rc.1`。共享 `prepare` job 会移除前导 `v`：Git tag
`v1.2.3-rc.1` 对应应用 `APP_VERSION=1.2.3-rc.1` 和两个 GHCR 镜像 tag
`1.2.3-rc.1`。因此现有 `VERSION=1.2.3` Compose 部署和
`bash scripts/update.sh --version 1.2.3` 保持可用。解析结果最长 128 个字符，非法或
超长 `v*` tag 会在构建镜像前失败，版本字符串不会被 Docker metadata 再次改写。

管理员还可以在“设置 > AI 模型配置”执行连接测试。普通测试只读；生成测试需要前端二次确认。AI 故障只影响 AI 推荐，核心图书功能继续可用。

### 使用宿主机 Ollama

macOS / Windows Docker Desktop 可使用：

```env
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Linux 服务器可改为宿主机网关 IP，或使用 Compose 内置 profile。

### 使用 Compose Ollama

```bash
docker compose --profile ollama up -d
docker compose exec ollama ollama pull qwen3.5:4b
```

同时将 `.env` 调整为：

```env
DOCKER_OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_ENABLED=true
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

健康检查的三个探针会并发执行；显式生成测试也会与这些探针并发，因此端点总预算接近单次后端读取超时。默认超时层级为：后端读取 180 秒、前端健康/生成请求 240 秒、Nginx 发送/读取 300 秒。
`OLLAMA_READ_TIMEOUT_SECONDS` 必须严格小于前端 `aiHealth` 和 `aiGeneration`
上限，而前端上限必须严格小于 Nginx `proxy_send_timeout` 和
`proxy_read_timeout`，以便后端先返回稳定的 `AI_RESPONSE_TIMEOUT` 错误。
需要调整时必须保持这一严格大小关系，例如：

```env
OLLAMA_CONNECT_TIMEOUT_SECONDS=20
OLLAMA_READ_TIMEOUT_SECONDS=180
```

并确认模型已下载：

```bash
docker compose exec ollama ollama list
```

### 首次构建较慢

当前前端没有提交 `package-lock.json`，Dockerfile 使用 `npm install`。首次构建会下载依赖，后续会利用 Docker 缓存。


### 服务器 AI 配置的引导与恢复

1. 首次部署先配置稳定 `APP_SECRET_KEY`、初始管理员和 `UPGRADE_PASSWORD`。应用密钥至少 32 个 UTF-8 字节，并排除已知开发默认值、本页公开示例及其前后空白变体；使用秘密管理生成的随机值，禁止复制文档占位符。此密钥同时涉及登录签名和 Access 加密，备份时与数据库分别安全保存。
2. 启用 HTTPS 后登录“设置 > 服务器 AI 配置”。保存/恢复需要当前管理员密码与服务器升级专用密码。`UPGRADE_PASSWORD` 未配置时，先通过受保护的服务器配置完成引导；它不是数据库可覆盖的项目。
3. 数据库覆盖优先于 `OLLAMA_*` 环境变量及程序默认值。保存后立即生效，无需重启；之后修改环境变量不会替代已保存覆盖。Access 两项留空会保留，显式勾选清除才删除。保存成功后连接测试失败仍表示配置已保存，可修正网络/令牌后重试测试。
4. “恢复环境变量配置”删除全局覆盖，保留所有账号偏好。环境内仍有凭据时，恢复后将重新使用它们。恢复前确认环境设置，避免把“恢复”误认为关闭 AI 或清除环境凭据。
5. 更换 `APP_SECRET_KEY`、密文损坏或仅恢复数据库而未恢复匹配密钥，会使旧 Access 凭据不可用。没有明文导出或自动换钥迁移；先恢复匹配密钥，或重新录入完整凭据对。弱密钥下允许读取非敏感状态，拒绝保存新凭据；AI 失败不阻断登录、图书、借阅等模块。

并发保存或恢复遇到 HTTP 409 时，先重新读取服务器配置，再确认本次完整变更；不要自动重发旧配置。数据库故障返回脱敏 500 并尝试回滚，回滚自身失败时使 Session 失效；若底层数据库连接同时无法回滚/失效，需要运维确认事务结果后再重试，不能把失败响应当作已保存。

**Docker HTTPS 代理接入：** 默认 Compose 发布 HTTP 80，不能直接满足远程敏感配置写入要求。部署时让 HTTPS 终止代理向后端传递准确的 `X-Forwarded-Proto: https`，在后端环境 `SERVER_CONFIG_TRUSTED_PROXY_IPS` 中仅登记后端实际看到的代理地址。为该代理分配经网络清单确认不冲突的固定地址，并在 Compose 的用户自定义 network/IPAM 配置中保持一致；不要把整个私有网段或任意客户端加入信任。该环境变量通过现有 `env_file` 传入，生产/测试使用各自地址。若有多级代理，应逐跳核对实际 backend peer 和覆盖头行为；浏览器地址是 `localhost` 不代表 Docker 内请求来源是回环。

生产保持 `verify_tls=true`。受控自签名验收环境可在明确风险确认后临时关闭；本次隔离验收使用回环 HTTPS 端口、独立网络和数据库，不是生产部署模板。只读远程 smoke 读取环境引导参数，不能证明数据库覆盖已正确应用；数据库配置应通过登录后的只读测试/API 验证。没有授权的真实 Cloudflare Service Token 时，报告外部验证未执行。
