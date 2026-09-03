<script setup lang="ts">
import { onMounted, watch } from 'vue';
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

onMounted(async () => {
  await authStore.init();
  wsStore.connect();

  // Кнопка «Назад» (TG показывает нативную, VK — no-op)
  appBridge.showBackButton(false, () => {
    uiStore.goBack();
  });
});

// Update BackButton visibility on active screen change
watch(
  () => uiStore.activeScreen,
  (screen) => {
    const shouldShow = screen === 'details' || screen === 'student-absences';
    appBridge.showBackButton(shouldShow);
  }
);
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
