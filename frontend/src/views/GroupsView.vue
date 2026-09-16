<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { useGroupsStore } from '../stores/groups';
import { useAuthStore } from '../stores/auth';
import { useUiStore } from '../stores/ui';
import {
  Building2,
  Users,
  Plus,
  Trash2,
  Edit2,
  Crown,
  Star,
  GraduationCap,
  BookOpen,
  RefreshCw,
  X,
  CalendarDays,
} from 'lucide-vue-next';
import type { AddMemberBody } from '../api/groups';
import ScheduleConstructor from '../components/admin/ScheduleConstructor.vue';

const groupsStore = useGroupsStore();
const authStore = useAuthStore();
const uiStore = useUiStore();

const isSuperAdmin = authStore.isSuperAdmin;

// Modals
const showCreateGroup = ref(false);
const showEditGroup = ref(false);
const showAddMember = ref(false);
const showEditMember = ref(false);
const confirmDeleteUserId = ref<number | null>(null);

// Form state - Create Group
const newGroupName = ref('');
const newGroupTgId = ref<string>('');
const newGroupVkId = ref<string>('');

// Form state - Add/Edit Member
const memberFormUserId = ref<number | null>(null);
const memberFormName = ref('');
const memberFormTgId = ref<string>('');
const memberFormVkId = ref<string>('');
const memberFormRole = ref<AddMemberBody['role']>('student');
const formError = ref('');
const submitting = ref(false);

onMounted(() => {
  groupsStore.loadGroups();
});

const roleLabel: Record<string, string> = {
  headman: 'Староста',
  deputy: 'Заместитель',
  curator: 'Куратор',
  student: 'Студент',
};

const roleOrder: Record<string, number> = {
  curator: 0,
  headman: 1,
  deputy: 2,
  student: 3,
};

const sortedMembers = computed(() =>
  [...groupsStore.members].sort(
    (a, b) => (roleOrder[a.role] ?? 99) - (roleOrder[b.role] ?? 99)
  )
);

function roleIcon(role: string) {
  switch (role) {
    case 'headman': return Crown;
    case 'deputy':  return Star;
    case 'curator': return BookOpen;
    default:        return GraduationCap;
  }
}

function roleBadgeClass(role: string): string {
  switch (role) {
    case 'headman': return 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30';
    case 'deputy':  return 'bg-blue-500/15 text-blue-400 border-blue-500/30';
    case 'curator': return 'bg-purple-500/15 text-purple-400 border-purple-500/30';
    default:        return 'bg-slate-500/10 text-app-muted border-slate-500/20';
  }
}

// ── Create/Edit Group ────────────────────────────────────────────────────────
function openCreateGroup() {
  newGroupName.value = '';
  newGroupTgId.value = '';
  newGroupVkId.value = '';
  formError.value = '';
  showCreateGroup.value = true;
}

function openEditGroup(g: any) {
  newGroupName.value = g.name;
  newGroupTgId.value = g.tg_chat_id ? String(g.tg_chat_id) : '';
  newGroupVkId.value = g.vk_peer_id ? String(g.vk_peer_id) : '';
  formError.value = '';
  showEditGroup.value = true;
}

async function submitGroupForm() {
  if (!newGroupName.value.trim()) {
    formError.value = 'Введите название группы';
    return;
  }
  submitting.value = true;
  formError.value = '';
  try {
    if (showEditGroup.value) {
      await groupsStore.updateGroup({
        name: newGroupName.value.trim(),
        tg_chat_id: newGroupTgId.value ? Number(newGroupTgId.value) : null,
        vk_peer_id: newGroupVkId.value ? Number(newGroupVkId.value) : null,
      });
      showEditGroup.value = false;
      uiStore.showToast('Группа обновлена', 'success');
    } else {
      await groupsStore.createGroup({
        name: newGroupName.value.trim(),
        tg_chat_id: newGroupTgId.value ? Number(newGroupTgId.value) : null,
        vk_peer_id: newGroupVkId.value ? Number(newGroupVkId.value) : null,
      });
      showCreateGroup.value = false;
      uiStore.showToast('Группа создана', 'success');
    }
    newGroupName.value = '';
    newGroupTgId.value = '';
    newGroupVkId.value = '';
  } catch (e: any) {
    formError.value = e.message || 'Ошибка сохранения';
  } finally {
    submitting.value = false;
  }
}

