<!--
  ReportList.vue —— 已生成报告列表（独立的侧边导航模块，与 A股数据看板 同级）
  数据源为后端 SQLite 索引（backend/data/reports_index.db），首次查询自动回填历史报告。
  支持按日期、行业筛选与服务端分页；点击股票名称进入对应日期的完整报告详情。
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { zhCN } from "date-fns/locale";
import { VueDatePicker } from "@vuepic/vue-datepicker";
import "@vuepic/vue-datepicker/dist/main.css";
import { fetchReportList } from "../api/client";
import type {
  ReportListItem,
  ReportListResponse,
  ReportSelection,
  ReportSource,
  Market,
} from "../api/types";
import { errorMessage, isAbortError } from "../utils/errors";

const emit = defineEmits<{ select: [report: ReportSelection] }>();
const pageSize = 10;

const data = ref<ReportListResponse | null>(null);
const filterDate = ref<string>("");
const filterIndustry = ref<string>("");
const filterMarket = ref<Market | "">("");
const currentPage = ref<number>(1);
const loading = ref<boolean>(false);
const error = ref<string>("");
let controller: AbortController | null = null;

interface PageItem {
  key: string;
  label: string;
  page?: number;
}

const pageItems = computed<PageItem[]>(() => {
  const total = data.value?.total_pages ?? 0;
  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => ({
      key: `page-${index + 1}`,
      label: String(index + 1),
      page: index + 1,
    }));
  }

  const pages = [...new Set([
    1,
    total,
    currentPage.value - 1,
    currentPage.value,
    currentPage.value + 1,
  ].filter((page) => page >= 1 && page <= total))].sort((a, b) => a - b);

  const items: PageItem[] = [];
  pages.forEach((page, index) => {
    if (index > 0 && page - pages[index - 1] > 1) {
      items.push({ key: `ellipsis-${pages[index - 1]}`, label: "…" });
    }
    items.push({ key: `page-${page}`, label: String(page), page });
  });
  return items;
});

async function load(): Promise<void> {
  controller?.abort();
  const requestController = new AbortController();
  controller = requestController;
  loading.value = true;
  error.value = "";
  try {
    const response = await fetchReportList({
      date: filterDate.value,
      industry: filterIndustry.value,
      market: filterMarket.value || undefined,
      page: currentPage.value,
      pageSize,
    }, requestController.signal);
    if (controller !== requestController) return;
    data.value = response;
    currentPage.value = response.page;
  } catch (caught: unknown) {
    if (!isAbortError(caught)) error.value = errorMessage(caught);
  } finally {
    if (controller === requestController) {
      controller = null;
      loading.value = false;
    }
  }
}

function applyFilters(): void {
  currentPage.value = 1;
  void load();
}

function goToPage(page: number): void {
  const total = data.value?.total_pages ?? 0;
  if (loading.value || page < 1 || page > total || page === currentPage.value) return;
  currentPage.value = page;
  void load();
}

function select(item: ReportListItem): void {
  emit("select", { code: item.code, date: item.date, name: item.name, market: item.market ?? "CN" });
}

function sourceLabel(source: ReportSource | null | undefined): string {
  if (source === "desktop") return "桌面端";
  if (source === "web") return "Web 端";
  return "未知";
}

function changePctClass(value: number | null): string {
  if (value === null || value === undefined) return "";
  return value >= 0 ? "is-up" : "is-down";
}

