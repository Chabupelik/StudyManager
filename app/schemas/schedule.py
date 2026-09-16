from pydantic import BaseModel


class LessonResponse(BaseModel):
    time: str
    name: str
    teacher: str
    canceled: bool
    absent_count: int
    is_current: bool
    classroom: str | None = None


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


class BaseScheduleResponse(BaseModel):
    group_id: int
    day_of_week: int
    lessons: list[BaseLessonItem]


class BaseLessonCreateRequest(BaseModel):
    lesson_number: int
    name: str
    teacher: str | None = None
    classroom: str | None = None
    start_time: str
    end_time: str
    valid_from: str | None = None
    valid_until: str | None = None


class BaseLessonUpdateRequest(BaseModel):
    lesson_number: int | None = None
    name: str | None = None
    teacher: str | None = None
    classroom: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
