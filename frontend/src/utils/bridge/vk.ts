/**
 * VK Mini Apps bridge.
 * Использует только необходимый минимум из @vkontakte/vk-bridge:
 * init, close, haptics, auth headers.
 * Вся бизнес-логика и аватарки работают через tg_id студента на бэкенде.
 */

import bridge from '@vkontakte/vk-bridge';
import type { PlatformBridge } from './types';

// Фиксируем query-строку запуска один раз при загрузке модуля.
// Vue Router может изменить window.location.search при навигации,
// поэтому читаем её до первого router.push().
const launchParams = window.location.search.slice(1);

// Тема: читается из VKWebAppUpdateConfig (async). По умолчанию dark —
// большинство пользователей VK на мобиле используют тёмную тему,
// а на ПК мы подхватим реальную через событие после init.
let _scheme: 'dark' | 'light' = 'dark';
const _themeListeners: Array<() => void> = [];

// Подписываемся на изменения темы от VK клиента
bridge.subscribe((event) => {
  if (event.detail.type === 'VKWebAppUpdateConfig') {
    const data = event.detail.data as any;
    const newScheme: 'dark' | 'light' =
      data?.scheme === 'space_gray' || data?.scheme === 'vkcom_dark' ? 'dark' : 'light';
    if (newScheme !== _scheme) {
      _scheme = newScheme;
      _themeListeners.forEach((cb) => cb());
    }
  }
});

export const vkBridge: PlatformBridge = {
  init() {
    try {
      // VKWebAppInit триггерит отправку VKWebAppUpdateConfig с реальной темой
      bridge.send('VKWebAppInit');
    } catch {}
  },

  close() {
    try {
      bridge.send('VKWebAppClose', { status: 'success' });
    } catch {}
  },

  impactOccurred(style) {
    try {
      bridge.send('VKWebAppTapticImpactOccurred', { style });
    } catch {}
  },

  getAuthHeaders(): Record<string, string> {
    if (!launchParams) return {};
    return { 'X-VK-Sign': launchParams };
  },

  getWsAuthPayload() {
    return launchParams;
  },

  getColorScheme() {
    return _scheme;
  },

  onThemeChange(callback: () => void) {
    _themeListeners.push(callback);
  },

  showBackButton(_show, _callback) {
    // VK Mini Apps используют системный back/свайп — нативная кнопка не нужна
  },
};
