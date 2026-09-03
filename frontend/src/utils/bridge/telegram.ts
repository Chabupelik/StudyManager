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

  showBackButton(show, callback) {
    try {
      if (!tg?.isVersionAtLeast?.('6.1')) return;
      if (show) {
        tg.BackButton?.show?.();
        if (callback) tg.BackButton?.onClick?.(callback);
      } else {
        tg.BackButton?.hide?.();
      }
    } catch {}
  },
};
