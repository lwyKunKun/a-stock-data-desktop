<!--
  QuoteCard.vue —— 实时行情卡片
  展示：现价、涨跌幅、换手率、成交额、市值等（腾讯源，零 token）
-->
<script setup>
// props：后端快照里的 quote 对象 + 股票代码
const props = defineProps({
  quote: { type: Object, default: () => ({}) },
  code: { type: String, default: '' },
})

// 根据涨跌方向返回样式类（A股红涨绿跌）
function pctClass(v) {
  if (v > 0) return 'up'
  if (v < 0) return 'down'
  return 'flat'
}

// 成交额从「万元」换算成「亿元」显示，更直观
function toYi(wan) {
  return wan ? (wan / 1e4).toFixed(2) : '-'
}
</script>

<template>
  <div class="card" v-if="quote && quote.price">
    <!-- 标题行：股票名 + 代码 + 僵尸报价警告 -->
    <div class="card-title">
      {{ quote.name }}
      <span class="muted">{{ code }}</span>
      <span v-if="quote.is_stale" class="tag" style="color: var(--up)">
        ⚠️ {{ quote.stale_reason }}
      </span>
    </div>

    <!-- 现价 + 涨跌幅（大字突出） -->
    <div style="display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px">
      <span class="value" :class="pctClass(quote.change_pct)" style="font-size: 30px; font-weight: 700">
        {{ quote.price }}
      </span>
      <span :class="pctClass(quote.change_pct)" style="font-size: 16px; font-weight: 600">
        {{ quote.change_pct > 0 ? '+' : '' }}{{ quote.change_pct }}%
      </span>
    </div>

    <!-- 关键指标网格：手机2列 / 宽屏4列 -->
    <div class="grid">
      <div class="grid-item">
        <div class="label">换手率</div>
        <div class="value">{{ quote.turnover_pct }}%</div>
      </div>
      <div class="grid-item">
        <div class="label">成交额</div>
        <div class="value">{{ toYi(quote.amount_wan) }}亿</div>
      </div>
      <div class="grid-item">
        <div class="label">总市值</div>
        <div class="value">{{ quote.mcap_yi }}亿</div>
      </div>
      <div class="grid-item">
        <div class="label">量比</div>
        <div class="value">{{ quote.vol_ratio }}</div>
      </div>
      <div class="grid-item">
        <div class="label">最高</div>
        <div class="value up">{{ quote.high }}</div>
      </div>
      <div class="grid-item">
        <div class="label">最低</div>
        <div class="value down">{{ quote.low }}</div>
      </div>
      <div class="grid-item">
        <div class="label">涨停价</div>
        <div class="value up">{{ quote.limit_up }}</div>
      </div>
      <div class="grid-item">
        <div class="label">跌停价</div>
        <div class="value down">{{ quote.limit_down }}</div>
      </div>
    </div>
  </div>
</template>
