from datetime import datetime

from pydantic import BaseModel, field_validator


class DutyAssignRequest(BaseModel):
    date: str
    group_id: int
    student_ids: list[int]

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v


class DutyStudentRow(BaseModel):
    id: int
    name: str
    tg_id: int
    date: str | None = None
    is_absent_now: bool


class DutiesResponse(BaseModel):
    duties: list[DutyStudentRow]
