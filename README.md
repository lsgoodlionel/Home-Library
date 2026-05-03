# Home Library

家庭藏书管理系统开发方案与并行开发计划。

本仓库当前用于沉淀项目方案、系统设计和任务分工，后续可按计划逐步实现前端、后端、数据库、Ollama 智能能力、部署与测试。

## 文档

- [完整 Web 应用开发方案](docs/home-library-web-app-plan.md)
- [并行开发任务分工计划](docs/parallel-development-plan.md)
- [API 契约](docs/api-contract.md)
- [数据库设计](docs/database-schema.md)
- [前端开发规范](docs/frontend-spec.md)
- [第一批并行任务领取说明](docs/first-wave-task-briefs.md)

## 目录结构

```text
Home-Library/
  docs/
  backend/
  frontend/
  docker/
```

## 项目定位

Home Library 是一个面向家庭场景的轻量级藏书管理系统，参考中图法做简化分类，支持图书位置管理、用户登录、网络检索补全、本地 Ollama 模型辅助分类与标签生成。
