export type Platform = 'vk' | 'telegram' | 'web';

declare global {
  interface Window {
    Telegram?: {
      WebApp: any;
    };
  }
}

export function detectPlatform(): Platform {
  const params = new URLSearchParams(window.location.search);

  // VK всегда шлёт параметры с префиксом vk_
  if (params.has('vk_user_id') || params.has('vk_app_id')) {
    return 'vk';
  }

  // Telegram: глобальный объект + непустой initData
  if (window.Telegram?.WebApp?.initData) {
    return 'telegram';
  }

  return 'web';
}
