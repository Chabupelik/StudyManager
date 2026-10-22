<script setup lang="ts">
import { getInitials } from '../../utils/formatters';

withDefaults(
  defineProps<{
    tgId?: number;
    name: string;
    size?: 'sm' | 'md' | 'lg';
  }>(),
  {
    size: 'md',
  }
);

const sizeClasses = {
  sm: 'w-8 h-8 text-xs',
  md: 'w-10 h-10 text-sm',
  lg: 'w-12 h-12 text-base',
};
</script>

<template>
  <div
    :class="[
      'rounded-full overflow-hidden flex-shrink-0 flex items-center justify-center font-bold select-none',
      sizeClasses[size],
      'bg-gradient-to-br from-[#007aff] to-[#5ac8fa] text-white border border-black/10 dark:border-white/10 shadow-sm',
    ]"
  >
    <span>{{ getInitials(name) }}</span>
  </div>
</template>
