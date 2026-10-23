from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AttendanceUpdateRequest(BaseModel):
    date: str
    time: str
    group_id: int
    student_id: int
    status: int = Field(default=0, ge=0, le=2)
    reason: str | None = ""

    @field_validator("time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
        return v

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v


class StudentAttendanceRow(BaseModel):
    id: int
    tg_id: int
    name: str
    status: int
    reason: str
    is_all_day: bool


class LessonDetailsResponse(BaseModel):
    students: list[StudentAttendanceRow]
