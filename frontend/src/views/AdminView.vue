<script setup lang="ts">
import { onMounted } from 'vue';
import { useAdminStore } from '../stores/admin';
import { useUiStore } from '../stores/ui';
import AdminOnlineCard from '../components/admin/AdminOnlineCard.vue';
import LogFilters from '../components/admin/LogFilters.vue';
import LogCard from '../components/admin/LogCard.vue';
import SkeletonLoader from '../components/common/SkeletonLoader.vue';
import { RefreshCw, Shield, History } from 'lucide-vue-next';

const adminStore = useAdminStore();
const uiStore = useUiStore();

onMounted(() => {
  adminStore.loadAdmins();
  adminStore.loadLogs(true);
});

async function handleDeleteLog(id: number) {
  await adminStore.deleteLog(id);
  uiStore.showToast('Запись удалена', 'info');
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-app-canvas">
    <!-- Header -->
    <header class="p-3.5 premium-header text-center font-extrabold text-base text-app-text sticky top-0 z-10 flex-shrink-0 shadow-sm">
      Панель управления
    </header>

    <!-- Scrollable content -->
    <div class="flex-1 overflow-y-auto p-4 space-y-4 pb-28">
      <!-- Section 1: Admins Network -->
      <div class="premium-card rounded-2xl p-4 space-y-3">
        <div class="flex items-center gap-2 text-xs font-bold text-app-muted uppercase tracking-wider">
          <Shield class="w-3.5 h-3.5 text-app-accent" />
          <span>Сеть администраторов</span>
        </div>

        <SkeletonLoader v-if="adminStore.loading" type="row" :count="3" />

        <div v-else class="space-y-1.5">
          <AdminOnlineCard
            v-for="a in adminStore.admins"
            :key="a.id"
            :admin="a"
          />
        </div>
      </div>

      <!-- Section 2: Action Logs -->
      <div class="premium-card rounded-2xl p-4 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2 text-xs font-bold text-app-muted uppercase tracking-wider">
            <History class="w-3.5 h-3.5 text-amber-500" />
            <span>Журнал действий</span>
          </div>
          <button
            class="text-app-muted hover:text-app-text p-1.5 rounded-lg hover:bg-slate-200/50 dark:hover:bg-slate-800 transition-all"
            title="Обновить журнал"
            @click="adminStore.loadLogs(true)"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': adminStore.loadingLogs }" />
          </button>
        </div>

        <!-- Filters -->
        <LogFilters />

        <!-- Logs list -->
        <div v-if="adminStore.logs.length === 0 && !adminStore.loadingLogs" class="text-center py-8 text-app-muted text-xs font-medium">
          Записей в журнале нет
        </div>

        <div v-else class="space-y-2.5">
          <LogCard
            v-for="l in adminStore.logs"
            :key="l.id"
            :log="l"
            @delete="handleDeleteLog"
          />
        </div>

        <!-- Load More Button -->
        <button
          v-if="adminStore.hasMoreLogs"
          class="w-full py-2.5 mt-2 rounded-xl bg-app-card-subtle border border-app-border text-app-text text-xs font-bold hover:bg-slate-200/60 dark:hover:bg-slate-800 active:scale-98 transition-all"
          :disabled="adminStore.loadingLogs"
          @click="adminStore.loadLogs(false)"
        >
          {{ adminStore.loadingLogs ? 'Загрузка...' : 'Загрузить еще' }}
        </button>
      </div>
    </div>
  </div>
</template>
