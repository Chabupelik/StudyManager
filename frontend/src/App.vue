<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue';
import { useAuthStore } from './stores/auth';
import { useUiStore } from './stores/ui';
import { useWsStore } from './stores/ws';
import { appBridge } from './utils/bridge';

import TabBar from './components/layout/TabBar.vue';
import Toast from './components/common/Toast.vue';
import ImageViewer from './components/common/ImageViewer.vue';
import ForbiddenScreen from './components/common/ForbiddenScreen.vue';
import DebugMenu from './components/common/DebugMenu.vue';
import InAppConsole from './components/common/InAppConsole.vue';

import ScheduleView from './views/ScheduleView.vue';
import LessonDetailsView from './views/LessonDetailsView.vue';
import StatsView from './views/StatsView.vue';
import StudentAbsencesView from './views/StudentAbsencesView.vue';
import DutiesView from './views/DutiesView.vue';
import AdminView from './views/AdminView.vue';

const authStore = useAuthStore();
const uiStore = useUiStore();
const wsStore = useWsStore();

// ── Telegram BackButton ────────────────────────────────────────────────────
const backScreens = new Set(['details', 'student-absences']);

function isBackScreen() {
  return backScreens.has(uiStore.activeScreen);
}

function registerBackButton() {
  appBridge.showBackButton(isBackScreen(), () => uiStore.goBack());
}

onMounted(async () => {
  await authStore.init();
  wsStore.connect();
  registerBackButton();
});

watch(() => uiStore.activeScreen, registerBackButton);

// ── Swipe-right-to-go-back ────────────────────────────────────────────────
let touchStartX = 0;
let touchStartY = 0;

function onTouchStart(e: TouchEvent) {
  touchStartX = e.touches[0].clientX;
  touchStartY = e.touches[0].clientY;
}

function onTouchEnd(e: TouchEvent) {
  if (!isBackScreen()) return;

  const dx = e.changedTouches[0].clientX - touchStartX;
  const dy = Math.abs(e.changedTouches[0].clientY - touchStartY);

  // Свайп вправо: горизонтальный сдвиг > 60px, вертикальный дрейф < 80px
  if (dx > 60 && dy < 80) {
    uiStore.goBack();
  }
}

onMounted(() => {
  window.addEventListener('touchstart', onTouchStart, { passive: true });
  window.addEventListener('touchend', onTouchEnd, { passive: true });
});

onUnmounted(() => {
  window.removeEventListener('touchstart', onTouchStart);
  window.removeEventListener('touchend', onTouchEnd);
});
</script>

<template>
  <div class="h-full w-full relative overflow-hidden bg-tg-secondaryBg text-tg-text">
    <!-- Forbidden Screen if not in group -->
    <ForbiddenScreen v-if="authStore.isForbidden" />

    <!-- Main App Screens -->
    <template v-else>
      <main class="h-full w-full relative">
        <KeepAlive>
          <component
            :is="
              uiStore.activeScreen === 'schedule'
                ? ScheduleView
                : uiStore.activeScreen === 'details'
                ? LessonDetailsView
                : uiStore.activeScreen === 'stats'
                ? StatsView
                : uiStore.activeScreen === 'student-absences'
                ? StudentAbsencesView
                : uiStore.activeScreen === 'duties'
                ? DutiesView
                : AdminView
            "
          />
        </KeepAlive>
      </main>

      <!-- Bottom TabBar -->
      <TabBar />

      <!-- Global Overlay Components -->
      <Toast />
      <ImageViewer />
      <DebugMenu />
      <InAppConsole />
    </template>
  </div>
</template>
