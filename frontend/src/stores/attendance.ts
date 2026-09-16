import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { ApiClient } from '../api/client';
import { useScheduleStore } from './schedule';
import type { StudentAttendance, LessonDetailsResponse } from '../types/attendance';

export const useAttendanceStore = defineStore('attendance', () => {
  const scheduleStore = useScheduleStore();
  const students = ref<StudentAttendance[]>([]);
  const loading = ref(false);
  const showOnlyAbsent = ref(false);

  // Lesson metadata
  const lessonTime = ref('');
  const lessonName = ref('');
  const lessonTeacher = ref('');
  const isCanceled = ref(false);

  // Modal state
  const pendingStudent = ref<StudentAttendance | null>(null);
  const showReasonModal = ref(false);

  const filteredStudents = computed(() => {
    if (!showOnlyAbsent.value) return students.value;
    return students.value.filter((s) => s.status > 0);
  });

  const totalAbsent = computed(() => students.value.filter((s) => s.status > 0).length);
  const countNb = computed(() => students.value.filter((s) => s.status === 1).length);
  const countUv = computed(() => students.value.filter((s) => s.status === 2).length);

  async function loadDetails(time: string, name: string, teacher: string, canceled: boolean) {
    lessonTime.value = time;
    lessonName.value = name;
    lessonTeacher.value = teacher;
    isCanceled.value = canceled;
    showOnlyAbsent.value = false;

    loading.value = true;
    try {
      const res = await ApiClient.get<LessonDetailsResponse>(
        `/api/lesson_details?date=${scheduleStore.dateKey}&time=${time}&group_id=${scheduleStore.selectedGroupId}`
      );
      students.value = res.students || [];
    } catch (e) {
      console.error('Failed to load lesson details', e);
    } finally {
      loading.value = false;
    }
  }

  async function refreshDetailsSilently() {
    try {
      const res = await ApiClient.get<LessonDetailsResponse>(
        `/api/lesson_details?date=${scheduleStore.dateKey}&time=${lessonTime.value}&group_id=${scheduleStore.selectedGroupId}`
      );
      students.value = res.students || [];
    } catch (e) {
      console.error('Failed to refresh lesson details', e);
    }
  }

  async function updateSingleAttendance(studentId: number, status: number, reason = '') {
    // Optimistic UI update
    const s = students.value.find((item) => item.id === studentId);
    if (s) {
      s.status = status;
      s.reason = reason;
    }

    try {
      await ApiClient.post('/api/attendance', {
        date: scheduleStore.dateKey,
        time: lessonTime.value,
        group_id: scheduleStore.selectedGroupId,
        student_id: studentId,
        status,
        reason,
      });
      scheduleStore.invalidateCache(scheduleStore.dateKey);
    } catch (e) {
      console.error('Failed to update attendance', e);
      // Reload on error
      loadDetails(lessonTime.value, lessonName.value, lessonTeacher.value, isCanceled.value);
    }
  }

  async function updateDayAttendance(studentId: number, status: number, reason = '') {
    try {
      await ApiClient.post('/api/attendance/day', {
        date: scheduleStore.dateKey,
        time: lessonTime.value,
        group_id: scheduleStore.selectedGroupId,
        student_id: studentId,
        status,
        reason,
      });
      scheduleStore.invalidateCache(scheduleStore.dateKey);
      await refreshDetailsSilently();
    } catch (e) {
      console.error('Failed to update day attendance', e);
    }
  }

  return {
    students,
    loading,
    showOnlyAbsent,
    lessonTime,
    lessonName,
    lessonTeacher,
    isCanceled,
    pendingStudent,
    showReasonModal,
    filteredStudents,
    totalAbsent,
    countNb,
    countUv,
    loadDetails,
    refreshDetailsSilently,
    updateSingleAttendance,
    updateDayAttendance,
  };
});
