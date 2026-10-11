<!--
  FundFlowCard.vue —— 资金流卡片
  展示：当日分钟级主力净流入 + 日级 5/20/60 日聚合（后端已聚合，不给逐日明细）
  东财被风控时分钟级会显示降级提示，日级自动走新浪备胎
-->
<script setup>
const props = defineProps({
  minute: { type: Object, default: () => ({}) },
  daily: { type: Object, default: () => ({}) },
})

// 金额（元）→ 亿元，保留 2 位；正数带 + 号
function toYi(v) {
  if (v == null) return '-'
  const yi = v / 1e8
  return (yi > 0 ? '+' : '') + yi.toFixed(2) + '亿'
}

// 资金流入红色、流出绿色（与涨跌同色系，符合A股习惯）
function flowClass(v) {
  if (v > 0) return 'up'
  if (v < 0) return 'down'
  return 'flat'
}
</script>

<template>
  <div class="card">
    <div class="card-title">💸 资金流向</div>

    <!-- 当日分钟级 -->
    <div style="margin-bottom: 12px">
      <div class="label muted" style="font-size: 12px; color: var(--text-light)">当日主力净流入</div>
      <!-- 正常：显示金额 + 信号；降级：显示后端返回的提示 -->
      <div v-if="minute && minute.main_net_total_wan != null"
           class="value" :class="flowClass(minute.main_net_total)" style="font-size: 20px">
        {{ minute.main_net_total > 0 ? '+' : '' }}{{ minute.main_net_total_wan }}万
        <span class="tag" :style="{ color: minute.signal === 'bullish' ? 'var(--up)' : 'var(--down)' }">
          {{ minute.signal === 'bullish' ? '流入' : '流出' }}
        </span>
      </div>
      <div v-else class="muted">{{ minute?.note || '暂无当日分钟数据' }}</div>
    </div>

    <!-- 日级 5/20/60 日窗口 -->
    <template v-if="daily && daily.windows && daily.windows['5d'] != null">
      <div class="grid" style="grid-template-columns: repeat(3, 1fr)">
        <div class="grid-item">
          <div class="label">近5日主力</div>
          <div class="value" :class="flowClass(daily.windows['5d'])" style="font-size: 15px">
            {{ toYi(daily.windows['5d']) }}
          </div>
        </div>
        <div class="grid-item">
          <div class="label">近20日主力</div>
          <div class="value" :class="flowClass(daily.windows['20d'])" style="font-size: 15px">
            {{ toYi(daily.windows['20d']) }}
          </div>
        </div>
        <div class="grid-item">
          <div class="label">近60日主力</div>
          <div class="value" :class="flowClass(daily.windows['60d'])" style="font-size: 15px">
            {{ toYi(daily.windows['60d']) }}
          </div>
        </div>
      </div>
      <!-- 趋势 + 数据源标注（备胎源明确告知用户） -->
      <div class="muted" style="margin-top: 8px">
        趋势：{{ daily.trend }}
        <span v-if="daily.source === 'sina_backup'">· 数据源：新浪备胎（东财临时风控）</span>
        <span v-else>· 数据源：东财</span>
      </div>
    </template>
    <div v-else class="muted">{{ daily?.note || '暂无日级资金流数据' }}</div>
  </div>
</template>
