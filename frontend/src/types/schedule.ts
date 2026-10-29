export interface Lesson {
  time: string;
  name: string;
  teacher: string;
  classroom?: string;
  canceled: boolean;
  absent_count: number;
  is_current?: boolean;
}

export interface ScheduleResponse {
  date: string;
  lessons: Lesson[];
}

export interface OverrideUpdateRequest {
  date: string;
  time: string;
  new_name?: string | null;
  new_teacher?: string | null;
  is_canceled: number;
}
