# Home Library 前端开发规范

## 1. 技术栈

推荐前端技术栈：

```text
Vue 3
TypeScript
Vite
Element Plus
Pinia
Vue Router
Axios
ECharts
```

## 2. 设计目标

家庭藏书管理系统应是一个安静、清晰、高效的管理工具。视觉风格应偏向信息管理界面，而不是营销页面。

原则：

- 第一屏直接进入工作界面。
- 重视搜索、筛选、录入和定位书籍。
- 桌面端优先保证表格和批量操作效率。
- 移动端优先保证查询、扫码扩展和快速查看位置。
- 不做大型装饰性页面。
- 控件密度适中，避免卡片嵌套卡片。

## 3. 目录结构

```text
frontend/src/
  api/
    client.ts
    auth.ts
    books.ts
    categories.ts
    locations.ts
    search.ts
    ai.ts
    stats.ts
  assets/
  components/
    book/
    category/
    location/
    ai/
    charts/
    common/
  layouts/
    AppLayout.vue
    AuthLayout.vue
  pages/
    dashboard/
    login/
    books/
    categories/
    locations/
    smart-import/
    borrow/
    reading/
    stats/
    users/
    settings/
  router/
    index.ts
  stores/
    auth.ts
    app.ts
  styles/
    variables.css
    global.css
  types/
    api.ts
    book.ts
    category.ts
    location.ts
    user.ts
```

## 4. 路由规划

| 路径 | 页面 | 权限 |
| --- | --- | --- |
| `/login` | 登录页 | 公开 |
| `/` | 首页仪表盘 | 登录 |
| `/books` | 图书列表 | 登录 |
| `/books/new` | 新增图书 | 登录 |
| `/books/:id` | 图书详情 | 登录 |
| `/books/:id/edit` | 编辑图书 | 登录 |
| `/smart-import` | 智能检索入库 | 登录 |
| `/categories` | 分类管理 | 管理员 |
| `/locations` | 位置管理 | 管理员 |
| `/borrow` | 借阅管理 | 登录 |
| `/reading` | 阅读笔记 | 登录 |
| `/stats` | 统计分析 | 登录 |
| `/users` | 用户管理 | 管理员 |
| `/settings` | 系统设置 | 管理员 |

路由守卫：

- 未登录访问受保护页面跳转 `/login`。
- 已登录访问 `/login` 跳转 `/`。
- 普通用户访问管理员页面显示无权限或跳转首页。

## 5. 布局

### 5.1 AppLayout

结构：

- 左侧导航
- 顶部工具栏
- 主内容区

导航项：

- 首页
- 藏书
- 智能入库
- 借阅
- 阅读笔记
- 统计
- 分类
- 位置
- 用户
- 设置

桌面端：

- 左侧固定导航
- 内容区最大宽度不强制收窄，表格页面使用全宽

移动端：

- 导航折叠为抽屉
- 图书列表切换为卡片列表
- 常用操作放入顶部工具区

### 5.2 AuthLayout

登录页居中展示登录表单，保留简洁品牌信息。

## 6. 页面规格

### 6.1 登录页

字段：

- 用户名
- 密码

行为：

- 登录成功后进入首页
- 登录失败展示错误
- Loading 状态防止重复提交

### 6.2 首页仪表盘

内容：

- 总藏书数
- 在架数量
- 借出数量
- 已读数量
- 最近入库
- 当前借出
- 分类分布
- 快速搜索
- 快速新增

### 6.3 图书列表页

视图：

- 表格视图
- 卡片视图

筛选：

- 关键词
- 分类
- 位置
- 状态
- 阅读状态
- 是否重点收藏
- 出版年份

操作：

- 新增图书
- 编辑
- 删除
- 批量修改分类
- 批量修改位置
- 批量导出

表格列：

- 封面
- 书名
- 作者
- 分类
- 位置
- 状态
- 阅读状态
- 评分
- 更新时间
- 操作

### 6.4 图书详情页

展示区域：

- 封面
- 书名、副标题
- 作者、译者、出版社、出版年份、ISBN
- 分类
- 位置
- 标签
- 状态
- 阅读状态
- 评分
- 简介
- 作者简介
- 借阅记录
- 阅读笔记

操作：

- 编辑
- 借出
- 归还
- 添加笔记
- AI 补全
- AI 分类推荐

### 6.5 图书表单

表单分组：

