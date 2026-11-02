"""#87 M2 HTTP 계약. 내부 저장용 항목 키는 학습 순서와 동일하다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints

ITEMS = (
    "hol",
    "task_1",
    "content_1",
    "content_2",
    "content_3",
    "organization_1",
    "organization_2",
    "expression_1",
    "expression_2",
)
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class M2Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
    text: Annotated[str, StringConstraints(min_length=1, max_length=50000, pattern=r"\S")]
    grade: int = Field(ge=3, le=6)
    inputType: Literal["NARRATIVE", "ESSAY"]
    keywords: list[Keyword] = Field(default_factory=list, max_length=100)


class Scores(BaseModel):
    hol: int = Field(ge=1, le=4)
    task_1: int = Field(ge=1, le=5)
    content_1: int = Field(ge=1, le=5)
    content_2: int = Field(ge=1, le=5)
    content_3: int = Field(ge=1, le=5)
    organization_1: int = Field(ge=1, le=5)
    organization_2: int = Field(ge=1, le=5)
    expression_1: int = Field(ge=1, le=5)
    expression_2: int = Field(ge=1, le=5)


class RawScores(BaseModel):
    hol: FiniteFloat
    task_1: FiniteFloat
    content_1: FiniteFloat
    content_2: FiniteFloat
    content_3: FiniteFloat
    organization_1: FiniteFloat
    organization_2: FiniteFloat
    expression_1: FiniteFloat
    expression_2: FiniteFloat


class ModelIdentity(BaseModel):
    name: str
    version: str
    revision: int = Field(ge=1)


class M2Active(BaseModel):
    active: Literal[True] = True
    inputType: Literal["NARRATIVE", "ESSAY"]
    scores: Scores
    rawScores: RawScores
    model: ModelIdentity


class M2Inactive(BaseModel):
    active: Literal[False] = False
