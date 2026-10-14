export type AttendanceFilter = 'all' | 'absent' | 'excused' | 'unexcused';

export interface StudentAttendance {
  id: number;
  tg_id: number;
  name: string;
  status: number; // 0 = present, 1 = Н (absent), 2 = У (excused)
  reason: string;
  is_all_day?: boolean;
}

export interface LessonDetailsResponse {
  students: StudentAttendance[];
}

export interface AttendanceUpdateRequest {
  date: string;
  time: string;
  student_id: number;
  status: number;
  reason?: string;
}