function formatPct(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

onMounted(load);
onBeforeUnmount(() => controller?.abort());
defineExpose({ reload: load });
</script>

<template>
  <header class="report-list-head">
    <div class="title">
      <h1 style="font-size: 20px">📄 已生成的报告</h1>
      <p class="muted report-list-subtitle">SQLite 索引 · 点击股票名称查看对应日期的完整报告</p>
    </div>
    <button class="btn btn-ghost" :disabled="loading" @click="load">刷新</button>
  </header>

  <section class="card report-list">
    <div class="report-list-filters">
      <label>
        日期
        <VueDatePicker
          v-model="filterDate"
          class="report-date-picker"
          model-type="yyyy-MM-dd"
          format="yyyy-MM-dd"
          :locale="zhCN"
          placeholder="全部日期"
          auto-apply
          :enable-time-picker="false"
          :clearable="true"
          @update:model-value="applyFilters"
        />
      </label>
      <label>
        行业
        <select v-model="filterIndustry" class="input" @change="applyFilters">
          <option value="">全部行业</option>
          <option
            v-for="industry in data?.industries ?? []"
            :key="industry"
            :value="industry"
          >
            {{ industry }}
          </option>
        </select>
      </label>
      <label>
        市场
        <select v-model="filterMarket" class="input" @change="applyFilters">
          <option value="">全部市场</option>
          <option value="CN">A股</option>
          <option value="US">美股</option>
        </select>
      </label>
      <span v-if="data" class="muted">共 {{ data.total }} 份</span>
    </div>

    <div v-if="error" class="error-box">{{ error }}</div>

    <div v-if="data && !data.items.length && !loading" class="muted report-list-empty">
      暂无符合条件的报告，先在「A股数据看板」中搜索股票生成一份
    </div>

    <div v-if="data && data.items.length" class="report-list-table-wrap">
      <table class="report-list-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>股票</th>
            <th>行业</th>
            <th>生成端</th>
            <th>现价</th>
            <th>涨跌幅</th>
            <th>PE(TTM)</th>
            <th>模型</th>
            <th>Tokens</th>
            <th>耗时</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in data.items"
            :key="`${item.market ?? 'CN'}-${item.date}-${item.code}`"
            @click="select(item)"
          >
            <td class="muted">{{ item.date }}</td>
            <td>
              <button class="report-name-link" type="button" @click.stop="select(item)">
                <strong>{{ item.name || item.code }}</strong>
                <span class="muted"> {{ item.code }} {{ (item.market ?? "CN") === "US" ? "美股" : "" }}</span>
              </button>
            </td>
            <td>{{ item.industry || "—" }}</td>
            <td>{{ sourceLabel(item.source) }}</td>
            <td>{{ item.price ?? "—" }}</td>
            <td :class="changePctClass(item.change_pct)">
              {{ formatPct(item.change_pct) }}
            </td>
            <td>{{ item.pe_ttm ?? "—" }}</td>
            <td class="muted">{{ item.model }}</td>
            <td class="muted">{{ item.total_tokens }}</td>
            <td class="muted">{{ item.duration_s }}s</td>
          </tr>
        </tbody>
      </table>
    </div>

    <nav
      v-if="data && data.items.length"
      class="report-pagination"
      aria-label="报告列表分页"
    >
      <span class="page-status">第 {{ currentPage }} / {{ data.total_pages }} 页</span>
      <button
        type="button"
        class="page-button"
        :disabled="loading || currentPage === 1"
        @click="goToPage(currentPage - 1)"
      >
        上一页
      </button>
      <template v-for="item in pageItems" :key="item.key">
        <span v-if="item.page === undefined" class="page-ellipsis">{{ item.label }}</span>
        <button
          v-else
          type="button"
          class="page-button page-number"
          :class="{ active: item.page === currentPage }"
          :disabled="loading"
          :aria-current="item.page === currentPage ? 'page' : undefined"
          @click="goToPage(item.page)"
        >
          {{ item.label }}
        </button>
      </template>
      <button
        type="button"
        class="page-button"
        :disabled="loading || currentPage === data.total_pages"
        @click="goToPage(currentPage + 1)"
      >
        下一页
      </button>
    </nav>
  </section>
</template>

<style scoped>
.report-list {
  padding: 16px 20px;
}
.report-list-head {
  padding: 8px 4px 16px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.report-list-subtitle {
  font-size: 12px;
}
.report-list-filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 16px;
  margin: 12px 0;
  font-size: 12px;
  color: var(--text-light);
}
.report-list-filters label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.report-list-filters select {
  width: auto;
  padding: 4px 8px;
  font-size: 12px;
}
.report-date-picker {
  width: 150px;
  --dp-font-size: 12px;
  --dp-input-padding: 5px 28px 5px 30px;
  --dp-border-radius: 6px;
  --dp-background-color: var(--control-bg);
  --dp-text-color: var(--text);
  --dp-hover-color: var(--primary-soft);
  --dp-hover-text-color: var(--primary);
  --dp-hover-icon-color: var(--primary);
  --dp-primary-color: var(--primary);
  --dp-primary-text-color: var(--on-primary);
  --dp-secondary-color: var(--text-light);
  --dp-border-color: var(--border);
  --dp-menu-border-color: var(--border);
  --dp-border-color-hover: var(--primary);
  --dp-border-color-focus: var(--primary);
  --dp-disabled-color: var(--surface-muted);
  --dp-disabled-color-text: var(--text-light);
  --dp-icon-color: var(--text-light);
  --dp-scroll-bar-background: var(--scrollbar-track);
  --dp-scroll-bar-color: var(--scrollbar-thumb);
  --dp-danger-color: var(--danger-text);
  --dp-success-color: var(--success-text);
  --dp-highlight-color: var(--primary-soft);
}
.report-list-empty {
  padding: 18px 0;
  text-align: center;
}
.report-list-table-wrap {
  overflow-x: auto;
}
.report-list-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.report-list-table th,
.report-list-table td {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  text-align: left;
  white-space: nowrap;
}
.report-list-table th {
  color: var(--text-light);
  font-size: 12px;
  font-weight: 500;
  border-top: none;
}
.report-list-table tbody tr {
  cursor: pointer;
}
.report-list-table tbody tr:hover {
  background: var(--primary-soft);
}
.report-name-link {
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.report-name-link:hover strong,
.report-name-link:focus-visible strong {
  color: var(--primary);
}
.report-name-link:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 3px;
}
.report-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 16px;
}
.page-status {
  margin-right: 6px;
  color: var(--text-light);
  font-size: 12px;
  white-space: nowrap;
}
.page-button {
  min-width: 34px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--control-bg);
  color: var(--text);
  font-family: inherit;
  cursor: pointer;
}
.page-button:hover:not(:disabled),
.page-button.active {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-soft);
}
.page-button.active {
  font-weight: 600;
}
.page-button:disabled {
  color: var(--text-light);
  cursor: not-allowed;
  opacity: 0.55;
}
.page-ellipsis {
  min-width: 20px;
  text-align: center;
  color: var(--text-light);
}
.is-up {
  color: var(--up);
}
.is-down {
  color: var(--down);
}

@media (max-width: 760px) {
  .report-list-filters label {
    width: 100%;
  }
  .report-date-picker,
  .report-list-filters select {
    flex: 1;
    width: auto;
  }
}
</style>
