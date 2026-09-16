from pydantic import BaseModel


class DutyAssignRequest(BaseModel):
    date: str
    group_id: int
    student_ids: list[int]


class DutyStudentRow(BaseModel):
    id: int
    name: str
    tg_id: int
    date: str | None = None
    is_absent_now: bool


class DutiesResponse(BaseModel):
    duties: list[DutyStudentRow]
