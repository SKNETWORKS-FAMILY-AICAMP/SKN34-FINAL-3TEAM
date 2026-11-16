"""리포트 설명 sLLM 입력. 문구를 바꾸면 PROMPT_VERSION을 올림 (NFR-DAT-02).

user 형식은 #475 학습 쌍의 입력과 같아야 함(docs/report/ai.md): 항목 하나에 이유 문장 하나.
학생 글만 넣고 학생 이름·ID는 넣지 않음 (NFR-SEC-03).
"""

PROMPT_VERSION = "report-explanation@1"

SYSTEM = """\
너는 초등학생 글의 한 평가 항목에 대해 전문가가 쓴 이유 문장을 쓴다.
항목 이름과 점수를 보고 학생 글의 어떤 점 때문에 그렇게 평가했는지 한두 문장으로 쓴다.
점수·등급·숫자는 쓰지 않는다."""


def build_user(grade: int, item_label: str, score: int, text: str) -> str:
    return f"[학년] 초{grade} [항목] {item_label} [점수] {score}\n{text.strip()}"
