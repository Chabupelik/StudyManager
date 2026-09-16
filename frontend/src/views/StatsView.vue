<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useStatsStore } from '../stores/stats';
import { useGroupsStore } from '../stores/groups';
import { useAuthStore } from '../stores/auth';
import { useUiStore } from '../stores/ui';
import { formatMonthYear } from '../utils/date';
import { tg, triggerHaptic } from '../utils/telegram';
import SortBar from '../components/stats/SortBar.vue';
import StatCard from '../components/stats/StatCard.vue';
import SkeletonLoader from '../components/common/SkeletonLoader.vue';
import { ChevronLeft, ChevronRight, FileSpreadsheet } from 'lucide-vue-next';

const statsStore = useStatsStore();
const groupsStore = useGroupsStore();
const authStore = useAuthStore();
const uiStore = useUiStore();

const formattedMonth = computed(() => formatMonthYear(statsStore.currentMonth));

onMounted(() => {
  statsStore.loadStats();
});

function handleOpenDrilldown(st: { id: number; name: string }) {
  statsStore.openStudentDrilldown(st);
  uiStore.switchTab('student-absences');
}

function handleExportExcel() {
  const y = statsStore.currentMonth.getFullYear();
  const m = String(statsStore.currentMonth.getMonth() + 1).padStart(2, '0');
  const botUsername = 'manager_ems_bot';
  const groupId = groupsStore.activeGroupId || 2;
  const deepLink = `https://t.me/${botUsername}?start=report_${y}_${m}_${groupId}`;

  tg.openTelegramLink(deepLink);
  tg.showPopup({
    title: 'Отчет формируется',
    message: 'Бот отправит вам Excel-файл прямо в чат Telegram через несколько секунд.',
  });
}

// Touch swipe gestures for switching months
let touchStartX = 0;
let touchStartY = 0;
let touchStartTime = 0;

function onTouchStart(e: TouchEvent) {
  if (e.touches.length !== 1) return;
  touchStartX = e.touches[0].clientX;
  touchStartY = e.touches[0].clientY;
  touchStartTime = Date.now();
}

function onTouchEnd(e: TouchEvent) {
  if (e.changedTouches.length !== 1) return;
  const deltaX = e.changedTouches[0].clientX - touchStartX;
  const deltaY = e.changedTouches[0].clientY - touchStartY;
  const elapsed = Date.now() - touchStartTime;

  if (elapsed < 600 && Math.abs(deltaX) > 50 && Math.abs(deltaX) > Math.abs(deltaY) * 1.3) {
    if (deltaX < 0) {
      // Swiped left -> Next Month
      statsStore.changeMonth(1);
      triggerHaptic('light');
    } else {
      // Swiped right -> Previous Month
      statsStore.changeMonth(-1);
      triggerHaptic('light');
    }
  }
}
</script>

<template>
  <div
    class="h-full flex flex-col overflow-hidden bg-app-canvas select-none"
    @touchstart="onTouchStart"
    @touchend="onTouchEnd"
  >
    <!-- Header with Month Switcher & Excel Export -->
    <header class="p-3 premium-header space-y-2.5 sticky top-0 z-10 flex-shrink-0 shadow-sm">
      <!-- Month Pill -->
      <div class="bg-app-card-subtle border border-app-border rounded-2xl p-1 flex items-center justify-between shadow-sm">
        <button
          class="w-8 h-8 rounded-xl bg-app-card border border-app-border text-app-text flex items-center justify-center font-bold shadow-sm active:scale-95 transition-all"
          title="Предыдущий месяц"
          @click="statsStore.changeMonth(-1)"
        >
          <ChevronLeft class="w-4 h-4" />
        </button>

        <div class="text-sm font-bold capitalize px-2 text-center select-none text-app-text">
          {{ formattedMonth }}
        </div>

        <button
          class="w-8 h-8 rounded-xl bg-app-card border border-app-border text-app-text flex items-center justify-center font-bold shadow-sm active:scale-95 transition-all"
          title="Следующий месяц"
          @click="statsStore.changeMonth(1)"
        >
          <ChevronRight class="w-4 h-4" />
        </button>
      </div>

      <!-- Excel Export Button for Admins -->
      <button
        v-if="authStore.isAdmin"
        class="w-full py-2 px-3 rounded-xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 font-bold text-xs flex items-center justify-center gap-2 active:scale-98 transition-all shadow-sm hover:brightness-105"
        @click="handleExportExcel"
      >
        <FileSpreadsheet class="w-4 h-4" />
        <span>Скачать ведомость за {{ formattedMonth }} (Excel)</span>
      </button>

      <!-- Sort Bar -->
      <SortBar />
    </header>

    <!-- Stats Cards List -->
    <div class="flex-1 overflow-y-auto p-4 space-y-3 pb-28">
      <!-- Loading Skeleton -->
      <SkeletonLoader v-if="statsStore.loading" type="stat" :count="4" />

      <!-- Actual Stats -->
      <template v-else>
        <StatCard
          v-for="s in statsStore.sortedStats"
          :key="s.id"
          :student="s"
          @click="handleOpenDrilldown(s)"
        />
      </template>
    </div>
  </div>
</template>
