<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useAttendanceStore } from '../../stores/attendance';
import type { AttendanceFilter } from '../../types/attendance';
import { Users, Filter, ChevronDown, Check } from 'lucide-vue-next';
import { triggerHaptic } from '../../utils/telegram';

const attendanceStore = useAttendanceStore();
const isDropdownOpen = ref(false);
const dropdownRef = ref<HTMLElement | null>(null);

const filterOptions: { id: AttendanceFilter; label: string }[] = [
  { id: 'all', label: 'Все' },
  { id: 'absent', label: 'Все пропуски' },
  { id: 'excused', label: 'Только уважительные' },
  { id: 'unexcused', label: 'Только неуважительные' },
];

const currentFilterLabel = computed(() => {
  const found = filterOptions.find((o) => o.id === attendanceStore.filter);
  return found ? found.label : 'Все';
});

function setFilter(id: AttendanceFilter) {
  triggerHaptic('select');
  if (attendanceStore.filter === id && id !== 'all') {
    attendanceStore.filter = 'all';
  } else {
    attendanceStore.filter = id;
  }
  isDropdownOpen.value = false;
}

function selectDropdownFilter(id: AttendanceFilter) {
  triggerHaptic('select');
  attendanceStore.filter = id;
  isDropdownOpen.value = false;
}

function handleClickOutside(event: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    isDropdownOpen.value = false;
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});
</script>

