"""learning의 학생 풀이 구조를 보존한다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

NonBlank = Annotated[str, Field(pattern=r"\S")]


class StudentSolution(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    steps: list[str] = Field(min_length=1)
    finalAnswer: NonBlank

    @field_validator("steps")
    @classmethod
    def require_nonblank_step(cls, steps: list[str]) -> list[str]:
        if not any(step.strip() for step in steps):
            raise ValueError("내용이 있는 풀이 단계가 필요합니다")
        return steps


class M1Request(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    problem: NonBlank
    answerKey: NonBlank
    solution: StudentSolution


class M1Inactive(BaseModel):
    active: Literal[False] = False
