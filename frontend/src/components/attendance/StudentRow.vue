<script setup lang="ts">
import { computed } from 'vue';
import type { StudentAttendance } from '../../types/attendance';
import { useAuthStore } from '../../stores/auth';
import Avatar from '../common/Avatar.vue';
import { triggerHaptic } from '../../utils/telegram';
import { Check, Edit3 } from 'lucide-vue-next';

const props = defineProps<{
  student: StudentAttendance;
  index: number;
}>();

const emit = defineEmits<{
  (e: 'toggleStatus', student: StudentAttendance): void;
  (e: 'openReason', student: StudentAttendance): void;
}>();

const authStore = useAuthStore();
const isMe = computed(() => props.student.tg_id === authStore.myTgId);

function handleStatusClick() {
  if (!authStore.isAdmin) return;
  triggerHaptic('select');
  emit('toggleStatus', props.student);
}
</script>

<template>
  <div
    class="flex items-center justify-between p-3.5 bg-app-card border-b border-app-border first:rounded-t-2xl last:rounded-b-2xl last:border-b-0 transition-colors duration-150"
    :class="{ 'bg-blue-50/50 dark:bg-blue-950/30 border-l-4 !border-l-app-accent pl-2.5': isMe }"
  >
    <!-- Left: Avatar and Info -->
    <div class="flex items-center gap-3 min-w-0 flex-1 mr-2">
      <!-- Index number -->
      <span class="w-5 text-center text-[11px] font-bold text-app-muted flex-shrink-0 select-none">{{ index }}</span>
      <Avatar :tg-id="student.tg_id" :name="student.name" size="md" />

      <div class="min-w-0 flex-1">
        <div class="font-bold text-[15px] text-app-text flex items-center gap-1.5 truncate">
          <span class="truncate">{{ student.name }}</span>
          <span
            v-if="isMe"
            class="bg-app-accent text-white text-[9px] font-extrabold px-1.5 py-0.5 rounded tracking-wider uppercase shadow-sm"
          >
            Я
          </span>
          <span
            v-if="student.is_all_day"
            class="bg-app-canvas text-app-muted text-[9.5px] font-bold px-1.5 py-0.5 rounded border border-app-border uppercase"
          >
            Весь день
          </span>
        </div>

        <div
          v-if="student.status > 0"
          class="text-xs font-semibold truncate mt-1 flex items-center gap-1 cursor-pointer transition-opacity hover:opacity-80"
          :class="student.reason ? 'text-amber-600 dark:text-amber-400' : 'text-app-hint hover:text-app-text'"
          @click="authStore.isAdmin ? emit('openReason', student) : null"
        >
          <Edit3 v-if="authStore.isAdmin" class="w-3 h-3 flex-shrink-0 opacity-70" />
          <span class="truncate">{{ student.reason || '+ Добавить причину' }}</span>
        </div>
      </div>
    </div>

    <!-- Right: Status Button -->
    <div class="flex items-center">
      <button
        class="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm transition-all duration-150 select-none shadow-sm"
        :class="{
          'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800': student.status === 0,
          'bg-rose-500 text-white font-black shadow-glow-rose': student.status === 1,
          'bg-amber-500 text-white font-black shadow-glow-amber': student.status === 2,
          'cursor-pointer active:scale-90 hover:brightness-105': authStore.isAdmin,
          'cursor-default opacity-80': !authStore.isAdmin,
        }"
        :disabled="!authStore.isAdmin"
        @click="handleStatusClick"
      >
        <Check v-if="student.status === 0" class="w-4 h-4 stroke-[3]" />
        <span v-else-if="student.status === 1">Н</span>
        <span v-else-if="student.status === 2">У</span>
      </button>
    </div>
  </div>
</template>
