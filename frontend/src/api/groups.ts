import { ApiClient } from './client';

export interface Group {
  id: number;
  name: string;
  tg_chat_id: number | null;
  vk_peer_id: number | null;
}

export interface Member {
  user_id: number;
  full_name: string;
  tg_user_id: number | null;
  role: 'student' | 'deputy' | 'headman' | 'curator';
}

export interface CreateGroupBody {
  name: string;
  tg_chat_id?: number | null;
  vk_peer_id?: number | null;
}

export interface AddMemberBody {
  tg_user_id?: number | null;
  vk_user_id?: number | null;
  full_name: string;
  role: 'student' | 'deputy' | 'headman' | 'curator';
}

export const GroupsApi = {
  async fetchMyGroups(): Promise<Group[]> {
    return ApiClient.get<Group[]>('/api/groups/my');
  },

  async createGroup(body: CreateGroupBody): Promise<Group> {
    return ApiClient.post<Group>('/api/groups', body);
  },

  async fetchMembers(groupId: number): Promise<Member[]> {
    return ApiClient.get<Member[]>(`/api/groups/${groupId}/members`);
  },

  async addMember(groupId: number, body: AddMemberBody): Promise<Member> {
    return ApiClient.post<Member>(`/api/groups/${groupId}/members`, body);
  },

  async removeMember(groupId: number, userId: number): Promise<void> {
    await ApiClient.delete(`/api/groups/${groupId}/members/${userId}`);
  },
};
