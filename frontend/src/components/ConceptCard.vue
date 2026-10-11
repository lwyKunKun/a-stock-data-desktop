<!--
  ConceptCard.vue —— 板块/概念归属卡片
  展示个股所属的行业/概念/地域板块（东财 slist，混合返回，板块名自解释）
-->
<script setup>
const props = defineProps({
  concept: { type: Object, default: () => ({}) },
})
</script>

<template>
  <div class="card" v-if="concept && concept.total">
    <div class="card-title">
      🏷️ 所属板块 / 概念
      <span class="muted">共 {{ concept.total }} 个</span>
    </div>
    <!-- 板块标签云 -->
    <div class="tags">
      <span v-for="tag in concept.tags" :key="tag" class="tag">{{ tag }}</span>
    </div>
  </div>
</template>
