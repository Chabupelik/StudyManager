import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { ApiClient } from '../api/client';
import { useScheduleStore } from './schedule';
import type { StudentAttendance, LessonDetailsResponse, AttendanceFilter } from '../types/attendance';

export const useAttendanceStore = defineStore('attendance', () => {
  const scheduleStore = useScheduleStore();
  const students = ref<StudentAttendance[]>([]);
  const loading = ref(false);
  const filter = ref<AttendanceFilter>('all');

  // Compatibility getter/setter for showOnlyAbsent
  const showOnlyAbsent = computed({
    get: () => filter.value !== 'all',
    set: (val: boolean) => {
      filter.value = val ? 'absent' : 'all';
    },
  });

  // Lesson metadata
  const lessonTime = ref('');
  const lessonName = ref('');
  const lessonTeacher = ref('');
  const isCanceled = ref(false);
  const isHomeroom = ref(false);

  // Modal state
  const pendingStudent = ref<StudentAttendance | null>(null);
  const showReasonModal = ref(false);

  const filteredStudents = computed(() => {
    if (filter.value === 'absent') {
      return students.value.filter((s) => s.status > 0);
    }
    if (filter.value === 'excused') {
      return students.value.filter((s) => s.status === 2);
    }
    if (filter.value === 'unexcused') {
      return students.value.filter((s) => s.status === 1);
    }
    return students.value;
  });

  const totalAbsent = computed(() => students.value.filter((s) => s.status > 0).length);
  const countNb = computed(() => students.value.filter((s) => s.status === 1).length);
  const countUv = computed(() => students.value.filter((s) => s.status === 2).length);

  async function loadDetails(time: string, name: string, teacher: string, canceled: boolean, homeroom = false) {
    lessonTime.value = time;
    lessonName.value = name;
    lessonTeacher.value = teacher;
    isCanceled.value = canceled;
    isHomeroom.value = homeroom;
    filter.value = 'all';

    loading.value = true;
    try {
      const res = await ApiClient.get<LessonDetailsResponse>(
        `/api/lesson_details?date=${scheduleStore.dateKey}&time=${time}&group_id=${scheduleStore.selectedGroupId}`
      );
      students.value = res.students || [];
      if (res.is_homeroom !== undefined) {
        isHomeroom.value = res.is_homeroom;
      }
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
      if (res.is_homeroom !== undefined) {
        isHomeroom.value = res.is_homeroom;
      }
    } catch (e) {
      console.error('Failed to refresh lesson details', e);
    }
  }

  async function updateSingleAttendance(studentId: number, status: number, reason = '') {
    if (isHomeroom.value) return;

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
      loadDetails(lessonTime.value, lessonName.value, lessonTeacher.value, isCanceled.value, isHomeroom.value);
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
    filter,
    showOnlyAbsent,
    lessonTime,
    lessonName,
    lessonTeacher,
    isCanceled,
    isHomeroom,
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