<template>
  <div class="premium-card rounded-2xl p-4 space-y-3">
    <!-- Top Row: Summary & Dropdown Filter Trigger -->
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2.5 min-w-0">
        <div class="w-8 h-8 rounded-xl bg-blue-50 text-app-accent dark:bg-blue-950 dark:text-blue-400 flex items-center justify-center border border-blue-200 dark:border-blue-800 flex-shrink-0">
          <Users class="w-4 h-4" />
        </div>
        <div class="min-w-0">
          <div class="text-[11px] font-bold text-app-muted uppercase tracking-wider">Отсутствуют</div>
          <div class="text-base sm:text-lg font-extrabold text-app-text leading-tight truncate">
            {{ attendanceStore.totalAbsent }} <span class="text-xs font-semibold text-app-muted">из {{ attendanceStore.students.length }} чел.</span>
          </div>
        </div>
      </div>

      <!-- Filter Dropdown Button -->
      <div class="relative flex-shrink-0" ref="dropdownRef">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-xl transition-all duration-150 active:scale-95 shadow-sm border"
          :class="
            attendanceStore.filter !== 'all'
              ? 'bg-app-accent text-white border-app-accent shadow-glow-blue'
              : 'bg-app-card-subtle text-app-text border-app-border hover:bg-slate-200/50 dark:hover:bg-slate-800'
          "
          @click.stop="isDropdownOpen = !isDropdownOpen"
        >
          <Filter class="w-3.5 h-3.5" />
          <span class="max-w-[130px] truncate">{{ currentFilterLabel }}</span>
          <ChevronDown class="w-3 h-3 transition-transform duration-200" :class="{ 'rotate-180': isDropdownOpen }" />
        </button>

        <!-- Dropdown Menu -->
        <div
          v-if="isDropdownOpen"
          class="absolute right-0 top-full mt-1.5 w-56 py-1.5 bg-app-card dark:bg-slate-900 rounded-2xl shadow-xl border border-app-border z-30 space-y-0.5 overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        >
          <button
            v-for="opt in filterOptions"
            :key="opt.id"
            type="button"
            class="w-full px-3 py-2 text-left text-xs font-bold flex items-center justify-between transition-colors hover:bg-app-card-subtle"
            :class="attendanceStore.filter === opt.id ? 'text-app-accent bg-blue-50/60 dark:bg-blue-950/40' : 'text-app-text'"
            @click.stop="selectDropdownFilter(opt.id)"
          >
            <div class="flex items-center gap-2">
              <Check v-if="attendanceStore.filter === opt.id" class="w-3.5 h-3.5 text-app-accent stroke-[2.5]" />
              <span v-else class="w-3.5 h-3.5"></span>
              <span>{{ opt.label }}</span>
            </div>
            <span class="text-[11px] font-bold px-1.5 py-0.5 rounded-md bg-app-canvas border border-app-border text-app-muted">
              {{
                opt.id === 'all'
                  ? attendanceStore.students.length
                  : opt.id === 'absent'
                  ? attendanceStore.totalAbsent
                  : opt.id === 'excused'
                  ? attendanceStore.countUv
                  : attendanceStore.countNb
              }}
            </span>
          </button>
        </div>
      </div>
    </div>

    <!-- Filter Buttons (2x2 Grid) -->
    <div class="grid grid-cols-2 gap-2 pt-1">
      <!-- Все -->
      <button
        type="button"
        class="flex items-center justify-between px-3 py-2 rounded-xl text-left font-bold text-xs transition-all duration-150 active:scale-95 border"
        :class="
          attendanceStore.filter === 'all'
            ? 'bg-app-accent text-white border-app-accent shadow-glow-blue'
            : 'bg-app-card-subtle text-app-text border-app-border hover:bg-slate-200/50 dark:hover:bg-slate-800'
        "
        @click="setFilter('all')"
      >
        <span class="truncate">Все</span>
        <span
          class="text-xs font-extrabold px-1.5 py-0.5 rounded-md"
          :class="attendanceStore.filter === 'all' ? 'bg-white/20 text-white' : 'text-app-muted bg-app-canvas border border-app-border'"
        >
          {{ attendanceStore.students.length }}
        </span>
      </button>

      <!-- Все пропуски -->
      <button
        type="button"
        class="flex items-center justify-between px-3 py-2 rounded-xl text-left font-bold text-xs transition-all duration-150 active:scale-95 border"
        :class="
          attendanceStore.filter === 'absent'
            ? 'bg-app-accent text-white border-app-accent shadow-glow-blue'
            : 'bg-app-card-subtle text-app-text border-app-border hover:bg-slate-200/50 dark:hover:bg-slate-800'
        "
        @click="setFilter('absent')"
      >
        <span class="truncate">Все пропуски</span>
        <span
          class="text-xs font-extrabold px-1.5 py-0.5 rounded-md"
          :class="attendanceStore.filter === 'absent' ? 'bg-white/20 text-white' : 'text-app-muted bg-app-canvas border border-app-border'"
        >
          {{ attendanceStore.totalAbsent }}
        </span>
      </button>

      <!-- Только уважительные (У) -->
      <button
        type="button"
        class="flex items-center justify-between px-3 py-2 rounded-xl text-left font-bold text-xs transition-all duration-150 active:scale-95 border"
        :class="
          attendanceStore.filter === 'excused'
            ? 'bg-amber-500 text-white border-amber-600 shadow-glow-amber'
            : 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800/80 hover:bg-amber-100/60'
        "
        @click="setFilter('excused')"
      >
        <span class="truncate">Только уважительные</span>
        <span
          class="text-xs font-extrabold px-1.5 py-0.5 rounded-md"
          :class="attendanceStore.filter === 'excused' ? 'bg-white/20 text-white' : 'text-amber-700 dark:text-amber-300'"
        >
          {{ attendanceStore.countUv }}
        </span>
      </button>

      <!-- Только неуважительные (Н) -->
      <button
        type="button"
        class="flex items-center justify-between px-3 py-2 rounded-xl text-left font-bold text-xs transition-all duration-150 active:scale-95 border"
        :class="
          attendanceStore.filter === 'unexcused'
            ? 'bg-rose-500 text-white border-rose-600 shadow-glow-rose'
            : 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800/80 hover:bg-rose-100/60'
        "
        @click="setFilter('unexcused')"
      >
        <span class="truncate">Только неуважительные</span>
        <span
          class="text-xs font-extrabold px-1.5 py-0.5 rounded-md"
          :class="attendanceStore.filter === 'unexcused' ? 'bg-white/20 text-white' : 'text-rose-700 dark:text-rose-300'"
        >
          {{ attendanceStore.countNb }}
        </span>
      </button>
    </div>
  </div>
</template>
