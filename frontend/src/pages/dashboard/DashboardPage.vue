<template>
  <section class="dashboard-page">
    <el-row :gutter="16">
      <el-col :lg="6" :sm="12" :xs="24">
        <el-card shadow="never">
          <div class="metric-label">总藏书数</div>
          <div class="metric-value">--</div>
        </el-card>
      </el-col>
      <el-col :lg="6" :sm="12" :xs="24">
        <el-card shadow="never">
          <div class="metric-label">在架数量</div>
          <div class="metric-value">--</div>
        </el-card>
      </el-col>
      <el-col :lg="6" :sm="12" :xs="24">
        <el-card shadow="never">
          <div class="metric-label">借出数量</div>
          <div class="metric-value">--</div>
        </el-card>
      </el-col>
      <el-col :lg="6" :sm="12" :xs="24">
        <el-card shadow="never">
          <div class="metric-label">已读数量</div>
          <div class="metric-value">--</div>
        </el-card>
      </el-col>
    </el-row>

    <el-empty description="首页仪表盘占位，统计和图表将在后续任务中接入。" />
  </section>
</template>
