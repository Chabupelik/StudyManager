import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { appBridge } from './utils/bridge';
import './style.css';

// Sync theme with HTML root class
function applyTheme() {
  const isDark = appBridge.getColorScheme() === 'dark';
  document.documentElement.classList.toggle('dark', isDark);
}

applyTheme();

// Подписываемся на изменение темы через универсальный callback обоих адаптеров
appBridge.onThemeChange?.(applyTheme);

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.mount('#app');
