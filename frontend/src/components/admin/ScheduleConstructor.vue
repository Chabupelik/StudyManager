<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { ApiClient as api } from '../../api/client';
import { useUiStore } from '../../stores/ui';
import { Clock, Plus, Trash2, Edit2, Calendar as CalendarIcon, Save, X, ChevronDown, ChevronUp } from 'lucide-vue-next';

interface BaseLessonItem {
  id: number;
  lesson_number: number;
  name: string;
  teacher?: string;
  classroom?: string;
  start_time: string;
  end_time: string;
  valid_from?: string;
  valid_until?: string;
}

interface BaseScheduleDay {
  day_of_week: number;
  lessons: BaseLessonItem[];
}
const uiStore = useUiStore();

const props = defineProps<{
  groupId: number;
}>();

const schedules = ref<BaseScheduleDay[]>([]);
const loading = ref(false);

const daysOfWeek = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];

async function loadSchedules() {
  if (!props.groupId) return;
  loading.value = true;
  try {
    const res = await api.get(`/api/admin/base?group_id=${props.groupId}`);
    schedules.value = Array.isArray(res) ? res : [];
  } catch (error) {
    uiStore.showToast('Ошибка загрузки расписания', 'error');
  } finally {
    loading.value = false;
  }
}

import { watch } from 'vue';
watch(() => props.groupId, () => {
  loadSchedules();
});

onMounted(() => {
  loadSchedules();
});

// Modal state
const isModalOpen = ref(false);
const editingLesson = ref<Partial<BaseLessonItem> & { day_of_week?: number }>({});
const isSaving = ref(false);

function openAddModal(day_of_week: number) {
  const defaultStart = '08:00';
  const defaultEnd = '09:30';
  editingLesson.value = {
    day_of_week,
    name: '',
    teacher: '',
    classroom: '',
    start_time: defaultStart,
    end_time: defaultEnd,
  };
  isModalOpen.value = true;
}

function openEditModal(day_of_week: number, lesson: BaseLessonItem) {
  editingLesson.value = { ...lesson, day_of_week };
  isModalOpen.value = true;
}

function closeModal() {
  isModalOpen.value = false;
  editingLesson.value = {};
}

async function saveLesson() {
  if (!editingLesson.value.name || !editingLesson.value.start_time || !editingLesson.value.end_time) {
    uiStore.showToast('Заполните обязательные поля (Название, Время)', 'error');
    return;
  }
  isSaving.value = true;
  try {
    const payload = {
      lesson_number: 1,
      name: editingLesson.value.name,
      teacher: editingLesson.value.teacher || null,
      classroom: editingLesson.value.classroom || null,
      start_time: editingLesson.value.start_time,
      end_time: editingLesson.value.end_time,
      valid_from: editingLesson.value.valid_from || null,
      valid_until: editingLesson.value.valid_until || null,
    };
    
    if (editingLesson.value.id) {
      await api.put(`/api/admin/base/lesson/${editingLesson.value.id}`, payload);
      uiStore.showToast('Пара обновлена', 'success');
    } else {
      await api.post(`/api/admin/base/${props.groupId}/${editingLesson.value.day_of_week}`, payload);
      uiStore.showToast('Пара добавлена', 'success');
    }
    closeModal();
    loadSchedules();
  } catch (error) {
    uiStore.showToast('Ошибка сохранения', 'error');
  } finally {
    isSaving.value = false;
  }
}

async function deleteLesson(id: number) {
  if (!confirm('Вы уверены, что хотите удалить эту пару?')) return;
  try {
    await api.delete(`/api/admin/base/lesson/${id}`);
    uiStore.showToast('Пара удалена', 'success');
    loadSchedules();
  } catch (error) {
    uiStore.showToast('Ошибка удаления', 'error');
  }
}

const expandedDays = ref<Set<number>>(new Set([0, 1, 2, 3, 4, 5]));

function toggleDay(day: number) {
  if (expandedDays.value.has(day)) {
    expandedDays.value.delete(day);
  } else {
    expandedDays.value.add(day);
  }
}

