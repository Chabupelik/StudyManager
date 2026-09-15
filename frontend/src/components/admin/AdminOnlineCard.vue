<script setup lang="ts">
import type { AdminUser } from '../../types/admin';
import Avatar from '../common/Avatar.vue';
import { formatLastSeen } from '../../utils/date';

defineProps<{
  admin: AdminUser;
}>();
</script>

<template>
  <div class="flex items-center justify-between py-2.5 border-b border-black/5 dark:border-white/5 last:border-b-0">
    <div class="flex items-center gap-3 min-w-0">
      <Avatar :tg-id="admin.id" :name="admin.name" size="sm" />
      <div class="min-w-0">
        <div class="font-medium text-sm text-tg-text truncate">{{ admin.name }}</div>
        <div class="text-xs text-tg-hint">
          {{ admin.is_online ? 'В сети' : (admin.last_seen ? `Был: ${formatLastSeen(admin.last_seen)}` : 'Не заходил') }}
        </div>
      </div>
    </div>

    <div>
      <span
        class="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded"
        :class="
          admin.is_online
            ? 'bg-[#34c759]/15 text-[#34c759]'
            : 'bg-black/10 dark:bg-white/10 text-tg-hint'
        "
      >
        {{ admin.is_online ? 'ONLINE' : 'OFFLINE' }}
      </span>
    </div>
  </div>
</template>
