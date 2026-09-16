from pydantic import BaseModel


class LessonResponse(BaseModel):
    time: str
    name: str
    teacher: str
    canceled: bool
    absent_count: int
    is_current: bool


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
