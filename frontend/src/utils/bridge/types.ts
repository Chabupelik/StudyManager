export interface PlatformBridge {
  /** Инициализация SDK платформы */
  init(): void;

  /** Закрытие мини-аппа */
  close(): void;

  /** Тактильная отдача */
  impactOccurred(style: 'light' | 'medium' | 'heavy'): void;

  /**
   * Заголовки авторизации для HTTP-запросов.
   * TG: { 'X-Telegram-Init-Data': '...' }
   * VK: { 'X-VK-Sign': '...' }
   */
  getAuthHeaders(): Record<string, string>;

  /**
   * Payload для первого сообщения WebSocket (авторизация).
   * TG: строка initData
   * VK: query-строка (без ?)
   */
  getWsAuthPayload(): string;

  /** Текущая цветовая схема */
  getColorScheme(): 'light' | 'dark';

  /** Подписка на изменение темы (опционально) */
  onThemeChange?(callback: () => void): void;

  /**
   * Управление кнопкой «Назад».
   * В VK — no-op (системный back/свайп).
   */
  showBackButton(show: boolean, callback?: () => void): void;
}
