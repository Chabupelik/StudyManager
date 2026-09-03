import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { appBridge } from './utils/bridge';
import { detectPlatform } from './utils/platform';
import './style.css';

// Sync theme with HTML root class
function applyTheme() {
  const isDark = appBridge.getColorScheme() === 'dark';

  if (isDark) {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
}

applyTheme();

// Подписка на изменение темы (только TG поддерживает событие)
if (detectPlatform() === 'telegram') {
  try {
    (window as any).Telegram?.WebApp?.onEvent?.('themeChanged', applyTheme);
  } catch {}
}

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.mount('#app');
