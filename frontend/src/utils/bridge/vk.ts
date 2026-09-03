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

export const vkBridge: PlatformBridge = {
  init() {
    try {
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
    // VK не предоставляет синхронного API для схемы при инициализации.
    // Используем prefers-color-scheme как фоллбек.
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  },

  showBackButton(_show, _callback) {
    // VK Mini Apps используют системный back/свайп — нативная кнопка не нужна
  },
};
