<script setup lang="ts">
import { useStatsStore, type SortType } from '../../stores/stats';

const statsStore = useStatsStore();

const options: Array<{ id: SortType; label: string }> = [
  { id: 'name', label: 'По имени' },
  { id: 'month', label: 'Пропуски (месяц)' },
  { id: 'total', label: 'Пропуски (семестр)' },
];
</script>

<template>
  <div class="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar select-none">
    <button
      v-for="opt in options"
      :key="opt.id"
      class="text-xs font-semibold px-3 py-1.5 rounded-xl border whitespace-nowrap transition-all"
      :class="
        statsStore.sortBy === opt.id
          ? 'bg-[#007aff] text-white border-[#007aff] shadow-sm'
          : 'bg-tg-bg text-tg-hint border-black/10 dark:border-white/10 hover:text-tg-text'
      "
      @click="statsStore.sortBy = opt.id"
    >
      {{ opt.label }}
    </button>
  </div>
</template>
