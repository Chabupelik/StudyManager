<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useScheduleStore } from '../stores/schedule';
import { useAttendanceStore } from '../stores/attendance';
import { useAuthStore } from '../stores/auth';
import { useUiStore } from '../stores/ui';
import { triggerHaptic } from '../utils/telegram';
import DatePill from '../components/schedule/DatePill.vue';
import LessonCard from '../components/schedule/LessonCard.vue';
import AddLessonModal from '../components/schedule/AddLessonModal.vue';
import SkeletonLoader from '../components/common/SkeletonLoader.vue';
import { Plus, Sparkles } from 'lucide-vue-next';

const scheduleStore = useScheduleStore();
const attendanceStore = useAttendanceStore();
const authStore = useAuthStore();
const uiStore = useUiStore();

const showAddModal = ref(false);

onMounted(() => {
  if (authStore.myGroups.length > 0 && !scheduleStore.selectedGroupId) {
    scheduleStore.selectedGroupId = authStore.myGroups[0].id;
  }
  scheduleStore.loadSchedule();
});

watch(() => authStore.myGroups, (newGroups) => {
  if (newGroups.length > 0 && !scheduleStore.selectedGroupId) {
    scheduleStore.selectedGroupId = newGroups[0].id;
    scheduleStore.loadSchedule();
  }
});

function openDetails(lesson: any) {
  attendanceStore.loadDetails(lesson.time, lesson.name, lesson.teacher, lesson.canceled);
  uiStore.switchTab('details');
}

// Touch swipe gestures for switching days
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

  // Horizontal swipe detected
  if (elapsed < 600 && Math.abs(deltaX) > 40 && Math.abs(deltaX) > Math.abs(deltaY) * 1.25) {
    if (deltaX < 0) {
      // Swiped left -> Next Day
      scheduleStore.changeDay(1);
      triggerHaptic('light');
    } else {
      // Swiped right -> Previous Day
      scheduleStore.changeDay(-1);
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
    <!-- Header with Date Pill and Group Selector -->
    <header class="p-3 premium-header sticky top-0 z-10 flex-shrink-0 shadow-sm flex flex-col gap-2">
      <DatePill />
      
      <!-- Group Selector for Admins -->
      <div v-if="authStore.myGroups.length > 1" class="px-1">
        <select
          v-model="scheduleStore.selectedGroupId"
          @change="scheduleStore.loadSchedule()"
          class="w-full bg-app-card border border-app-border rounded-xl px-3 py-2 text-sm text-app-text font-medium outline-none focus:border-app-accent transition-colors shadow-sm appearance-none cursor-pointer"
        >
          <option v-for="g in authStore.myGroups" :key="g.id" :value="g.id">
            Группа: {{ g.name }}
          </option>
        </select>
      </div>
    </header>

    <!-- Lessons List with inner scrolling -->
    <div class="flex-1 overflow-y-auto p-4 space-y-3 pb-28">
      <!-- Loading Skeleton -->
      <SkeletonLoader v-if="scheduleStore.loading" type="card" :count="3" />

      <!-- Empty State -->
      <div
        v-else-if="scheduleStore.lessons.length === 0"
        class="premium-card rounded-3xl p-8 my-8 text-center flex flex-col items-center justify-center space-y-3 animate-fade-in"
      >
        <div class="w-14 h-14 rounded-2xl bg-blue-50 text-app-accent dark:bg-blue-950 dark:text-blue-400 flex items-center justify-center mb-1">
          <Sparkles class="w-7 h-7" />
        </div>
        <h3 class="text-base font-bold text-app-text">Выходной день</h3>
        <p class="text-xs text-app-muted max-w-[220px]">
          На выбранную дату пары не запланированы. Можно отдохнуть 🎉
        </p>
      </div>

      <!-- Actual Lessons -->
      <template v-else>
        <LessonCard
          v-for="l in scheduleStore.lessons"
          :key="l.time"
          :lesson="l"
          @click="openDetails(l)"
        />
      </template>
    </div>

    <!-- Floating Add Button for Admins -->
    <button
      v-if="authStore.isAdmin"
      class="fixed bottom-20 right-5 w-14 h-14 rounded-2xl bg-app-accent text-white flex items-center justify-center shadow-xl active:scale-95 transition-all z-20 shadow-glow-blue"
      title="Добавить или заменить пару"
      @click="showAddModal = true"
    >
      <Plus class="w-7 h-7" />
    </button>

    <!-- Add Lesson Modal -->
    <AddLessonModal :show="showAddModal" @close="showAddModal = false" />
  </div>
</template>
