import { defineStore } from 'pinia';
import { ref } from 'vue';
import { GroupsApi, type Group, type Member, type AddMemberBody, type UpdateMemberBody, type CreateGroupBody, type UpdateGroupBody } from '../api/groups';

export const useGroupsStore = defineStore('groups', () => {
  const groups = ref<Group[]>([]);
  const activeGroupId = ref<number | null>(null);
  const members = ref<Member[]>([]);
  const loading = ref(false);
  const loadingMembers = ref(false);
  const error = ref<string | null>(null);

  const activeGroup = () => groups.value.find((g) => g.id === activeGroupId.value) ?? null;

  async function loadGroups() {
    loading.value = true;
    error.value = null;
    try {
      groups.value = await GroupsApi.fetchMyGroups();
      // Auto-select first group if none selected
      if (groups.value.length > 0 && activeGroupId.value === null) {
        activeGroupId.value = groups.value[0].id;
        await loadMembers(groups.value[0].id);
      }
    } catch (e: any) {
      error.value = e.message || 'Ошибка загрузки групп';
    } finally {
      loading.value = false;
    }
  }

  async function selectGroup(groupId: number) {
    if (activeGroupId.value === groupId) return;
    activeGroupId.value = groupId;
    await loadMembers(groupId);
  }

  async function loadMembers(groupId: number) {
    loadingMembers.value = true;
    try {
      members.value = await GroupsApi.fetchMembers(groupId);
    } catch (e: any) {
      error.value = e.message || 'Ошибка загрузки участников';
    } finally {
      loadingMembers.value = false;
    }
  }

  async function createGroup(body: CreateGroupBody): Promise<Group> {
    const group = await GroupsApi.createGroup(body);
    groups.value.push(group);
    activeGroupId.value = group.id;
    members.value = [];
    return group;
  }

  async function updateGroup(body: UpdateGroupBody): Promise<Group | void> {
    if (!activeGroupId.value) return;
    const group = await GroupsApi.updateGroup(activeGroupId.value, body);
    const idx = groups.value.findIndex((g) => g.id === group.id);
    if (idx >= 0) {
      groups.value[idx] = group;
    }
    return group;
  }

  async function addMember(body: AddMemberBody): Promise<void> {
    if (!activeGroupId.value) return;
    const member = await GroupsApi.addMember(activeGroupId.value, body);
    // Upsert in local list
    const idx = members.value.findIndex((m) => m.user_id === member.user_id);
    if (idx >= 0) {
      members.value[idx] = member;
    } else {
      members.value.push(member);
    }
  }

  async function updateMember(userId: number, body: UpdateMemberBody): Promise<void> {
    if (!activeGroupId.value) return;
    const member = await GroupsApi.updateMember(activeGroupId.value, userId, body);
    const idx = members.value.findIndex((m) => m.user_id === member.user_id);
    if (idx >= 0) {
      members.value[idx] = member;
    }
  }

  async function removeMember(userId: number): Promise<void> {
    if (!activeGroupId.value) return;
    await GroupsApi.removeMember(activeGroupId.value, userId);
    members.value = members.value.filter((m) => m.user_id !== userId);
  }

  async function deleteGroup(groupId: number): Promise<void> {
    await GroupsApi.deleteGroup(groupId);
    groups.value = groups.value.filter((g) => g.id !== groupId);
    if (activeGroupId.value === groupId) {
      activeGroupId.value = null;
      members.value = [];
      if (groups.value.length > 0) {
        await selectGroup(groups.value[0].id);
      }
    }
  }

  return {
    groups,
    activeGroupId,
    members,
    loading,
    loadingMembers,
    error,
    activeGroup,
    loadGroups,
    selectGroup,
    loadMembers,
    createGroup,
    updateGroup,
    deleteGroup,
    addMember,
    updateMember,
    removeMember,
  };
});
