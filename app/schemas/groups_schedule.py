from __future__ import annotations

from datetime import date, time

from pydantic import BaseModel, Field, model_validator


class ScheduleCreateRequest(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)


class LessonCreateRequest(BaseModel):
    lesson_number: int = Field(..., ge=1, le=12)
    name: str = Field(..., min_length=1, max_length=255)
    teacher: str | None = Field(None, max_length=255)
    classroom: str | None = Field(None, max_length=50)
    start_time: time
    end_time: time
    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def validate_times(self) -> LessonCreateRequest:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be >= valid_from")
        return self


class LessonResponse(BaseModel):
    id: int
    lesson_number: int
    name: str
    teacher: str | None
    classroom: str | None
    start_time: str
    end_time: str
    valid_from: date | None
    valid_until: date | None


class ScheduleResponse(BaseModel):
    id: int
    group_id: int
    day_of_week: int
    lessons: list[LessonResponse]


class TodayLessonResponse(BaseModel):
    schedule_id: int
    day_of_week: int
    lessons: list[LessonResponse]
