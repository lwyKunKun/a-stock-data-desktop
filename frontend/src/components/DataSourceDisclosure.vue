<script setup lang="ts">
import type { DataSourceDisclosure } from '../api/types'
defineProps<{ sources: DataSourceDisclosure[] }>()
</script>

<template>
  <div v-if="sources.length" class="source-disclosures">
    <div v-for="source in sources" :key="source.id" class="source-disclosure">
      <span :class="['source-grade', `grade-${source.grade.toLowerCase()}`]">{{ source.grade }}</span>
      <strong>{{ source.name }}</strong>
      <span>{{ source.restriction }}</span>
      <small v-if="source.status">{{ source.status }}</small>
    </div>
  </div>
</template>
