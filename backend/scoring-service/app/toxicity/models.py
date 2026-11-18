"""답변 표현 분류 HTTP 계약 (api-spec 4.3.4). 칸별 결과·점수·걸린 말은 응답에 없다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.m2.models import ModelIdentity

MAX_TEXTS = 20
MAX_CHARS = 1500

Text = Annotated[str, StringConstraints(min_length=1, max_length=MAX_CHARS, pattern=r"\S")]


class ToxicityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    texts: list[Text] = Field(
        min_length=1,
        max_length=MAX_TEXTS,
        description="학생이 쓴 칸마다 1개, 칸 순서대로. 모든 칸 합계 1~1,500자",
    )

    @model_validator(mode="after")
    def total_length(self):
        if sum(len(text) for text in self.texts) > MAX_CHARS:
            raise ValueError("texts exceed 1500 characters in total")
        return self


class ToxicityActive(BaseModel):
    active: Literal[True] = True
    flagged: bool
    review: bool = Field(
        description="flagged가 아니고 한 창이라도 review_threshold 이상이면 true(#725). "
        "review_threshold가 없는 모델은 항상 false"
    )
    model: ModelIdentity


class ToxicityInactive(BaseModel):
    active: Literal[False] = False
