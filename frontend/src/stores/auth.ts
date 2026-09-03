import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { ApiClient } from '../api/client';
import { detectPlatform } from '../utils/platform';

export type UserRole = 'viewer' | 'admin' | 'super';

export const useAuthStore = defineStore('auth', () => {
  const role = ref<UserRole>('viewer');
  const user = ref<{ id: number; first_name: string } | null>(null);
  const isForbidden = ref(false);
  const showPcLoginModal = ref(false);
  const debugRoleOverride = ref<UserRole | null>(null);

  const effectiveRole = computed(() => debugRoleOverride.value || role.value);
  const isAdmin = computed(() => effectiveRole.value === 'admin' || effectiveRole.value === 'super');
  const isSuperAdmin = computed(() => effectiveRole.value === 'super' || (user.value?.id === 620159705));
  const isDeveloper = computed(() => user.value?.id === 620159705 || myTgId.value === 620159705);
  const myTgId = computed(() => user.value?.id || 0);

  async function init() {
    // PC-модалка только если нет TG и нет VK параметров
    if (detectPlatform() === 'web' && !ApiClient.getToken()) {
      showPcLoginModal.value = true;
      return;
    }

    try {
      const data = await ApiClient.get('/api/init');
      if (data) {
        role.value = data.role === 'admin' ? 'admin' : 'viewer';
        user.value = data.user;
        isForbidden.value = false;
        showPcLoginModal.value = false;

        // Superadmin check
        if (user.value?.id === 620159705) {
          role.value = 'super';
        }

        if (isAdmin.value) {
          ApiClient.get('/api/admin/ping').catch(() => {});
        }
      }
    } catch (e: any) {
      if (e.message === 'FORBIDDEN_NOT_IN_GROUP') {
        isForbidden.value = true;
      } else if (e.message === 'UNAUTHORIZED') {
        showPcLoginModal.value = true;
      }
    }
  }

  function setDebugRole(newRole: UserRole) {
    debugRoleOverride.value = newRole;
  }



  return {
    role,
    user,
    isForbidden,
    showPcLoginModal,
    effectiveRole,
    isAdmin,
    isSuperAdmin,
    isDeveloper,
    myTgId,
    init,
    setDebugRole,
  };
});
