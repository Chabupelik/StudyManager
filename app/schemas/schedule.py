from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class LessonResponse(BaseModel):
    time: str
    name: str
    teacher: str
    canceled: bool
    absent_count: int
    is_current: bool
    classroom: str | None = None
    is_homeroom: bool = False


class ScheduleResponse(BaseModel):
    date: str
    lessons: list[LessonResponse]


class OverrideUpdateRequest(BaseModel):
    date: str
    time: str
    group_id: int | None = None
    new_name: str | None = None
    new_teacher: str | None = None
    is_canceled: int

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


class BaseLessonItem(BaseModel):
    id: int
    lesson_number: int
    name: str
    teacher: str | None = None
    classroom: str | None = None
    start_time: str
    end_time: str
    valid_from: str | None = None
    valid_until: str | None = None
    is_homeroom: int = 0
    is_hidden: int = 0


class BaseScheduleResponse(BaseModel):
    day_of_week: int
    lessons: list[BaseLessonItem]
    group_id: int | None = None


class BaseLessonCreateRequest(BaseModel):
    lesson_number: int = Field(default=1, ge=1, le=12)
    name: str = Field(..., min_length=1, max_length=255)
    teacher: str | None = Field(default=None, max_length=255)
    classroom: str | None = Field(default=None, max_length=50)
    start_time: str
    end_time: str
    valid_from: str | None = None
    valid_until: str | None = None
    is_homeroom: int = 0
    is_hidden: int = 0

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
        return v

    @field_validator("valid_from", "valid_until")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @model_validator(mode="after")
    def validate_times(self) -> BaseLessonCreateRequest:
        try:
            t_start = datetime.strptime(self.start_time, "%H:%M").time()
            t_end = datetime.strptime(self.end_time, "%H:%M").time()
            if t_end <= t_start:
                raise ValueError("end_time must be after start_time")
        except ValueError as e:
            if "end_time must be after start_time" in str(e):
                raise
        if self.valid_from and self.valid_until:
            d_from = datetime.strptime(self.valid_from, "%Y-%m-%d").date()
            d_until = datetime.strptime(self.valid_until, "%Y-%m-%d").date()
            if d_until < d_from:
                raise ValueError("valid_until must be >= valid_from")
        return self


class BaseLessonUpdateRequest(BaseModel):
    lesson_number: int | None = Field(default=None, ge=1, le=12)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    teacher: str | None = Field(default=None, max_length=255)
    classroom: str | None = Field(default=None, max_length=50)
    start_time: str | None = None
    end_time: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    is_homeroom: int | None = None
    is_hidden: int | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
        return v

    @field_validator("valid_from", "valid_until")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @model_validator(mode="after")
    def validate_times(self) -> BaseLessonUpdateRequest:
        if self.start_time and self.end_time:
            t_start = datetime.strptime(self.start_time, "%H:%M").time()
            t_end = datetime.strptime(self.end_time, "%H:%M").time()
            if t_end <= t_start:
                raise ValueError("end_time must be after start_time")
        if self.valid_from and self.valid_until:
            d_from = datetime.strptime(self.valid_from, "%Y-%m-%d").date()
            d_until = datetime.strptime(self.valid_until, "%Y-%m-%d").date()
            if d_until < d_from:
                raise ValueError("valid_until must be >= valid_from")
        return self
