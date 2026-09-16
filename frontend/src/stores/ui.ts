import { defineStore } from 'pinia';
import { ref } from 'vue';
import { tg, triggerHaptic } from '../utils/telegram';

export type ScreenTab = 'schedule' | 'details' | 'stats' | 'student-absences' | 'duties' | 'admin' | 'groups';

export interface ToastMessage {
  id: number;
  text: string;
  type?: 'info' | 'success' | 'error';
}

export const useUiStore = defineStore('ui', () => {
  const activeScreen = ref<ScreenTab>('schedule');
  const previewImage = ref<string | null>(null);
  const showDebugMenu = ref(false);
  const showConsole = ref(false);
  const toasts = ref<ToastMessage[]>([]);
  let toastId = 0;

  function switchTab(tab: ScreenTab) {
    triggerHaptic('light');
    activeScreen.value = tab;

    if (tab === 'details' || tab === 'student-absences') {
      tg.BackButton.show();
    } else {
      tg.BackButton.hide();
    }
  }

  function goBack() {
    if (activeScreen.value === 'details') {
      switchTab('schedule');
    } else if (activeScreen.value === 'student-absences') {
      switchTab('stats');
    }
  }

  function showToast(text: string, type: 'info' | 'success' | 'error' = 'info') {
    const id = ++toastId;
    toasts.value.push({ id, text, type });
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id);
    }, 3000);
  }

  function openImageViewer(url: string) {
    previewImage.value = url;
  }

  function closeImageViewer() {
    previewImage.value = null;
  }

  return {
    activeScreen,
    previewImage,
    showDebugMenu,
    showConsole,
    toasts,
    switchTab,
    goBack,
    showToast,
    openImageViewer,
    closeImageViewer,
  };
});
