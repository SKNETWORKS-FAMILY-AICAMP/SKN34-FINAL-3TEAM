"""#87 M2 HTTP 계약. 내부 저장용 항목 키는 학습 순서와 동일하다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, model_validator

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
ESSAY_ITEMS = ("org", "cont", "exp")
EssayType = Literal["설명글", "글짓기", "주장", "찬성반대", "대안제시"]

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class M2Request(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"inputType": {"const": "ESSAY"}},
                        "required": ["inputType"],
                    },
                    "then": {
                        "required": ["essayType"],
                        "properties": {"essayType": {"type": "string"}},
                    },
                }
            ]
        },
    )
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
    text: Annotated[str, StringConstraints(min_length=1, max_length=50000, pattern=r"\S")]
    grade: int = Field(ge=3, le=6)
    inputType: Literal["NARRATIVE", "ESSAY"]
    keywords: list[Keyword] = Field(default_factory=list, max_length=100)

    essayType: EssayType | None = None

    @model_validator(mode="after")
    def require_essay_type(self):
        if self.inputType == "ESSAY" and self.essayType is None:
            raise ValueError("essayType is required for ESSAY")
        return self


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


class EssayScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    org: int = Field(ge=0, le=3)
    cont: int = Field(ge=0, le=3)
    exp: int = Field(ge=0, le=3)


class EssayRawScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    org: FiniteFloat
    cont: FiniteFloat
    exp: FiniteFloat


class ModelIdentity(BaseModel):
    name: str
    version: str
    revision: int = Field(ge=1)


class M2Active(BaseModel):
    active: Literal[True] = True
    inputType: Literal["NARRATIVE", "ESSAY"]
    scores: Scores | EssayScores
    rawScores: RawScores | EssayRawScores
    model: ModelIdentity

    @model_validator(mode="after")
    def consistent_score_shape(self):
        essay = isinstance(self.scores, EssayScores)
        if essay != isinstance(self.rawScores, EssayRawScores):
            raise ValueError("scores and rawScores must have the same keys")
        if essay and self.inputType != "ESSAY":
            raise ValueError("three-domain scores require ESSAY")
        return self


class M2Inactive(BaseModel):
    active: Literal[False] = False