function getSemesterName(valid_from?: string): string {
  if (!valid_from) return 'Постоянные пары';
  const [y, m] = valid_from.split('-');
  const year = parseInt(y, 10);
  const month = parseInt(m, 10);
  
  if (month >= 9 && month <= 12) {
    return `1 семестр ${year}-${year + 1}`;
  } else {
    return `2 семестр ${year - 1}-${year}`;
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-bold text-app-text">Конструктор расписания</h3>
    </div>

    <div v-if="loading" class="text-center py-8 text-app-muted text-xs">
      Загрузка расписания...
    </div>

    <div v-else class="space-y-3">
      <div v-for="(_, day) in daysOfWeek" :key="day" class="premium-card rounded-2xl overflow-hidden border border-app-border">
        <!-- Day Header -->
        <button 
          @click="toggleDay(day)"
          class="w-full flex items-center justify-between p-3.5 bg-app-card-subtle hover:bg-slate-200/50 dark:hover:bg-slate-800/50 transition-colors"
        >
          <span class="font-semibold text-app-text text-sm flex items-center gap-2">
            <CalendarIcon class="w-4 h-4 text-app-accent" />
            {{ daysOfWeek[day] }}
          </span>
          <div class="flex items-center gap-3">
            <span class="text-xs font-medium text-app-muted bg-slate-200/50 dark:bg-slate-800 px-2 py-0.5 rounded-full">
              {{ schedules.find(s => s.day_of_week === day)?.lessons.length || 0 }} пар
            </span>
            <ChevronUp v-if="expandedDays.has(day)" class="w-4 h-4 text-app-muted" />
            <ChevronDown v-else class="w-4 h-4 text-app-muted" />
          </div>
        </button>

        <!-- Lessons List -->
        <div v-show="expandedDays.has(day)" class="p-3 bg-app-card border-t border-app-border space-y-2">
          <template v-for="(lesson, index) in (schedules.find(s => s.day_of_week === day)?.lessons || [])" :key="lesson.id">
            
            <!-- Semester Header -->
            <div 
              v-if="index === 0 || getSemesterName(lesson.valid_from) !== getSemesterName(schedules.find(s => s.day_of_week === day)!.lessons[index - 1].valid_from)"
              class="text-[10px] font-bold text-app-muted uppercase tracking-wider mt-4 mb-2 px-1"
              :class="{ 'mt-0': index === 0 }"
            >
              {{ getSemesterName(lesson.valid_from) }}
            </div>

            <div class="group flex flex-col sm:flex-row gap-3 sm:items-center justify-between p-3 rounded-xl border border-app-border/50 bg-slate-50/50 dark:bg-slate-800/20 hover:border-app-accent/30 hover:bg-app-accent/5 transition-all">
              <!-- Lesson Info -->
              <div class="flex items-center gap-3">
                <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-200 dark:bg-slate-700 text-app-text font-bold text-xs shrink-0">
                  {{ index + 1 }}
                </div>
                <div>
                  <div class="text-sm font-bold text-app-text">{{ lesson.name }}</div>
                  <div class="flex items-center gap-2 text-xs text-app-muted mt-0.5">
                    <span class="flex items-center gap-1">
                      <Clock class="w-3.5 h-3.5" />
                      {{ lesson.start_time }} - {{ lesson.end_time }}
                    </span>
                    <span v-if="lesson.teacher" class="opacity-50">•</span>
                    <span v-if="lesson.teacher">{{ lesson.teacher }}</span>
                    <span v-if="lesson.classroom" class="opacity-50">•</span>
                    <span v-if="lesson.classroom">Каб. {{ lesson.classroom }}</span>
                  </div>
                  <div v-if="lesson.valid_from || lesson.valid_until" class="text-[10px] text-amber-600 dark:text-amber-400 font-medium mt-1 uppercase tracking-wide">
                    Действует: {{ lesson.valid_from ? 'с ' + lesson.valid_from : 'всегда' }} {{ lesson.valid_until ? 'по ' + lesson.valid_until : '' }}
                  </div>
                </div>
              </div>

              <!-- Actions -->
              <div class="flex items-center gap-2 self-end sm:self-auto sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                <button 
                  @click="openEditModal(day, lesson)"
                  class="p-2 rounded-lg text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors"
                  title="Редактировать"
                >
                  <Edit2 class="w-4 h-4" />
                </button>
                <button 
                  @click="deleteLesson(lesson.id)"
                  class="p-2 rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                  title="Удалить"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </div>
          </template>

          <div v-if="!schedules.find(s => s.day_of_week === day)?.lessons.length" class="text-center py-4 text-xs text-app-muted italic">
            Нет пар в этот день
          </div>

          <!-- Add Button -->
          <button 
            @click="openAddModal(day)"
            class="w-full mt-2 py-2.5 flex items-center justify-center gap-2 rounded-xl border border-dashed border-app-border text-app-muted hover:text-app-accent hover:border-app-accent hover:bg-app-accent/5 transition-all text-sm font-medium"
          >
            <Plus class="w-4 h-4" />
            Добавить пару
          </button>
        </div>
      </div>
    </div>

    <!-- Edit/Add Modal -->
    <div v-if="isModalOpen" class="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="closeModal"></div>
      
      <div class="relative w-full max-w-md bg-app-card rounded-2xl shadow-xl overflow-hidden border border-app-border animate-in fade-in zoom-in-95 duration-200">
        <!-- Header -->
        <div class="px-5 py-4 border-b border-app-border flex items-center justify-between bg-app-card-subtle">
          <h3 class="font-bold text-app-text text-base">
            {{ editingLesson.id ? 'Редактировать пару' : 'Добавить пару' }}
          </h3>
          <button @click="closeModal" class="text-app-muted hover:text-app-text transition-colors">
            <X class="w-5 h-5" />
          </button>
        </div>
        
        <!-- Body -->
        <div class="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-1.5 col-span-2">
              <label class="text-xs font-bold text-app-muted uppercase">Название предмета *</label>
              <input type="text" v-model="editingLesson.name" placeholder="Например: Математика" class="w-full bg-slate-100 dark:bg-slate-800 border border-transparent focus:border-app-accent rounded-xl px-3 py-2 text-sm text-app-text outline-none transition-colors" />
            </div>
            
            <div class="space-y-1.5 col-span-2">
              <label class="text-xs font-bold text-app-muted uppercase">Преподаватель</label>
              <input type="text" v-model="editingLesson.teacher" placeholder="Фамилия И.О." class="w-full bg-slate-100 dark:bg-slate-800 border border-transparent focus:border-app-accent rounded-xl px-3 py-2 text-sm text-app-text outline-none transition-colors" />
            </div>

            <div class="space-y-1.5 col-span-2">
              <label class="text-xs font-bold text-app-muted uppercase">Кабинет (опц.)</label>
              <input type="text" v-model="editingLesson.classroom" placeholder="Например: 404 или 408/409" class="w-full bg-slate-100 dark:bg-slate-800 border border-transparent focus:border-app-accent rounded-xl px-3 py-2 text-sm text-app-text outline-none transition-colors" />
            </div>
            
            <div class="space-y-1.5">
              <label class="text-xs font-bold text-app-muted uppercase">Начало *</label>
              <input type="time" v-model="editingLesson.start_time" class="w-full bg-slate-100 dark:bg-slate-800 border border-transparent focus:border-app-accent rounded-xl px-3 py-2 text-sm text-app-text outline-none transition-colors" />
            </div>
            <div class="space-y-1.5">
              <label class="text-xs font-bold text-app-muted uppercase">Конец *</label>
              <input type="time" v-model="editingLesson.end_time" class="w-full bg-slate-100 dark:bg-slate-800 border border-transparent focus:border-app-accent rounded-xl px-3 py-2 text-sm text-app-text outline-none transition-colors" />
            </div>
            
            <div class="space-y-1.5 col-span-2">
              <label class="text-xs font-bold text-app-muted uppercase">Действует с даты (опц.)</label>
              <input type="date" v-model="editingLesson.valid_from" class="w-full bg-slate-100 dark:bg-slate-800 border border-transparent focus:border-app-accent rounded-xl px-3 py-2 text-sm text-app-text outline-none transition-colors" />
            </div>
            <div class="space-y-1.5 col-span-2">
              <label class="text-xs font-bold text-app-muted uppercase">Действует по дату (опц.)</label>
              <input type="date" v-model="editingLesson.valid_until" class="w-full bg-slate-100 dark:bg-slate-800 border border-transparent focus:border-app-accent rounded-xl px-3 py-2 text-sm text-app-text outline-none transition-colors" />
            </div>
          </div>
        </div>
        
        <!-- Footer -->
        <div class="p-5 border-t border-app-border bg-app-card-subtle flex gap-3">
          <button @click="closeModal" class="flex-1 py-2.5 rounded-xl border border-app-border text-app-text font-bold text-sm hover:bg-slate-200/50 dark:hover:bg-slate-800 transition-colors">
            Отмена
          </button>
          <button @click="saveLesson" :disabled="isSaving" class="flex-1 py-2.5 rounded-xl bg-app-accent text-white font-bold text-sm hover:opacity-90 transition-opacity flex items-center justify-center gap-2">
            <Save v-if="!isSaving" class="w-4 h-4" />
            {{ isSaving ? 'Сохранение...' : 'Сохранить' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
