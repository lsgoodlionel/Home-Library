# Home Library Backend

后端计划使用 FastAPI、SQLAlchemy、Pydantic 和 SQLite 实现。

当前已包含任务 B 的 FastAPI 基础服务：配置读取、CORS、API 路由注册、健康检查、版本接口和统一错误响应雏形。

## 环境要求

- Python 3.11+

## 安装依赖

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 配置

服务默认读取当前目录下的 `.env`，环境变量前缀为 `HOME_LIBRARY_`。

常用配置：

```bash
HOME_LIBRARY_APP_NAME=Home Library
HOME_LIBRARY_APP_VERSION=0.1.0
HOME_LIBRARY_ENVIRONMENT=development
HOME_LIBRARY_API_PREFIX=/api
HOME_LIBRARY_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
HOME_LIBRARY_DATABASE_URL=sqlite:///./home_library.db
```

## 启动

```bash
cd backend
uvicorn app.main:app --reload
```

启动后可访问：

- `GET http://127.0.0.1:8000/api/health`
- `GET http://127.0.0.1:8000/api/version`
- `http://127.0.0.1:8000/docs`

## 测试

```bash
cd backend
pytest
```
