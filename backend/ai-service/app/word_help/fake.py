"""개발용 가짜 설명 (WORD_HELP_PROVIDER=fake, #599).

LLM 없이 질문에서 묻는 말·조사를 뗀 글자를 표제어로 쓰고, 사전 첫 후보를 골라
`{표제어}는 {원문}라는 뜻이야.`로 답한다(같은 요청 = 같은 응답). 사전은 실제로 부르고 사용량은
남기지 않는다.
"""

from app.word_help.dictionary import Candidate
from app.word_help.prompts import GeneratedWordHelp

FAKE_MODEL = "fake-word-help-v1"


def generated(headword: str, candidates: list[Candidate]) -> GeneratedWordHelp:
    definition = candidates[0].definition.rstrip(". ")
    return GeneratedWordHelp(
        kind="WORD", sense=0, easy=f"{headword}는 {definition}라는 뜻이야.", example=""
    )
