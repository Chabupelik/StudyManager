from pydantic import BaseModel


class AttendanceUpdateRequest(BaseModel):
    date: str
    time: str
    group_id: int
    student_id: int
    status: int
    reason: str | None = ""


class StudentAttendanceRow(BaseModel):
    id: int
    tg_id: int
    name: str
    status: int
    reason: str
    is_all_day: bool


class LessonDetailsResponse(BaseModel):
    students: list[StudentAttendanceRow]
