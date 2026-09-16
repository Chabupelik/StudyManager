import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { ApiClient } from '../api/client';
import { useGroupsStore } from './groups';
import { useAuthStore } from './auth';
import type { StudentStatsRow, StatsResponse, AbsenceRecord, StudentAbsencesResponse, SubjectStatRow, StudentSubjectStatsResponse } from '../types/stats';

export type SortType = 'name' | 'month' | 'total';
export type SubSortType = 'hours' | 'name';

export const useStatsStore = defineStore('stats', () => {
  const currentMonth = ref<Date>(new Date());
  const stats = ref<StudentStatsRow[]>([]);
  const totalMonthHours = ref(0);
  const totalLifetimeHours = ref(0);
  const loading = ref(false);

  // Sorting
  const sortBy = ref<SortType>('name');

  // Selected student drilldown
  const selectedStudent = ref<{ id: number; name: string } | null>(null);
  const absences = ref<AbsenceRecord[]>([]);
  const subjectStats = ref<SubjectStatRow[]>([]);
  const subTab = ref<'history' | 'subjects'>('history');
  const subSort = ref<SubSortType>('hours');
  const drilldownLoading = ref(false);

  const sortedStats = computed(() => {
    const list = [...stats.value];
    if (sortBy.value === 'name') {
      return list.sort((a, b) => a.name.localeCompare(b.name, 'ru'));
    }
    if (sortBy.value === 'month') {
      return list.sort((a, b) => (b.month_nb + b.month_uv) - (a.month_nb + a.month_uv));
    }
    if (sortBy.value === 'total') {
      return list.sort((a, b) => (b.total_nb + b.total_uv) - (a.total_nb + a.total_uv));
    }
    return list;
  });

  const sortedSubjectStats = computed(() => {
    const list = [...subjectStats.value];
    if (subSort.value === 'hours') {
      return list.sort((a, b) => b.missed_all - a.missed_all);
    }
    return list.sort((a, b) => a.subject.localeCompare(b.subject, 'ru'));
  });

  function changeMonth(delta: number) {
    const next = new Date(currentMonth.value);
    next.setMonth(next.getMonth() + delta);
    currentMonth.value = next;
    loadStats();
  }

  async function loadStats() {
    loading.value = true;
    const y = currentMonth.value.getFullYear();
    const m = String(currentMonth.value.getMonth() + 1).padStart(2, '0');

    try {
      const groupsStore = useGroupsStore();
      const authStore = useAuthStore();
      let groupId = groupsStore.activeGroupId;
      if (!groupId && authStore.myGroups.length > 0) {
        groupId = authStore.myGroups[0].id;
      }
      const groupIdParam = groupId ? `&group_id=${groupId}` : '';
      const res = await ApiClient.get<StatsResponse>(`/api/stats?year=${y}&month=${m}${groupIdParam}`);
      stats.value = res.stats || [];
      totalMonthHours.value = res.total_month_hours || 0;
      totalLifetimeHours.value = res.total_lifetime_hours || 0;
    } catch (e) {
      console.error('Failed to load stats', e);
    } finally {
      loading.value = false;
    }
  }

  async function openStudentDrilldown(student: { id: number; name: string }) {
    selectedStudent.value = student;
    subTab.value = 'history';
    drilldownLoading.value = true;

    const y = currentMonth.value.getFullYear();
    const m = String(currentMonth.value.getMonth() + 1).padStart(2, '0');

    try {
      const [absRes, subjRes] = await Promise.all([
        ApiClient.get<StudentAbsencesResponse>(`/api/student_absences?student_id=${student.id}`),
        ApiClient.get<StudentSubjectStatsResponse>(
          `/api/student_subject_stats?student_id=${student.id}&year=${y}&month=${m}`
        ),
      ]);
      absences.value = absRes.absences || [];
      subjectStats.value = subjRes.subjects || [];
    } catch (e) {
      console.error('Failed to load student drilldown', e);
    } finally {
      drilldownLoading.value = false;
    }
  }

  return {
    currentMonth,
    stats,
    totalMonthHours,
    totalLifetimeHours,
    loading,
    sortBy,
    sortedStats,
    selectedStudent,
    absences,
    subjectStats,
    subTab,
    subSort,
    sortedSubjectStats,
    drilldownLoading,
    changeMonth,
    loadStats,
    openStudentDrilldown,
  };
});
