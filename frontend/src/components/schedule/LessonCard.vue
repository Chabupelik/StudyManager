<script setup lang="ts">
import type { Lesson } from '../../types/schedule';
import MarqueeText from '../common/MarqueeText.vue';
import { ChevronRight, User, CheckCircle2, AlertCircle } from 'lucide-vue-next';

defineProps<{
  lesson: Lesson;
}>();

const emit = defineEmits<{
  (e: 'click'): void;
}>();

function getEndTime(startTime: string, name: string): string {
  if (!startTime || !startTime.includes(':')) return '';
  const [hoursStr, minutesStr] = startTime.split(':');
  let hours = parseInt(hoursStr, 10);
  let minutes = parseInt(minutesStr, 10);

  // Классный час lasts 60 minutes, others last 90 minutes
  const duration = name.toLowerCase().includes('классный час') ? 60 : 90;
  
  minutes += duration;
  hours += Math.floor(minutes / 60);
  minutes = minutes % 60;
  
  const formattedHours = hours.toString().padStart(2, '0');
  const formattedMinutes = minutes.toString().padStart(2, '0');
  
  return `${formattedHours}:${formattedMinutes}`;
}
</script>

<template>
  <div
    class="premium-card rounded-2xl p-3.5 flex items-center gap-3 cursor-pointer active:scale-[0.98] transition-all duration-150 relative overflow-hidden group"
    :class="{
      'opacity-50 grayscale': lesson.canceled,
      'ring-2 ring-app-accent bg-blue-50/30 dark:bg-blue-950/20 shadow-glow-blue': lesson.is_current,
    }"
    @click="emit('click')"
  >
    <!-- Time Badge Column -->
    <div
      class="flex flex-col items-center justify-center px-1.5 py-1.5 rounded-xl bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 font-extrabold text-xs min-w-[50px] border border-blue-200/80 dark:border-blue-800/60 flex-shrink-0 self-start mt-0.5"
    >
      <span class="tracking-tight">{{ lesson.time }}</span>
      <div class="w-full h-px bg-blue-200/60 dark:bg-blue-800/60 my-0.5"></div>
      <span class="tracking-tight opacity-75 text-[10px]">{{ getEndTime(lesson.time, lesson.name) }}</span>
    </div>

    <!-- Lesson Info with multi-line full title display -->
    <div class="flex-1 min-w-0 pr-1">
      <div class="flex items-start gap-1.5" :class="{ 'line-through opacity-70': lesson.canceled }">
        <MarqueeText
          :text="lesson.name"
          class="text-[14.5px] font-bold tracking-tight text-app-text leading-snug flex-1 min-w-0"
          :speed="38"
          :pause-ms="1000"
        />
        <span
          v-if="lesson.canceled"
          class="text-[9.5px] font-bold bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300 px-1.5 py-0.5 rounded border border-rose-200 dark:border-rose-800 flex-shrink-0"
        >
          ОТМЕНЕНА
        </span>
      </div>

      <div class="text-xs text-app-muted flex items-center gap-1.5 mt-1 mb-2 font-medium">
        <User class="w-3.5 h-3.5 opacity-60 flex-shrink-0" />
        <span class="truncate">{{ lesson.teacher || 'Преподаватель не назначен' }}</span>
      </div>

      <div class="flex items-center gap-2 flex-wrap">
        <span
          v-if="lesson.absent_count > 0"
          class="inline-flex items-center gap-1 bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300 border border-rose-200 dark:border-rose-800 text-[10.5px] font-bold px-2 py-0.5 rounded-md"
        >
          <AlertCircle class="w-3 h-3" />
          Отсутствуют: {{ lesson.absent_count }} чел.
        </span>
        <span
          v-else-if="!lesson.canceled"
          class="inline-flex items-center gap-1 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 text-[10.5px] font-semibold px-2 py-0.5 rounded-md"
        >
          <CheckCircle2 class="w-3 h-3" />
          Все присутствуют
        </span>
      </div>
    </div>

    <!-- Arrow -->
    <div class="text-app-muted group-hover:text-app-text transition-colors flex-shrink-0">
      <ChevronRight class="w-4 h-4 opacity-40 group-hover:opacity-100" />
    </div>

    <!-- СЕЙЧАС badge — правый нижний угол -->
    <span
      v-if="lesson.is_current"
      class="absolute bottom-2.5 right-9 inline-flex items-center gap-1 bg-app-accent text-white text-[9.5px] font-black tracking-wider px-2 py-0.5 rounded-full shadow-sm uppercase pointer-events-none"
    >
      <span class="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span>
      СЕЙЧАС
    </span>
  </div>
</template>
