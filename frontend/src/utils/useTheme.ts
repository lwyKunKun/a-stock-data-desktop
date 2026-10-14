// 主题（白天/黑色换肤）共享状态
// 模块级单例 ref：App.vue 侧边栏与 SettingsPanel 外观区共用同一主题状态，
// 任一处切换，另一处同步更新；初始化时读取 localStorage 并应用到 <html data-theme>
import { ref, watch } from "vue";
import { loadTheme, saveTheme } from "./storage";
import type { Theme } from "./storage";

const theme = ref<Theme>(loadTheme());

watch(
  theme,
  (value) => {
    document.documentElement.dataset.theme = value;
    saveTheme(value);

    const themeColor = getComputedStyle(document.documentElement)
      .getPropertyValue("--bg")
      .trim();
    document
      .querySelector<HTMLMetaElement>('meta[name="theme-color"]')
      ?.setAttribute("content", themeColor);
  },
  { immediate: true }
);

export function useTheme() {
  function toggleTheme(): void {
    theme.value = theme.value === "light" ? "dark" : "light";
  }

  function setTheme(value: Theme): void {
    theme.value = value;
  }

  return { theme, toggleTheme, setTheme };
}
