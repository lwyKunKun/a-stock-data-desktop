<!--
  SettingsPanel.vue —— 应用设置（外观换肤 + LLM 接入信息）
  职责：外观（白天/黑色主题）切换；读写用户级 LLM 配置（API Key / Base URL / Model / Temperature）
  规则：Key 永不明文回显（只展示后端脱敏掩码）；后端生效值来自环境变量（.env）时
        提示「此处保存不生效」，避免用户误以为改成功了
-->
<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { fetchSettings, saveSettings } from "../api/client";
import type { SettingsStatus } from "../api/types";
import { errorMessage } from "../utils/errors";
import { useTheme } from "../utils/useTheme";

const { theme, setTheme } = useTheme();

const loading = ref<boolean>(false);
const saving = ref<boolean>(false);
const error = ref<string>("");
const notice = ref<string>("");
const status = ref<SettingsStatus | null>(null);

// 表单模型：apiKey 留空表示「不修改」；其余字段预填当前生效值
const form = reactive({
  apiKey: "",
  baseUrl: "",
  model: "",
  temperature: 1,
});

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const s = await fetchSettings();
    status.value = s;
    form.baseUrl = s.llm_base_url;
    form.model = s.llm_model;
    form.temperature = s.llm_temperature;
    form.apiKey = "";
  } catch (caught: unknown) {
    error.value = errorMessage(caught);
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = "";
  notice.value = "";
  try {
    const update: Record<string, string | number> = {
      llm_base_url: form.baseUrl.trim(),
      llm_model: form.model.trim(),
      llm_temperature: Number(form.temperature),
    };
    // Key 非空才提交；空串表示保持不变
    if (form.apiKey.trim()) {
      update.llm_api_key = form.apiKey.trim();
    }
    const s = await saveSettings(update);
    status.value = s;
    form.apiKey = "";
    notice.value = s.from_env
      ? "已保存到配置文件。注意：当前进程通过环境变量（.env）读到了 Key，环境变量优先，重启后生效值仍可能来自 .env。"
      : "已保存，AI 分析现在可以使用了。";
  } catch (caught: unknown) {
    error.value = errorMessage(caught);
  } finally {
    saving.value = false;
  }
}

onMounted(load);

// 暴露给 App.vue：首次启动（未配置 Key）时外层切到设置页
defineExpose({ reload: load });
</script>

<template>
  <!-- 外观：白天/黑色换肤（与侧边栏底部切换按钮共用同一主题状态） -->
  <div class="card">
    <h2 class="card-title">🎨 设置 · 外观</h2>
    <p class="muted">切换白天 / 黑色主题，选择会永久保存，重启应用后保持。</p>
    <div class="theme-choices" role="group" aria-label="主题选择">
      <button
        type="button"
        class="theme-choice"
        :class="{ active: theme === 'light' }"
        :aria-pressed="theme === 'light'"
        @click="setTheme('light')"
      >
        <span aria-hidden="true">☀️</span> 白天主题
      </button>
      <button
        type="button"
        class="theme-choice"
        :class="{ active: theme === 'dark' }"
        :aria-pressed="theme === 'dark'"
        @click="setTheme('dark')"
      >
        <span aria-hidden="true">🌙</span> 黑色主题
      </button>
    </div>
  </div>

  <div class="card">
    <h2 class="card-title">⚙️ 设置 · AI 接入</h2>
    <p class="muted">
      AI 全维度分析按次计费，需配置 OpenAI 兼容接口。普通数据查询零成本，无需任何配置。
    </p>

    <div v-if="loading" class="loading"><span class="spinner"></span>正在读取配置…</div>
    <div v-else>
      <!-- 当前状态 -->
      <p v-if="status">
        当前状态：
        <strong v-if="status.llm_ready" style="color: var(--success-text)">✅ 已配置（{{ status.llm_provider }}）</strong>
        <strong v-else style="color: var(--danger-text)">❌ 未配置</strong>
        <span v-if="status.llm_key_masked" class="muted"> · Key：{{ status.llm_key_masked }}</span>
      </p>
      <p v-if="status?.from_env" class="muted">
        当前生效值来自环境变量 / .env，优先级高于下方配置文件。
      </p>

      <div class="grid" style="max-width: 560px">
        <div class="grid-item" style="grid-column: 1 / -1">
          <div class="label">API Key（留空表示不修改）</div>
          <input
            v-model="form.apiKey"
            class="input"
            type="password"
            autocomplete="new-password"
            placeholder="sk-..."
          />
        </div>
        <div class="grid-item" style="grid-column: 1 / -1">
          <div class="label">Base URL（OpenAI 兼容端点）</div>
          <input v-model="form.baseUrl" class="input" placeholder="https://api.kimi.com/coding/v1" />
        </div>
        <div class="grid-item">
          <div class="label">模型</div>
          <input v-model="form.model" class="input" placeholder="kimi-k2-0711-preview" />
        </div>
        <div class="grid-item">
          <div class="label">Temperature</div>
          <input v-model.number="form.temperature" class="input" type="number" step="0.1" min="0" max="2" />
        </div>
      </div>

      <div style="margin-top: 12px; display: flex; gap: 8px; align-items: center">
        <button class="btn btn-primary" :disabled="saving" @click="save">
          {{ saving ? "保存中…" : "保存设置" }}
        </button>
        <span v-if="notice" style="color: var(--success-text); font-size: 13px">{{ notice }}</span>
      </div>
      <div v-if="error" class="error-box">❌ {{ error }}</div>

      <p class="muted" style="margin-top: 16px">
        提示：Kimi For Coding 订阅用 <code>https://api.kimi.com/coding/v1</code> 端点，K2
        推理模型只接受 temperature=1；DeepSeek 用 <code>https://api.deepseek.com</code>。
      </p>
    </div>
  </div>
</template>