// ── Add/Edit Member ────────────────────────────────────────────────────────
function openAddMember() {
  memberFormUserId.value = null;
  memberFormName.value = '';
  memberFormTgId.value = '';
  memberFormVkId.value = '';
  memberFormRole.value = 'student';
  formError.value = '';
  showAddMember.value = true;
}

function openEditMember(m: any) {
  memberFormUserId.value = m.user_id;
  memberFormName.value = m.full_name;
  memberFormTgId.value = m.tg_user_id ? String(m.tg_user_id) : '';
  memberFormVkId.value = m.vk_user_id ? String(m.vk_user_id) : '';
  memberFormRole.value = m.role;
  formError.value = '';
  showEditMember.value = true;
}

async function submitMemberForm() {
  if (!memberFormName.value.trim()) {
    formError.value = 'Введите имя';
    return;
  }
  if (!memberFormTgId.value && !memberFormVkId.value) {
    formError.value = 'Введите Telegram ID или VK ID';
    return;
  }
  submitting.value = true;
  formError.value = '';
  try {
    if (memberFormUserId.value) {
      // Edit
      await groupsStore.updateMember(memberFormUserId.value, {
        full_name: memberFormName.value.trim(),
        tg_user_id: memberFormTgId.value ? Number(memberFormTgId.value) : null,
        vk_user_id: memberFormVkId.value ? Number(memberFormVkId.value) : null,
        role: memberFormRole.value,
      });
      uiStore.showToast('Участник обновлён', 'success');
      showEditMember.value = false;
    } else {
      // Add
      await groupsStore.addMember({
        full_name: memberFormName.value.trim(),
        tg_user_id: memberFormTgId.value ? Number(memberFormTgId.value) : null,
        vk_user_id: memberFormVkId.value ? Number(memberFormVkId.value) : null,
        role: memberFormRole.value,
      });
      uiStore.showToast('Участник добавлен', 'success');
      showAddMember.value = false;
    }
  } catch (e: any) {
    formError.value = e.message || 'Ошибка сохранения';
  } finally {
    submitting.value = false;
  }
}

// ── Remove Member ────────────────────────────────────────────────────────────
async function confirmRemove(userId: number) {
  confirmDeleteUserId.value = userId;
}

async function doRemove() {
  if (!confirmDeleteUserId.value) return;
  try {
    await groupsStore.removeMember(confirmDeleteUserId.value);
    uiStore.showToast('Участник удалён', 'info');
  } catch (e: any) {
    uiStore.showToast(e.message || 'Ошибка удаления', 'error');
  } finally {
    confirmDeleteUserId.value = null;
  }
}

// ── Remove Group ─────────────────────────────────────────────────────────────
const confirmDeleteGroupId = ref<number | null>(null);

async function confirmDeleteGroup(groupId: number) {
  confirmDeleteGroupId.value = groupId;
}

