import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { ApiClient } from '../api/client';
import { toApiDate } from '../utils/date';
import type { Lesson, ScheduleResponse } from '../types/schedule';

export const useScheduleStore = defineStore('schedule', () => {
  const currentDate = ref<Date>(new Date());
  const lessons = ref<Lesson[]>([]);
  const loading = ref(false);
  const selectedLesson = ref<Lesson | null>(null);

  // In-memory caching
  const cache = new Map<string, { data: Lesson[]; expires: number }>();
  const CACHE_TTL = 60000; // 1 min

  const dateKey = computed(() => toApiDate(currentDate.value));

  function changeDay(delta: number) {
    const next = new Date(currentDate.value);
    next.setDate(next.getDate() + delta);
    currentDate.value = next;
    loadSchedule();
  }

  function changeMonth(delta: number) {
    const next = new Date(currentDate.value);
    next.setMonth(next.getMonth() + delta);
    currentDate.value = next;
    loadSchedule();
  }

  function invalidateCache(dateStr?: string) {
    if (dateStr) {
      cache.delete(dateStr);
    } else {
      cache.clear();
    }
  }

  async function loadSchedule(force = false) {
    const key = dateKey.value;
    const now = Date.now();

    if (!force && cache.has(key)) {
      const entry = cache.get(key)!;
      if (entry.expires > now) {
        lessons.value = entry.data;
        return;
      }
    }

    loading.value = true;
    try {
      const res = await ApiClient.get<ScheduleResponse>(`/api/schedule?date=${key}`);
      lessons.value = res.lessons || [];
      cache.set(key, { data: lessons.value, expires: now + CACHE_TTL });
    } catch (e) {
      console.error('Failed to load schedule', e);
    } finally {
      loading.value = false;
    }
  }

  /**
   * Тихое обновление расписания — без включения loading-индикатора.
   * Используется для WS-обновлений, чтобы данные обновились без мерцания UI.
   */
  async function refreshSilently() {
    const key = dateKey.value;
    const now = Date.now();
    try {
      const res = await ApiClient.get<ScheduleResponse>(`/api/schedule?date=${key}`);
      lessons.value = res.lessons || [];
      cache.set(key, { data: lessons.value, expires: now + CACHE_TTL });
    } catch (e) {
      console.error('Failed to refresh schedule silently', e);
    }
  }

  async function updateOverride(time: string, newName?: string | null, newTeacher?: string | null, isCanceled = 0) {
    await ApiClient.post('/api/override', {
      date: dateKey.value,
      time,
      new_name: newName,
      new_teacher: newTeacher,
      is_canceled: isCanceled,
    });
    invalidateCache(dateKey.value);
    await loadSchedule(true);
  }

  return {
    currentDate,
    lessons,
    loading,
    selectedLesson,
    dateKey,
    changeDay,
    changeMonth,
    invalidateCache,
    loadSchedule,
    refreshSilently,
    updateOverride,
  };
});
