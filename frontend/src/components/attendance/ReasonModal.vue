<script setup lang="ts">
import { ref, watch } from 'vue';
import { useAttendanceStore } from '../../stores/attendance';
import Modal from '../common/Modal.vue';

const attendanceStore = useAttendanceStore();
const reason = ref('');
const applyAllDay = ref(false);

const templates = ['Больничный', 'Заявление', 'Объяснительная', 'Врач', 'Военкомат', "Автошкола"];

watch(
  () => attendanceStore.pendingStudent,
  (st) => {
    reason.value = st?.reason || '';
    applyAllDay.value = false;
  }
);

function selectTemplate(t: string) {
  reason.value = t;
  handleSave();
}

async function handleSave() {
  if (!attendanceStore.pendingStudent) return;
  const s = attendanceStore.pendingStudent;
  const status = s.status === 0 ? 1 : s.status;

  if (applyAllDay.value) {
    await attendanceStore.updateDayAttendance(s.id, status, reason.value);
  } else {
    await attendanceStore.updateSingleAttendance(s.id, status, reason.value);
  }

  attendanceStore.showReasonModal = false;
  attendanceStore.pendingStudent = null;
}
</script>

<template>
  <Modal
    :show="attendanceStore.showReasonModal"
    :title="attendanceStore.pendingStudent ? `Причина: ${attendanceStore.pendingStudent.name}` : 'Причина'"
    @close="attendanceStore.showReasonModal = false"
  >
    <div class="space-y-3">
      <!-- Quick Reason Chips -->
      <div class="flex flex-wrap gap-1.5 justify-center py-1">
        <button
          v-for="t in templates"
          :key="t"
          class="text-xs font-medium px-2.5 py-1.5 rounded-lg bg-[#007aff]/10 text-[#007aff] border border-[#007aff]/20 active:scale-95 transition-all"
          @click="selectTemplate(t)"
        >
          {{ t }}
        </button>
      </div>

      <!-- Manual Input -->
      <div>
        <input
          v-model="reason"
          type="text"
          placeholder="Введите причину..."
          class="w-full p-3 rounded-xl bg-tg-secondaryBg border-none text-tg-text text-sm focus:ring-2 focus:ring-[#007aff] outline-none"
          @keyup.enter="handleSave"
        />
      </div>

      <!-- Apply to All Day Checkbox -->
      <label class="flex items-center gap-2 text-xs font-medium text-tg-hint cursor-pointer px-1">
        <input
          v-model="applyAllDay"
          type="checkbox"
          class="w-4 h-4 rounded text-[#007aff] focus:ring-0"
        />
        <span>Применить ко всем парам за этот день</span>
      </label>

      <!-- Actions -->
      <div class="flex gap-2 pt-2">
        <button
          class="flex-1 py-3 rounded-xl bg-tg-secondaryBg text-tg-text font-semibold active:scale-95 transition-all"
          @click="attendanceStore.showReasonModal = false"
        >
          Отмена
        </button>
        <button
          class="flex-1 py-3 rounded-xl bg-[#007aff] text-white font-semibold shadow-md active:scale-95 transition-all"
          @click="handleSave"
        >
          Готово
        </button>
      </div>
    </div>
  </Modal>
</template>
