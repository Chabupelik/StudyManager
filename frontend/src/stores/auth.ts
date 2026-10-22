import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { ApiClient } from '../api/client';

export type UserRole = 'viewer' | 'admin' | 'super';

export const useAuthStore = defineStore('auth', () => {
  const role = ref<UserRole>('viewer');
  const user = ref<{ id: number; first_name: string } | null>(null);
  const isForbidden = ref(false);
  const debugRoleOverride = ref<UserRole | null>(null);

  const effectiveRole = computed(() => debugRoleOverride.value || role.value);
  const isAdmin = computed(() => effectiveRole.value === 'admin' || effectiveRole.value === 'super');
  const isSuperAdmin = computed(() => effectiveRole.value === 'super' || (user.value?.id === 620159705));
  const isDeveloper = computed(() => user.value?.id === 620159705 || myTgId.value === 620159705);
  const myTgId = computed(() => user.value?.id || 0);

  const myGroups = ref<{ id: number; name: string }[]>([]);

  async function init() {
    try {
      const data = await ApiClient.get('/api/init');
      if (data) {
        role.value = data.role === 'admin' ? 'admin' : 'viewer';
        user.value = data.user;
        isForbidden.value = false;

        if (user.value?.id === 620159705) {
          role.value = 'super';
        }

        if (isAdmin.value) {
          ApiClient.get('/api/admin/ping').catch(() => {});
        }
        
        try {
          const groups = await ApiClient.get('/api/groups/my');
          myGroups.value = groups || [];
        } catch (e) {
          console.error("Failed to fetch groups", e);
        }
      }
    } catch (e: any) {
      if (e.message === 'FORBIDDEN_NOT_IN_GROUP' || e.message === 'UNAUTHORIZED' || e.message === 'FORBIDDEN') {
        isForbidden.value = true;
      }
    }
  }

  function setDebugRole(newRole: UserRole) {
    debugRoleOverride.value = newRole;
  }

  return {
    role,
    user,
    myGroups,
    isForbidden,
    effectiveRole,
    isAdmin,
    isSuperAdmin,
    isDeveloper,
    myTgId,
    init,
    setDebugRole,
  };
});
