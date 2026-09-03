/**
 * Единая точка входа для платформенного адаптера.
 * Импортируй appBridge везде вместо прямых вызовов window.Telegram.WebApp.
 */

import { detectPlatform } from '../platform';
import { telegramBridge } from './telegram';
import { vkBridge } from './vk';

const platform = detectPlatform();

export const appBridge = platform === 'vk' ? vkBridge : telegramBridge;

// Инициализируем SDK сразу при импорте модуля
appBridge.init();
