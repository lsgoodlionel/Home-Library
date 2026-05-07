# 部署指南

家藏书库基于 Docker，支持一键部署在主流服务器和 NAS 设备上。

---

## 前置要求

| 平台 | 要求 |
|------|------|
| **Ubuntu / Debian** | 64位系统，内存 ≥ 512MB |
| **CentOS / RHEL** | 64位系统，内存 ≥ 512MB |
| **macOS** | macOS 12+，Docker Desktop 已安装 |
| **Windows** | Windows 10/11 64位，Docker Desktop 已安装 |
| **群晖 NAS** | DSM 7.x，Container Manager 套件已安装 |

---

## Ubuntu / Debian（推荐）

**一行命令，自动安装 Docker 并部署：**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.sh)
```

**自定义端口和密码：**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.sh) \
  -p 8080 -u admin -w "MySecurePass123"
```

**参数说明：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-p` | HTTP 访问端口 | `80` |
| `-s` | JWT 密钥（留空自动生成） | 随机生成 |
| `-u` | 管理员用户名 | `admin` |
| `-w` | 管理员初始密码 | `Admin@123` |
| `-d` | 仅更新（跳过 Docker 安装） | — |

**更新到最新版本：**

```bash
bash ~/home-library/scripts/deploy.sh -d
```

---

## CentOS / RHEL

与 Ubuntu 命令完全相同，脚本自动识别发行版：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.sh)
```

---

## macOS

1. 安装 [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)，启动后确认 Docker 图标出现在菜单栏

2. 打开终端，运行：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.sh) -p 8080
```

> macOS 80 端口需要 root 权限，建议使用 8080

3. 访问 http://localhost:8080

---

## Windows

1. 安装 [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)，启动后确认系统托盘有 Docker 图标

2. 安装 [Git for Windows](https://git-scm.com/download/win)

3. 以**管理员身份**打开 PowerShell，运行：

```powershell
irm https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.ps1 | iex
```

或克隆后本地运行：

```powershell
git clone https://github.com/lsgoodlionel/Home-Library.git $env:USERPROFILE\home-library
cd $env:USERPROFILE\home-library
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\deploy.ps1 -Port 8080 -AdminUser admin -AdminPass "MyPass123"
```

4. 浏览器自动打开 http://localhost:8080

---

## 群晖 NAS（Synology）

### 方式一：Container Manager 图形界面（推荐）

1. **安装套件**：套件中心 → 搜索 `Container Manager` → 安装

2. **下载项目**：File Station 新建文件夹 `/docker/home-library`，上传以下两个文件：
   - `docker-compose.yml`
   - `.env`（复制自 `.env.example`，修改配置）

3. **配置 .env**（最少需改以下几项）：

```env
HTTP_PORT=8080
APP_SECRET_KEY=替换为随机长字符串
INITIAL_ADMIN_PASSWORD=你的密码
CORS_ORIGINS=http://你的NAS_IP:8080
```

4. **Container Manager** → 项目 → 新增 → 选择 `docker-compose.yml` → 创建

5. 访问 `http://NAS的IP:8080`

### 方式二：SSH 命令行（高级用户）

```bash
# 1. 启用 SSH：控制面板 → 终端机和SNMP → 启动SSH
# 2. 以管理员身份 SSH 登入

# 安装 git（如未安装）
sudo synopkg install git-server

# 部署
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.sh) \
  -p 8080 -d
```

> 群晖的 Docker 命令路径为 `/usr/local/bin/docker`，脚本已自动处理。

---

## 通用管理命令

以下命令在项目目录（默认 `~/home-library`）执行：

```bash
# 查看服务状态
docker compose ps

# 实时查看日志
docker compose logs -f

# 停止服务
docker compose down

# 重启服务
docker compose restart

# 更新到最新版本
git pull && docker compose build && docker compose up -d
```

---

## 数据备份

数据存储在 Docker 卷中，使用内置备份脚本：

```bash
bash ~/home-library/scripts/backup.sh
```

备份文件默认保存到 `~/home-library-backups/`。

**手动备份数据库：**

```bash
docker compose exec backend sqlite3 /data/home_library.sqlite3 \
  ".backup '/data/backup_$(date +%Y%m%d).sqlite3'"
```

---

## 常见问题

**Q：端口 80 被占用怎么办？**  
A：使用 `-p 8080` 换一个端口，或先停止占用 80 端口的服务（Nginx/Apache）。

**Q：群晖提示 `Permission denied`？**  
A：确保文件夹权限正确：`sudo chmod -R 755 /volume1/docker/home-library`

**Q：忘记管理员密码怎么办？**  
A：进入容器重置：
```bash
docker compose exec backend python3 -c "
from app.db.session import SessionLocal
from app.models.user import User
from passlib.context import CryptContext
db = SessionLocal()
pwd = CryptContext(schemes=['bcrypt']).hash('NewPass123')
db.query(User).filter_by(username='admin').update({'password_hash': pwd})
db.commit()
print('密码已重置为 NewPass123')
"
```

**Q：如何开启 AI 分类功能（Ollama）？**  
A：
```bash
# 启动 Ollama 服务
docker compose --profile ollama up -d

# 下载推荐模型（中文分类效果好）
docker compose exec ollama ollama pull qwen2.5
```

**Q：如何使用 HTTPS？**  
A：在应用前部署反向代理，推荐 [Nginx Proxy Manager](https://nginxproxymanager.com/) 或群晖的 `Application Portal`。
