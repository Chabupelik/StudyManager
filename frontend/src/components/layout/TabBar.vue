<script setup lang="ts">
import { useUiStore, type ScreenTab } from '../../stores/ui';
import { useAuthStore } from '../../stores/auth';
import { Calendar, BarChart3, Users, Shield, Building2 } from 'lucide-vue-next';

const uiStore = useUiStore();
const authStore = useAuthStore();

const tabs: Array<{ id: ScreenTab; label: string; icon: any; adminOnly?: boolean; superAdminOnly?: boolean }> = [
  { id: 'schedule', label: 'Расписание', icon: Calendar },
  { id: 'stats', label: 'Статистика', icon: BarChart3 },
  { id: 'duties', label: 'Дежурства', icon: Users },
  { id: 'admin', label: 'Админка', icon: Shield, adminOnly: true },
  { id: 'groups', label: 'Группы', icon: Building2, superAdminOnly: true },
];

function isTabActive(tabId: ScreenTab): boolean {
  if (uiStore.activeScreen === tabId) return true;
  if (tabId === 'schedule' && uiStore.activeScreen === 'details') return true;
  if (tabId === 'stats' && uiStore.activeScreen === 'student-absences') return true;
  return false;
}
</script>

<template>
  <nav
    class="fixed bottom-0 left-0 right-0 z-30 premium-nav flex items-center justify-around px-2 pt-1.5 pb-[calc(var(--safe-bottom)+4px)] shadow-lg"
  >
    <template v-for="t in tabs" :key="t.id">
      <button
        v-if="(!t.adminOnly || authStore.isAdmin) && (!t.superAdminOnly || authStore.isSuperAdmin)"
        class="flex-1 flex flex-col items-center justify-center py-1 px-1 rounded-xl transition-all duration-150 relative select-none active:scale-95"
        @click="uiStore.switchTab(t.id)"
      >
        <div class="relative flex items-center justify-center mb-0.5">
          <component
            :is="t.icon"
            class="w-5 h-5 transition-transform duration-150"
            :class="
              isTabActive(t.id)
                ? 'text-app-accent scale-110'
                : 'text-app-muted hover:text-app-text'
            "
            :stroke-width="isTabActive(t.id) ? 2.5 : 1.8"
          />
        </div>

        <span
          class="text-[11px] font-semibold tracking-tight transition-colors duration-150"
          :class="
            isTabActive(t.id)
              ? 'text-app-accent'
              : 'text-app-muted'
          "
        >
          {{ t.label }}
        </span>
      </button>
    </template>
  </nav>
</template>
