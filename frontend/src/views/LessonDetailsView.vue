<script setup lang="ts">
import { ref } from 'vue';
import { useAttendanceStore } from '../stores/attendance';
import { useScheduleStore } from '../stores/schedule';
import { useAuthStore } from '../stores/auth';
import { useUiStore } from '../stores/ui';
import StudentRow from '../components/attendance/StudentRow.vue';
import AttendanceSummary from '../components/attendance/AttendanceSummary.vue';
import ReasonModal from '../components/attendance/ReasonModal.vue';
import Modal from '../components/common/Modal.vue';
import SkeletonLoader from '../components/common/SkeletonLoader.vue';
import MarqueeText from '../components/common/MarqueeText.vue';
import { ChevronLeft, Edit2, Ban, RotateCcw } from 'lucide-vue-next';
import type { StudentAttendance } from '../types/attendance';

const attendanceStore = useAttendanceStore();
const scheduleStore = useScheduleStore();
const authStore = useAuthStore();
const uiStore = useUiStore();

const showRenameModal = ref(false);
const renameName = ref('');
const renameTeacher = ref('');

function openRename() {
  renameName.value = attendanceStore.lessonName;
  renameTeacher.value = attendanceStore.lessonTeacher;
  showRenameModal.value = true;
}

async function handleSaveRename() {
  await scheduleStore.updateOverride(
    attendanceStore.lessonTime,
    renameName.value,
    renameTeacher.value || null,
    attendanceStore.isCanceled ? 1 : 0
  );
  attendanceStore.lessonName = renameName.value;
  attendanceStore.lessonTeacher = renameTeacher.value;
  showRenameModal.value = false;
  uiStore.showToast('Пара изменена', 'success');
}

async function toggleCancelLesson() {
  const newCanceled = attendanceStore.isCanceled ? 0 : 1;
  await scheduleStore.updateOverride(
    attendanceStore.lessonTime,
    attendanceStore.lessonName,
    attendanceStore.lessonTeacher,
    newCanceled
  );
  attendanceStore.isCanceled = Boolean(newCanceled);
  uiStore.showToast(newCanceled ? 'Пара отменена' : 'Пара восстановлена', 'info');
}

function handleStatusToggle(s: StudentAttendance) {
  // Cycle: 0 (Present) -> 1 (Absent) -> 2 (Excused) -> 0 (Present)
  if (s.status === 0) {
    attendanceStore.updateSingleAttendance(s.id, 1, s.reason);
  } else if (s.status === 1) {
    attendanceStore.updateSingleAttendance(s.id, 2, s.reason);
  } else {
    attendanceStore.updateSingleAttendance(s.id, 0, '');
  }
}

function handleOpenReason(s: StudentAttendance) {
  attendanceStore.pendingStudent = s;
  attendanceStore.showReasonModal = true;
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-app-canvas">
    <!-- Header with 100% Mathematically Centered Title & Teacher -->
    <header class="relative px-3 py-2 premium-header sticky top-0 z-10 flex-shrink-0 shadow-sm flex items-center justify-between min-h-[58px]">
      <!-- Left Back Button -->
      <button
        class="text-app-accent flex items-center font-bold text-sm py-1.5 px-2 rounded-xl hover:bg-blue-50 dark:hover:bg-blue-950 active:scale-95 transition-all z-10 flex-shrink-0"
        @click="uiStore.switchTab('schedule')"
      >
        <ChevronLeft class="w-5 h-5 -ml-1" />
        <span>Назад</span>
      </button>

      <!-- Absolute Centered Title & Teacher -->
      <div class="absolute inset-x-20 top-0 bottom-0 flex flex-col items-center justify-center text-center pointer-events-none px-2">
        <MarqueeText
          :text="attendanceStore.lessonName"
          class="font-bold text-[14.5px] text-app-text leading-snug w-full"
          :speed="35"
          :pause-ms="1200"
        />
        <div class="text-xs text-app-muted font-semibold w-full mt-0.5 truncate text-center">
          👨‍🏫 {{ attendanceStore.lessonTeacher || 'Преподаватель не назначен' }}
        </div>
      </div>

      <!-- Right Spacer to maintain balance -->
      <div class="w-16 flex-shrink-0 pointer-events-none"></div>
    </header>

    <!-- Content List -->
    <div class="flex-1 overflow-y-auto p-4 space-y-4 pb-28">
      <!-- Admin Tools Box -->
      <div v-if="authStore.isAdmin" class="flex gap-2">
        <button
          class="flex-1 py-2.5 px-3 rounded-xl premium-card text-app-text font-bold text-xs flex items-center justify-center gap-1.5 active:scale-95 transition-all shadow-sm"
          @click="openRename"
        >
          <Edit2 class="w-3.5 h-3.5 opacity-70" />
          <span>Изменить пару</span>
        </button>
        <button
          class="flex-1 py-2.5 px-3 rounded-xl font-bold text-xs flex items-center justify-center gap-1.5 active:scale-95 transition-all shadow-sm"
          :class="
            attendanceStore.isCanceled
              ? 'premium-card text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800'
              : 'bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300 border border-rose-200 dark:border-rose-800'
          "
          @click="toggleCancelLesson"
        >
          <RotateCcw v-if="attendanceStore.isCanceled" class="w-3.5 h-3.5" />
          <Ban v-else class="w-3.5 h-3.5" />
          <span>{{ attendanceStore.isCanceled ? 'Восстановить' : 'Отменить пару' }}</span>
        </button>
      </div>

      <!-- Attendance Summary -->
      <AttendanceSummary />

      <!-- Student Rows Card Container -->
      <div class="premium-card rounded-2xl overflow-hidden shadow-sm">
        <div v-if="attendanceStore.loading" class="p-3">
          <SkeletonLoader type="row" :count="6" />
        </div>

        <template v-else>
          <StudentRow
            v-for="s in attendanceStore.filteredStudents"
            :key="s.id"
            :student="s"
            @toggle-status="handleStatusToggle"
            @open-reason="handleOpenReason"
          />
        </template>
      </div>
    </div>

    <!-- Reason Modal -->
    <ReasonModal />

    <!-- Edit/Rename Lesson Modal -->
    <Modal :show="showRenameModal" title="Редактировать пару" @close="showRenameModal = false">
      <div class="space-y-3">
        <div>
          <label class="text-xs text-app-muted font-bold mb-1 block">Название предмета</label>
          <input
            v-model="renameName"
            type="text"
            class="modal-input w-full p-3 rounded-xl border border-app-border text-sm focus:ring-2 focus:ring-app-accent outline-none"
          />
        </div>

        <div>
          <label class="text-xs text-app-muted font-bold mb-1 block">Преподаватель</label>
          <input
            v-model="renameTeacher"
            type="text"
            class="modal-input w-full p-3 rounded-xl border border-app-border text-sm focus:ring-2 focus:ring-app-accent outline-none"
          />
        </div>

        <div class="flex gap-2 pt-2">
          <button
            class="flex-1 py-3 rounded-xl bg-app-card-subtle border border-app-border text-app-text font-bold active:scale-95 transition-all"
            @click="showRenameModal = false"
          >
            Отмена
          </button>
          <button
            class="flex-1 py-3 rounded-xl bg-app-accent text-white font-bold shadow-md active:scale-95 transition-all shadow-glow-blue"
            @click="handleSaveRename"
          >
            Сохранить
          </button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
/* Force input colors inside modal regardless of Telegram theme injection */
.modal-input {
  background-color: #f8fafc !important;
  color: #0f172a !important;
}

.modal-input::placeholder {
  color: #94a3b8 !important;
}
</style>
