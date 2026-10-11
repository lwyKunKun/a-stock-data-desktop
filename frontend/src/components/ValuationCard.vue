<!--
  ValuationCard.vue —— 估值卡片
  展示后端算好的结论性指标：PE/PB/前向PE/PEG/消化年限/机构覆盖
  （后端出结论，前端只展示，不需要 AI，零 token）
-->
<script setup>
const props = defineProps({
  valuation: { type: Object, default: () => ({}) },
})

// PEG 判断对应的颜色：<1 便宜(绿)、1~1.5 合理(默认)、>1.5 偏贵(红)
function pegClass(peg) {
  if (peg == null) return 'flat'
  if (peg < 1) return 'down'   // 便宜用绿色
  if (peg <= 1.5) return 'flat'
  return 'up'                  // 偏贵用红色
}

// 空值统一显示为 -
function show(v, suffix = '') {
  return v == null ? '-' : v + suffix
}
</script>

<template>
  <div class="card" v-if="valuation && !valuation.error">
    <div class="card-title">💰 估值分析</div>

    <!-- 无机构覆盖时的提示 -->
    <div v-if="!valuation.covered" class="muted" style="margin-bottom: 8px">
      ⚠️ 无机构一致预期覆盖，前向PE/PEG 不可用，参考 PE(TTM)/PB
    </div>

    <div class="grid">
      <div class="grid-item">
        <div class="label">PE (TTM)</div>
        <div class="value">{{ show(valuation.pe_ttm) }}</div>
      </div>
      <div class="grid-item">
        <div class="label">PB</div>
        <div class="value">{{ show(valuation.pb) }}</div>
      </div>
      <div class="grid-item">
        <div class="label">前向 PE</div>
        <div class="value">{{ show(valuation.pe_fwd) }}</div>
      </div>
      <div class="grid-item">
        <div class="label">PEG</div>
        <div class="value" :class="pegClass(valuation.peg)">
          {{ show(valuation.peg) }}
        </div>
      </div>
      <div class="grid-item">
        <div class="label">PEG 判断</div>
        <div class="value" :class="pegClass(valuation.peg)" style="font-size: 14px">
          {{ valuation.peg_verdict || '-' }}
        </div>
      </div>
      <div class="grid-item">
        <div class="label">EPS 增速</div>
        <div class="value">{{ show(valuation.cagr_pct, '%') }}</div>
      </div>
      <div class="grid-item">
        <div class="label">PE消化年限</div>
        <div class="value">{{ show(valuation.digest_years, '年') }}</div>
      </div>
      <div class="grid-item">
        <div class="label">机构覆盖</div>
        <div class="value">{{ valuation.analyst_count || 0 }}家</div>
      </div>
    </div>
  </div>
</template>