async function doDeleteGroup() {
  if (!confirmDeleteGroupId.value) return;
  try {
    await groupsStore.deleteGroup(confirmDeleteGroupId.value);
    uiStore.showToast('Группа удалена', 'info');
  } catch (e: any) {
    uiStore.showToast(e.message || 'Ошибка удаления', 'error');
  } finally {
    confirmDeleteGroupId.value = null;
  }
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-app-canvas">
    <!-- Header -->
    <header class="p-3.5 premium-header text-center font-extrabold text-base text-app-text sticky top-0 z-10 flex-shrink-0 shadow-sm flex items-center justify-between px-4">
      <span>Группы</span>
      <button
        v-if="isSuperAdmin"
        class="p-1.5 rounded-lg hover:bg-slate-200/40 dark:hover:bg-slate-800 transition-all"
        title="Создать группу"
        @click="openCreateGroup"
      >
        <Plus class="w-4 h-4 text-app-accent" />
      </button>
    </header>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4 space-y-4 pb-28">

      <!-- Loading -->
      <div v-if="groupsStore.loading" class="flex justify-center py-12">
        <RefreshCw class="w-6 h-6 text-app-accent animate-spin" />
      </div>

      <!-- Error -->
      <div v-else-if="groupsStore.error" class="premium-card rounded-2xl p-4 text-red-400 text-sm text-center">
        {{ groupsStore.error }}
      </div>

      <!-- No groups -->
      <div v-else-if="groupsStore.groups.length === 0" class="premium-card rounded-2xl p-8 text-center">
        <Building2 class="w-10 h-10 text-app-muted mx-auto mb-3" />
        <p class="text-app-muted text-sm">Групп пока нет</p>
        <button
          v-if="isSuperAdmin"
          class="mt-4 px-4 py-2 rounded-xl bg-app-accent text-white text-xs font-bold hover:brightness-110 active:scale-95 transition-all"
          @click="openCreateGroup"
        >
          Создать группу
        </button>
      </div>

      <template v-else>
        <!-- Group Tabs -->
        <div class="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
          <button
            v-for="g in groupsStore.groups"
            :key="g.id"
            class="flex-shrink-0 px-4 py-1.5 rounded-full text-xs font-bold transition-all"
            :class="groupsStore.activeGroupId === g.id
              ? 'bg-app-accent text-white shadow-md shadow-app-accent/30'
              : 'bg-app-card-subtle border border-app-border text-app-muted hover:text-app-text'"
            @click="groupsStore.selectGroup(g.id)"
          >
            {{ g.name }}
          </button>
        </div>

        <!-- Active Group Info Card -->
        <div v-if="groupsStore.activeGroup()" class="premium-card rounded-2xl p-4 space-y-2">
          <div class="flex items-center justify-between mb-1">
            <div class="flex items-center gap-2 text-xs font-bold text-app-muted uppercase tracking-wider">
              <Building2 class="w-3.5 h-3.5 text-app-accent" />
              <span>{{ groupsStore.activeGroup()!.name }}</span>
            </div>
            <div class="flex items-center gap-1">
              <button
                v-if="isSuperAdmin"
                class="p-1 rounded-lg text-app-muted hover:text-indigo-400 hover:bg-indigo-500/10 transition-all"
                title="Редактировать группу"
                @click="openEditGroup(groupsStore.activeGroup()!)"
              >
                <Edit2 class="w-3.5 h-3.5" />
              </button>
              <button
                v-if="isSuperAdmin"
                class="p-1 rounded-lg text-app-muted hover:text-red-400 hover:bg-red-500/10 transition-all"
                title="Удалить группу"
                @click="confirmDeleteGroup(groupsStore.activeGroup()!.id)"
              >
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="bg-app-canvas rounded-xl p-2.5">
              <span class="text-app-muted block mb-0.5">TG чат ID</span>
              <span class="text-app-text font-mono font-medium">
                {{ groupsStore.activeGroup()!.tg_chat_id ?? '—' }}
              </span>
            </div>
            <div class="bg-app-canvas rounded-xl p-2.5">
              <span class="text-app-muted block mb-0.5">VK peer ID</span>
              <span class="text-app-text font-mono font-medium">
                {{ groupsStore.activeGroup()!.vk_peer_id ?? '—' }}
              </span>
            </div>
          </div>
        </div>

        <!-- Schedule Section -->
        <div v-if="isSuperAdmin" class="premium-card rounded-2xl p-4 space-y-3">
          <div class="flex items-center gap-2 text-xs font-bold text-app-muted uppercase tracking-wider mb-2">
            <CalendarDays class="w-3.5 h-3.5 text-purple-500" />
            <span>Расписание группы</span>
          </div>
          <ScheduleConstructor :groupId="groupsStore.activeGroup()!.id" />
        </div>

        <!-- Members Section -->
        <div class="premium-card rounded-2xl p-4 space-y-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2 text-xs font-bold text-app-muted uppercase tracking-wider">
              <Users class="w-3.5 h-3.5 text-indigo-400" />
              <span>Участники ({{ groupsStore.members.length }})</span>
            </div>
            <button
              v-if="isSuperAdmin"
              class="flex items-center gap-1 text-xs font-bold text-app-accent hover:brightness-110 transition-all"
              @click="openAddMember"
            >
              <Plus class="w-3.5 h-3.5" />
              Добавить
            </button>
          </div>

          <!-- Members Loading -->
          <div v-if="groupsStore.loadingMembers" class="flex justify-center py-6">
            <RefreshCw class="w-5 h-5 text-app-accent animate-spin" />
          </div>

          <!-- Members List -->
          <div v-else class="space-y-1.5">
            <div
              v-for="m in sortedMembers"
              :key="m.user_id"
              class="flex items-center gap-3 p-2.5 rounded-xl bg-app-canvas hover:bg-slate-100/50 dark:hover:bg-slate-800/50 transition-colors"
            >
              <!-- Role icon -->
              <div
                class="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
                :class="roleBadgeClass(m.role)"
              >
                <component :is="roleIcon(m.role)" class="w-3.5 h-3.5" />
              </div>

              <!-- Name + role badge -->
              <div class="flex-1 min-w-0">
                <p class="text-sm font-semibold text-app-text truncate">{{ m.full_name }}</p>
                <span
                  class="inline-block text-[10px] font-bold px-1.5 py-0.5 rounded-full border mt-0.5"
                  :class="roleBadgeClass(m.role)"
                >
                  {{ roleLabel[m.role] }}
                </span>
              </div>

              <!-- IDs -->
              <div class="hidden sm:flex flex-col gap-0.5 text-right ml-auto px-2">
                <span v-if="m.tg_user_id" class="text-[10px] text-[#3390ec] font-mono whitespace-nowrap" title="TG ID">
                  tg: {{ m.tg_user_id }}
                </span>
                <span v-if="m.vk_user_id" class="text-[10px] text-[#0077FF] font-mono whitespace-nowrap" title="VK ID">
                  vk: {{ m.vk_user_id }}
                </span>
              </div>

              <!-- Actions -->
              <div v-if="isSuperAdmin" class="flex items-center gap-1 flex-shrink-0 ml-auto sm:ml-0">
                <button
                  class="p-1.5 rounded-lg text-app-muted hover:text-indigo-400 hover:bg-indigo-500/10 transition-all"
                  title="Редактировать участника"
                  @click="openEditMember(m)"
                >
                  <Edit2 class="w-3.5 h-3.5" />
                </button>
                <button
                  class="p-1.5 rounded-lg text-app-muted hover:text-red-400 hover:bg-red-500/10 transition-all"
                  title="Удалить из группы"
                  @click="confirmRemove(m.user_id)"
                >
                  <Trash2 class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div v-if="groupsStore.members.length === 0" class="text-center py-6 text-app-muted text-xs">
              В группе нет участников
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ── Modal: Create/Edit Group ─────────────────────────────────────── -->
    <Teleport to="body">
      <div
        v-if="showCreateGroup || showEditGroup"
        class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm"
        @click.self="showCreateGroup = false; showEditGroup = false"
      >
        <div class="w-full max-w-lg bg-app-card rounded-t-3xl p-6 pb-[calc(1.5rem+var(--safe-bottom))] space-y-4 shadow-2xl">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-extrabold text-app-text">
              {{ showEditGroup ? 'Редактировать группу' : 'Новая группа' }}
            </h2>
            <button class="p-1.5 rounded-lg hover:bg-slate-200/40 dark:hover:bg-slate-800" @click="showCreateGroup = false; showEditGroup = false">
              <X class="w-4 h-4 text-app-muted" />
            </button>
          </div>

          <div class="space-y-3">
            <input
              v-model="newGroupName"
              type="text"
              placeholder="Название группы (напр. 37/2)"
              class="w-full bg-app-canvas border border-app-border rounded-xl px-3.5 py-2.5 text-sm text-app-text placeholder:text-app-muted outline-none focus:border-app-accent transition-colors"
            />
            <input
              v-model="newGroupTgId"
              type="number"
              placeholder="Telegram chat ID (необязательно)"
              class="w-full bg-app-canvas border border-app-border rounded-xl px-3.5 py-2.5 text-sm text-app-text placeholder:text-app-muted outline-none focus:border-app-accent transition-colors"
            />
            <input
              v-model="newGroupVkId"
              type="number"
              placeholder="VK peer ID (необязательно)"
              class="w-full bg-app-canvas border border-app-border rounded-xl px-3.5 py-2.5 text-sm text-app-text placeholder:text-app-muted outline-none focus:border-app-accent transition-colors"
            />
          </div>

          <p v-if="formError" class="text-red-400 text-xs font-medium">{{ formError }}</p>

          <button
            class="w-full py-3 rounded-2xl bg-app-accent text-white font-bold text-sm hover:brightness-110 active:scale-98 transition-all disabled:opacity-50"
            :disabled="submitting"
            @click="submitGroupForm"
          >
            {{ submitting ? 'Сохраняем...' : 'Сохранить' }}
          </button>
        </div>
      </div>
    </Teleport>

    <!-- ── Modal: Add/Edit Member ───────────────────────────────────────── -->
    <Teleport to="body">
      <div
        v-if="showAddMember || showEditMember"
        class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm"
        @click.self="showAddMember = false; showEditMember = false"
      >
        <div class="w-full max-w-lg bg-app-card rounded-t-3xl p-6 pb-[calc(1.5rem+var(--safe-bottom))] space-y-4 shadow-2xl">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-extrabold text-app-text">
              {{ showEditMember ? 'Редактировать участника' : 'Добавить участника' }}
            </h2>
            <button class="p-1.5 rounded-lg hover:bg-slate-200/40 dark:hover:bg-slate-800" @click="showAddMember = false; showEditMember = false">
              <X class="w-4 h-4 text-app-muted" />
            </button>
          </div>

          <div class="space-y-3">
            <input
              v-model="memberFormName"
              type="text"
              placeholder="Фамилия Имя"
              class="w-full bg-app-canvas border border-app-border rounded-xl px-3.5 py-2.5 text-sm text-app-text placeholder:text-app-muted outline-none focus:border-app-accent transition-colors"
            />
            <div class="grid grid-cols-2 gap-3">
              <input
                v-model="memberFormTgId"
                type="number"
                placeholder="Telegram ID"
                class="w-full bg-app-canvas border border-app-border rounded-xl px-3.5 py-2.5 text-sm text-app-text placeholder:text-app-muted outline-none focus:border-app-accent transition-colors"
              />
              <input
                v-model="memberFormVkId"
                type="number"
                placeholder="VK ID"
                class="w-full bg-app-canvas border border-app-border rounded-xl px-3.5 py-2.5 text-sm text-app-text placeholder:text-app-muted outline-none focus:border-app-accent transition-colors"
              />
            </div>

            <!-- Role selector -->
            <div class="grid grid-cols-4 gap-1.5">
              <button
                v-for="r in ['student', 'deputy', 'headman', 'curator'] as const"
                :key="r"
                class="py-2 rounded-xl text-[11px] font-bold border transition-all"
                :class="memberFormRole === r
                  ? roleBadgeClass(r) + ' scale-105 shadow'
                  : 'bg-app-canvas border-app-border text-app-muted'"
                @click="memberFormRole = r"
              >
                {{ roleLabel[r] }}
              </button>
            </div>
          </div>

          <p v-if="formError" class="text-red-400 text-xs font-medium">{{ formError }}</p>

          <button
            class="w-full py-3 rounded-2xl bg-app-accent text-white font-bold text-sm hover:brightness-110 active:scale-98 transition-all disabled:opacity-50"
            :disabled="submitting"
            @click="submitMemberForm"
          >
            {{ submitting ? 'Сохраняем...' : 'Сохранить' }}
          </button>
        </div>
      </div>
    </Teleport>

    <!-- ── Confirm Delete ───────────────────────────────────────────────── -->
    <Teleport to="body">
      <div
        v-if="confirmDeleteUserId !== null"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        @click.self="confirmDeleteUserId = null"
      >
        <div class="bg-app-card rounded-2xl p-6 mx-4 max-w-sm w-full space-y-4 shadow-2xl">
          <h3 class="text-sm font-extrabold text-app-text">Удалить участника?</h3>
          <p class="text-xs text-app-muted">
            Участник будет исключён из группы. Данные об отметках не удаляются.
          </p>
          <div class="flex gap-2">
            <button
              class="flex-1 py-2.5 rounded-xl border border-app-border text-app-muted text-xs font-bold hover:bg-slate-200/40 dark:hover:bg-slate-800 transition-all"
              @click="confirmDeleteUserId = null"
            >
              Отмена
            </button>
            <button
              class="flex-1 py-2.5 rounded-xl bg-red-500 text-white text-xs font-bold hover:bg-red-600 active:scale-98 transition-all"
              @click="doRemove"
            >
              Удалить
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Confirm Delete Group ─────────────────────────────────────────── -->
    <Teleport to="body">
      <div
        v-if="confirmDeleteGroupId !== null"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        @click.self="confirmDeleteGroupId = null"
      >
        <div class="bg-app-card rounded-2xl p-6 mx-4 max-w-sm w-full space-y-4 shadow-2xl">
          <h3 class="text-sm font-extrabold text-app-text">Удалить группу?</h3>
          <p class="text-xs text-app-muted text-red-400">
            Внимание! Это действие безвозвратно удалит группу, всех участников и все отметки об их посещаемости!
          </p>
          <div class="flex gap-2">
            <button
              class="flex-1 py-2.5 rounded-xl border border-app-border text-app-muted text-xs font-bold hover:bg-slate-200/40 dark:hover:bg-slate-800 transition-all"
              @click="confirmDeleteGroupId = null"
            >
              Отмена
            </button>
            <button
              class="flex-1 py-2.5 rounded-xl bg-red-500 text-white text-xs font-bold hover:bg-red-600 active:scale-98 transition-all"
              @click="doDeleteGroup"
            >
              Удалить
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