- 基础信息
- 出版信息
- 分类与标签
- 位置
- 阅读与收藏
- 备注

校验：

- 书名必填
- ISBN 格式提示但不强制
- 评分 1-5
- 出版年份为合理年份
- 页数大于 0
- 价格大于等于 0

### 6.6 智能检索入库页

流程：

1. 输入 ISBN、书名或书名加作者。
2. 展示外部候选结果。
3. 用户选择候选结果。
4. 生成图书草稿。
5. 调用 Ollama 推荐分类和标签。
6. 用户确认分类、位置和标签。
7. 入库。

状态：

- 搜索中
- 无结果
- 数据源部分失败
- Ollama 不可用
- 导入成功

### 6.7 分类管理页

内容：

- 分类树
- 分类详情
- 新增子分类
- 编辑分类
- 删除分类

限制：

- 系统分类显示锁定标识。
- 已使用分类删除时提示先迁移图书。

### 6.8 位置管理页

内容：

- 位置列表
- 按房间分组
- 新增位置
- 编辑位置
- 删除位置
- 查看该位置图书

位置显示格式：

```text
书房 / A 架 / 第 2 层 / 右侧
```

### 6.9 借阅管理页

内容：

- 当前借出
- 借阅历史
- 借出操作
- 归还操作
- 超期标识

### 6.10 阅读笔记页

内容：

- 按图书查看笔记
- 按时间查看笔记
- Markdown 编辑器
- 阅读进度
- 评分

### 6.11 统计分析页

图表：

- 分类分布
- 位置分布
- 阅读状态
- 年度入库趋势
- 作者排行

### 6.12 用户管理页

管理员页面：

- 用户列表
- 创建用户
- 修改角色
- 禁用用户

### 6.13 系统设置页

配置：

- Ollama 地址
- 默认模型
- 外部检索数据源开关
- 备份设置
- 系统信息

## 7. TypeScript 类型约定

### 7.1 分页

```ts
export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}
```

### 7.2 用户

```ts
export type UserRole = 'admin' | 'member' | 'guest'
export type UserStatus = 'active' | 'disabled'

export interface User {
  id: number
  username: string
  displayName: string
  email?: string
  role: UserRole
  status: UserStatus
}
```

### 7.3 图书

```ts
export type BookStatus = 'available' | 'borrowed' | 'lost' | 'pending' | 'gifted'
export type ReadStatus = 'unread' | 'reading' | 'read' | 'paused'

export interface BookListItem {
  id: number
  title: string
  subtitle?: string
  author?: string
  publisher?: string
  publishYear?: number
  isbn?: string
  coverUrl?: string
  category?: CategoryBrief
  location?: LocationBrief
  status: BookStatus
  readStatus: ReadStatus
  rating?: number
  isFavorite: boolean
  createdAt: string
  updatedAt: string
}
```

## 8. API 客户端约定

建议封装：

- `src/api/client.ts` 创建 axios 实例
- 请求拦截器自动附加 Token
- 响应拦截器统一处理错误
- 401 自动退出登录

错误展示：

- 表单错误显示在字段附近
- 普通接口错误用消息提示
- 删除、批量操作错误用对话框解释

## 9. 状态管理

Pinia store：

- `authStore`
  - token
  - currentUser
  - login
  - logout
  - fetchMe
- `appStore`
  - sidebarCollapsed
  - theme
  - globalLoading

业务数据优先由页面自行请求，MVP 不做复杂全局缓存。

## 10. UI 规范

颜色：

- 主色使用稳重蓝绿或中性蓝。
- 辅助色用于状态区分。
- 避免整站单一色系过重。

控件：

- 新增、保存、删除、导入、导出使用明确按钮。
- 编辑、删除、查看、借出、归还可使用图标加 Tooltip。
- 表格批量操作放在表格顶部工具栏。
- 状态使用 Tag。
- 分类使用树形选择。
- 位置使用级联或组合选择。

响应式：

- 大屏展示侧边栏和表格。
- 小屏图书列表默认卡片视图。
- 表单字段在小屏单列展示。

## 11. 验收标准

MVP 前端必须满足：

- 能登录、退出。
- 能进入首页。
- 能查看图书列表。
- 能新增、编辑、删除图书。
- 能管理分类和位置。
- 能通过智能检索导入图书草稿。
- 能展示 Ollama 分类建议。
- 能查看统计概览。
- 移动端无明显文本重叠。

