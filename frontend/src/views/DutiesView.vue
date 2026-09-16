<script setup lang="ts">
import { onMounted } from 'vue';
import { useDutyStore } from '../stores/duties';
import { useAuthStore } from '../stores/auth';
import { useUiStore } from '../stores/ui';
import { useScheduleStore } from '../stores/schedule';
import DutyStudentRow from '../components/duties/DutyStudentRow.vue';
import SkeletonLoader from '../components/common/SkeletonLoader.vue';
import { Save, Calendar } from 'lucide-vue-next';

const dutyStore = useDutyStore();
const authStore = useAuthStore();
const uiStore = useUiStore();
const scheduleStore = useScheduleStore();

onMounted(() => {
  dutyStore.loadDuties();
});

import { watch } from 'vue';
watch(() => scheduleStore.selectedGroupId, () => {
  dutyStore.loadDuties();
});


async function handleSaveDuties() {
  const ok = await dutyStore.saveDuties();
  if (ok) {
    uiStore.showToast('Дежурные успешно назначены!', 'success');
  } else {
    uiStore.showToast('Ошибка при назначении дежурных', 'error');
  }
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-app-canvas">
    <!-- Header with Date Picker -->
    <header class="p-3.5 premium-header flex items-center justify-between sticky top-0 z-10 flex-shrink-0 shadow-sm">
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-xl bg-blue-50 text-app-accent dark:bg-blue-950 dark:text-blue-400 flex items-center justify-center border border-blue-200 dark:border-blue-800">
          <Calendar class="w-4 h-4" />
        </div>
        <div>
          <div class="font-bold text-[15px] text-app-text leading-tight">График дежурств</div>
          <div class="text-[11px] text-app-muted font-medium">
            {{ authStore.isAdmin ? 'Выберите студентов для назначения' : 'Очередь дежурных' }}
          </div>
        </div>
      </div>

      <input
        v-if="authStore.isAdmin"
        v-model="dutyStore.dutyDate"
        type="date"
        class="bg-app-card-subtle text-app-accent font-bold text-xs p-2 rounded-xl border border-app-border outline-none focus:ring-2 focus:ring-app-accent"
      />
    </header>

    <!-- Students List -->
    <div class="flex-1 overflow-y-auto p-4 pb-28 space-y-3">
      <!-- Loading Skeleton -->
      <SkeletonLoader v-if="dutyStore.loading" type="duty" :count="7" />

      <!-- Students List Container -->
      <div
        v-else
        class="premium-card rounded-2xl overflow-hidden shadow-sm"
      >
        <DutyStudentRow
          v-for="s in dutyStore.duties"
          :key="s.id"
          :student="s"
          :selected="dutyStore.selectedStudentIds.includes(s.id)"
          :can-select="authStore.isAdmin"
          @toggle="dutyStore.toggleStudentSelection(s.id)"
        />
      </div>
    </div>

    <!-- Floating Save Button -->
    <button
      v-if="authStore.isAdmin && dutyStore.selectedStudentIds.length > 0"
      class="fixed bottom-20 right-5 px-5 h-14 rounded-2xl bg-app-accent text-white flex items-center justify-center gap-2 font-bold text-sm shadow-xl active:scale-95 transition-all z-20 shadow-glow-blue"
      :disabled="dutyStore.saving"
      @click="handleSaveDuties"
    >
      <Save class="w-5 h-5" />
      <span>Назначить ({{ dutyStore.selectedStudentIds.length }})</span>
    </button>
  </div>
</template>
