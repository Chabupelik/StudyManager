/**
 * Telegram Mini App bridge.
 * Переносит текущую логику из utils/telegram.ts в стандартный интерфейс PlatformBridge.
 */

import type { PlatformBridge } from './types';

declare global {
  interface Window {
    Telegram?: {
      WebApp: any;
    };
  }
}

const tg = window.Telegram?.WebApp ?? null;

// Храним текущий callback, чтобы снимать его перед перерегистрацией
let _backCallback: (() => void) | null = null;

export const telegramBridge: PlatformBridge = {
  init() {
    try {
      tg?.expand?.();
      tg?.ready?.();
    } catch {}
  },

  close() {
    try {
      tg?.close?.();
    } catch {}
  },

  impactOccurred(style) {
    try {
      if (!tg?.isVersionAtLeast?.('6.1')) return;
      tg.HapticFeedback?.impactOccurred?.(style);
    } catch {}
  },

  getAuthHeaders(): Record<string, string> {
    const initData = tg?.initData ?? '';
    if (!initData) return {};
    return { 'X-Telegram-Init-Data': initData };
  },

  getWsAuthPayload() {
    return tg?.initData ?? '';
  },

  getColorScheme() {
    return tg?.colorScheme === 'dark' ? 'dark' : 'light';
  },

  onThemeChange(callback) {
    try {
      tg?.onEvent?.('themeChanged', callback);
    } catch {}
  },

  showBackButton(show, callback) {
    try {
      if (!tg?.isVersionAtLeast?.('6.1')) return;

      // Снимаем старый callback перед любым действием
      if (_backCallback) {
        tg.BackButton?.offClick?.(_backCallback);
        _backCallback = null;
      }

      if (show) {
        tg.BackButton?.show?.();
        if (callback) {
          _backCallback = callback;
          tg.BackButton?.onClick?.(_backCallback);
        }
      } else {
        tg.BackButton?.hide?.();
      }
    } catch {}
  },
};
