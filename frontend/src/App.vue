<!--
  App.vue —— 应用主组件
  职责：搜索框 + 状态管理（当前股票、加载状态）+ 编排各展示组件
  数据流：输入代码 → 归一化校验拿到股票代码 → 全维度数据面板自动采集展示
          （全部十二章数据，零 token）→ 下方可选 AI 全维度分析（按次计费）
  持久化：上次查询代码与查询历史存 localStorage，刷新页面自动恢复
-->
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchSnapshot } from "./api/client";
import { errorMessage } from "./utils/errors";
import { addHistory, loadLastQuery, saveLastQuery } from "./utils/storage";
import FullDataPanel from "./components/FullDataPanel.vue";
import AiReport from "./components/AiReport.vue";
import HistoryBar from "./components/HistoryBar.vue";
import DataSourceBanner from "./components/DataSourceBanner.vue";
import ReportList from "./components/ReportList.vue";

const codeInput = ref<string>("");
const currentCode = ref<string>("");
const loading = ref<boolean>(false);
const error = ref<string>("");

const historyBar = ref<InstanceType<typeof HistoryBar> | null>(null);

async function search(code?: string): Promise<void> {
  const target = (code || codeInput.value).trim();
  if (!target) return;
  loading.value = true;
  error.value = "";
  currentCode.value = "";
  try {
    const snapshot = await fetchSnapshot(target);
    currentCode.value = snapshot.code;
    codeInput.value = snapshot.code;
    // 持久化：记录上次查询与历史记录（股票名从行情快照里取，取不到就只存代码）
    saveLastQuery(snapshot.code);
    const quote = snapshot.quote as { name?: string } | undefined;
    addHistory(snapshot.code, quote?.name ?? "");
    historyBar.value?.refresh();
  } catch (caught: unknown) {
    error.value = errorMessage(caught);
  } finally {
    loading.value = false;
  }
}

// 刷新页面后恢复上次的查询（后端按日缓存，恢复后面板秒开）
onMounted(() => {
  const last = loadLastQuery();
  if (last) void search(last);
});
</script>

<template>
  <div class="container">
    <!-- 顶部标题 -->
    <header style="padding: 8px 4px 16px">
      <h1 style="font-size: 20px">📈 A股数据看板</h1>
      <p class="muted">普通查询零成本 · 全维度数据全量展示 · AI 分析按次计费</p>
    </header>

    <!-- 数据源更新提醒 -->
    <DataSourceBanner />

    <!-- 搜索区 -->
    <div class="card">
      <div style="display: flex; gap: 8px">
        <input
          v-model="codeInput"
          class="input"
          placeholder="输入股票代码，如 600519（支持 sh600519 / 600519.SH）"
          @keyup.enter="search()"
        />
        <button class="btn btn-primary" :disabled="loading" @click="search()">
          查询
        </button>
      </div>
      <!-- 查询历史 -->
      <HistoryBar ref="historyBar" @select="search" />
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-box">❌ {{ error }}</div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading">
      <span class="spinner"></span>正在校验股票代码…
    </div>

    <!-- 数据展示区：全维度数据面板（自动采集全部十二章）+ AI 分析 -->
    <template v-if="currentCode && !loading">
      <FullDataPanel :code="currentCode" />

      <!-- AI 分析：独立组件，可自动或手动触发 -->
      <AiReport :code="currentCode" />
    </template>

    <!-- 已生成报告归档：按日期/行业筛选，点击行跳回该股票 -->
    <ReportList @select="search" />
  </div>
</template>
