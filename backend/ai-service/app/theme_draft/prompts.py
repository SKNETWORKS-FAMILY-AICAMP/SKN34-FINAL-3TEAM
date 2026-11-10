"""주간 테마 초안 프롬프트 (theme-draft@1, #437).

줄거리·미션 이야기 조각·대화·글 검토·미션 검토 묶음.
문구를 바꾸면 PROMPT_VERSION을 올림 (NFR-DAT-02). 문구는 텍스트 시험(2026-11-10, 처음 보는
주제 초3·초4·초5·초6 통과)에서 검증한 것이다. LLM 입력에 학생 정보·학생 답은 넣지 않는다.
"""

import json

from app.followup.prompts import grade_style
from app.mission_draft.models import Draft, MissionDraftRequest
from app.mission_draft.prompts import THINKING_LABEL
from app.theme_draft.checks import (
    CANDIDATES,
    CLUE_TYPES,
    DAY_KO,
    DAY_TYPE,
    DAYS,
    DIALOGUE_LINES,
    HINTS,
    Theme,
    clue_list,
)
from app.theme_draft.models import ThemeDraftRequest

PROMPT_VERSION = "theme-draft@1"

GRADE_CLUE = {  # 학년별 차이는 단서 복잡도(기준안)
    3: "단서 하나에 사실 하나. 읽으면 바로 그 후보가 왜 안 되는지 알 수 있게",
    4: "단서 하나에 사실 하나. 읽으면 바로 그 후보가 왜 안 되는지 알 수 있게",
    5: "두 사실을 이어야 알 수 있는 단서를 1~2개 둘 수 있음",
    6: "두 사실을 이어야 알 수 있는 단서를 2개까지 둘 수 있음",
}

# 줄 길이 제한 때문에 문자열을 이어 붙였을 뿐 한 규칙은 한 줄이다
PLAN_SYSTEM = (
    "너는 초등학생 사고력 학습 서비스의 한 주 이야기(테마)를 설계한다. 만든 테마는 사람이 검수한 "
    "뒤에만 학생에게 공개된다.\n"
    "한 주는 시작 이야기 → 월~금 하루 한 문제 → 토요일 종료 이야기로 이어진다. 문제는 따로 만든다. "
    "너는 이야기 틀과 큰 질문·단서를 만든다.\n"
    "\n"
    "이야기\n"
    "- 주인공은 솜뭉치 캐릭터 '뭉치'(모습은 정해져 있어 characters에 넣지 않는다). 이야기 속 "
    "등장인물(characters)은 "
    "뭉치를 뺀 1~3명, 흔한 이름의 또래나 동네 어른. 실존 인물·상표 금지. look은 그림을 그릴 사람이 "
    "장면마다 같은 "
    "모습으로 그릴 수 있게 쓰는 겉모습(옷·머리·소지품).\n"
    "- outfit은 이 테마에서 뭉치가 입는 옷. 실제 제복·휘장을 그대로 쓰지 않는다. styleNote는 이 "
    "테마 그림의 색·분위기 메모.\n"
    "- 학생이 집·학교·마을에서 직접 보는 사물과 일만. 범죄·폭력·위험·무서운 일 금지. 시각은 '오후 "
    "3시 10분'처럼 12시간제.\n"
    "- days는 MON~FRI 다섯 장면이고 thinkingType은 주어진 요일 배치 그대로. place는 그날 장소(20자 "
    "이내), 다음 날 장소는 "
    "걸어서 이어지는 가까운 곳. sceneNote는 그 장면 메모(150자 이내): 누가 어디서 무엇을 하고 "
    "무엇이 보이는지. 그날 문제의 "
    "성취기준 활동이 자연스럽게 나올 거리(물건·불편한 일·상황)를 넣되, 그날 문제의 답(만들 "
    "물건·계산 결과·고를 답·바뀐 "
    "생각)은 쓰지 않는다(학생이 생각할 몫). 뭉치가 지나는 길에 탁자 같은 물체를 두지 않고, 소품은 "
    "쓰임새대로 쓴다.\n"
    "- intro는 사건과 큰 질문을 소개하는 시작 이야기(200자 이내). outro는 토요일 종료 이야기(300자 "
    "이내): 정답을 밝히고 "
    "다섯 단서로 어떻게 정답만 남는지 짧게 정리한다.\n"
    "\n"
    "큰 질문·후보·정답\n"
    "- bigQuestion은 누구·어디·무엇으로 답이 하나로 정해지는 질문(40자 이내). 지나간 일을 "
    "묻는다(예: 마지막으로 간 곳, "
    '마지막으로 둔 곳, 누가 가져갔는지). "지금 어디에 있을까"처럼 현재를 묻지 않는다(지난 '
    "흔적·목격으로는 지금 위치를 "
    "증명할 수 없음). candidates는 주어진 개수, 각 2~10자 명사(예: 빵집 뒤뜰). 후보 이름에 색 "
    "낱말(빨간·파란·노란·초록 등)을 "
    "쓰지 않는다. answer는 후보 중 하나.\n"
    "- 정답 이름은 outro에만 쓴다. title·world·intro·bigQuestion·styleNote·outfit과 days의 "
    "place·sceneNote·clue에 쓰지 않는다.\n"
    "\n"
    "특징 표(features) — 정답 논리는 이 표로 코드가 확인한다\n"
    "- 후보를 가려낼 특징 2~5개. 특징마다 name과 values(후보마다 값 하나, [{candidate, value}]). "
    "값은 짧은 낱말이고, "
    "같은 특징 안에서 같은 값은 같은 낱말로 쓴다.\n"
    "- 특징은 되도록 그 주 요일별 성취기준 내용에서 고른다(예: 사는 곳·환경을 배우면 주변 바닥이나 "
    "물기, 길이·거리를 "
    "계산하면 거리, 무게를 비교하면 무게). 어울리는 것이 없으면 장면에서 고른다.\n"
    "- 값은 그 장소·물건에 실제로 그럴 법해야 한다.\n"
    "- standardCode: 그 특징을 그날 성취기준 내용에서 골랐으면 그 성취기준 코드, 장면에서 골랐으면 "
    "null.\n"
    "\n"
    "단서\n"
    "- 요일마다 clue 하나(대화 한 줄로 그대로 나가므로 공백 포함 30자 안팎, 40자를 넘으면 안 됨). "
    "말한 사람은 붙이지 "
    "않는다. 단서는 그날 장면의 이야기 속 사실이다. 그날 문제 활동의 결과(계산값·학생 답)에서 "
    "만들지 않는다.\n"
    "- condition: 그 단서가 말하는 조건. kind는 RULE(후보를 뺌) 또는 HINT(빼지 않고 기울임), "
    "feature는 표의 특징 이름, "
    "allowed는 그 단서로 보아 가능한 값 목록(표에 있는 값만).\n"
    "- clue 문장은 그 condition만 말한다. allowed 값 낱말을 모두 그대로 쓰고(값이 둘이면 '모래나 "
    "나무'처럼 둘 다), 허용 밖 "
    "값 낱말은 쓰지 않는다. 그 특징에 대한 사실만 쓰고 표에 없는 새 사실을 더하지 않는다.\n"
    "- 단서는 찾는 대상 자체에 대한 증거다: 대상이 지나가거나 머문 곳에 남긴 흔적(발자국·떨어뜨린 "
    "것 등), 대상을 본 "
    "사람의 목격, 대상을 찍은 사진·적은 기록(언제의 것인지 함께). 대상은 아직 찾지 못했으므로 대상 "
    "몸이나 겉에 남은 "
    '자국·묻은 것("톱니에 물방울 자국이 있었다", "물건 아래에 책상 면이 닿아 있었다")은 볼 수 없어 '
    "쓰지 않는다. 그 증거가 "
    '"대상이 그 특징을 가진 곳·사람·때에 있었다"를 보여 주어야 한다. 장소의 특징만 설명하는 '
    '말("○○는 바닥이 평평했다"), '
    '동물·물건의 일반 상식("강아지는 그늘을 좋아한다"), 해야 할 일·지시("실내에 두라고 적혀 '
    '있다")는 증거가 아니므로 '
    "쓰지 않는다.\n"
    "- RULE: rulesOut은 allowed 밖 값을 가진 후보 전부, 정답의 값은 allowed 안. 찾지 못한 "
    '것("없었다")만으로 빼지 않고, '
    "그 값 때문에 왜 답이 될 수 없는지 다른 가능성이 남지 않게 쓴다(시간이면 앞뒤가 다 막히게, "
    "크기면 단단한 물건으로).\n"
    "- RULE은 그때까지 남은 후보를 적어도 하나 새로 뺀다(이미 빠진 후보만 빼는 단서는 HINT로 "
    "쓴다).\n"
    "- HINT: rulesOut은 빈 배열. 그때까지 남은 후보는 모두 allowed 값을 가져야 한다. 남은 후보를 "
    "하나라도 빼는 내용이면 "
    "HINT가 아니라 RULE로 쓰고 rulesOut에 적는다. 이미 빠진 후보는 allowed 밖이어도 된다(그래서 "
    "정답만 남은 뒤의 힌트는 "
    "정답만 가리켜도 됨).\n"
    "- 정답은 어떤 단서로도 빠지지 않는다. 틀린 후보는 각각 적어도 한 RULE 단서에서 빠진다. 마지막 "
    "틀린 후보는 목요일(THU)"
    "이나 금요일(FRI) 단서에서 빠진다(수요일까지는 후보가 2개 이상 남음).\n"
    "- target은 찾는 대상(사라진 동물·물건·사람)의 이름이다. 찾는 대상은 종료 이야기 전까지 찾지 "
    "못한 상태다. 어느 "
    "장면에서도 지금 있는 곳이 보이거나 말을 하지 않는다. 목격은 지나간 일로 쓴다.\n"
    "- clueType은 주어진 종류 중 하나이고 다섯 단서가 모두 다른 종류다.\n"
    "- evidence: 단서의 증거 종류(kind)와 그 증거가 생긴 때(when). kind는 TRACE(대상이 지나가거나 "
    "머문 곳에 남은 흔적), "
    "SIGHTING(대상을 본 사람의 목격), RECORD(대상을 찍은 사진·적은 기록) 중 하나. when은 큰 질문이 "
    "묻는 그때(예: "
    "마지막으로 둔 때)와 맞는 때로 쓰고, 다섯 단서가 모두 같은 그때를 가리킨다.\n"
    "- 위 예시는 특징을 고르는 방향일 뿐이다. 예시 낱말·문장을 그대로 쓰지 말고 이 테마에 맞게 "
    "새로 정한다.\n"
)


def plan_user(request: ThemeDraftRequest, feedback: list[tuple[str, list[str]]]) -> str:
    """feedback: 이전 시도 실패 [(stage, reasons)] — 요청 previousFailures와 그래프 안 재생성 "
    "사유."""
    grade = request.grade
    lines = [
        f"학년: 초{grade}",
        f"학년에 맞는 말투: {grade_style(grade)}",
        f"후보 개수: {CANDIDATES[grade]}개",
        f"단서 복잡도: {GRADE_CLUE[grade]}",
        f"단서 종류(clueType): {', '.join(CLUE_TYPES)}",
    ]
    if request.topic:
        lines.append(f"주제: {request.topic}")
    lines += [
        "",
        "요일 배치와 그날 문제의 성취기준(문제는 따로 만든다. 장면에 그 활동이 자연스럽게 나올 "
        "거리를 넣는다):",
    ]
    for day, thinking in DAY_TYPE.items():
        mission = request.mission_for(thinking)  # type: ignore[arg-type]
        standards = "; ".join(f"{s.code} {s.statement}" for s in mission.standards)
        lines.append(f"- {day}({DAY_KO[day]}): {THINKING_LABEL[thinking]} / {standards}")
    if feedback:
        lines += ["", "이전 테마가 검사를 통과하지 못했다. 아래를 고쳐서 새로 만든다:"]
        lines += [f"- {stage}: {reason}" for stage, reasons in feedback for reason in reasons]
    return "\n".join(lines)


def knowledge_lines(knowledge: list[str] | None) -> list[str]:
    """RAG(#470) 근거 자리. 지금은 기능이 꺼져 있어 비어 있다. 켜지면 성취기준 해설·유형 출제 지침 "
    "조각."""
    if not knowledge:
        return []
    return ["근거 자료(교육과정 고시·유형 출제 지침, 문제의 바탕으로만 쓴다):"] + [
        f"- {k}" for k in knowledge
    ]


def story_text(theme: Theme, day: str, grade: int, knowledge: list[str] | None = None) -> str:
    """미션 초안 프롬프트 뒤에 붙이는 테마 이야기 조각(생각 열기 개수·찾는 대상 포함, 정답은 주지 "
    "않음)."""
    d = next(x for x in theme["days"] if x["day"] == day)
    names = ", ".join(c["name"] for c in theme["characters"])
    lines = [
        "",
        "테마 이야기 조각(이 미션은 주간 테마의 한 장면이다):",
        f"- 테마: {theme['title']} / {theme['world']}",
        f"- 등장인물: 뭉치(솜뭉치 모양의 주인공 캐릭터), {names}",
        f"- 오늘({DAY_KO[day]}요일) 장소: {d['place']}",
        f"- 오늘 장면: {d['sceneNote']}",
        "테마 규칙:",
        "- 문제는 이 장소와 장면에서 뭉치와 등장인물이 겪는 일로 쓰고, 이 글만 읽고 풀 수 있게 "
        "한다. 관찰·비교할 내용"
        "(사진·그림 속 모습, 수, 생김새)은 question 글에 직접 쓴다. 그림에만 있는 정보로 풀게 "
        "하지 않는다.",
        "- 질문이 어떤 글을 비교·점검·고쳐 쓰게 하면(예: 처음 쓴 글과 고친 글) 그 글 자체를 "
        "question 안에 짧게 넣는다. "
        "학생이 질문 글만 읽고 답할 수 있어야 한다.",
        "- 읽을 글·자료가 필요하면 question 안에 넣는다. guide에는 풀이 안내만 쓴다. 읽을 글에 "
        "나오는 낱말·문장은 "
        "forbiddenTerms에 넣지 않는다(학생이 그 글을 읽고 답함). forbiddenTerms에 수는 넣지 "
        "않는다(정답 수는 정답 키로 "
        "따로 검사함).",
        "- 큰 질문의 사건에 관한 새 사실(흔적·목격·기록 등)을 지어내지 않는다.",
        f"- 찾는 대상: {theme.get('target') or ''}. 아직 찾지 못했으므로 문제에서 지금 보거나 "
        "만지거나 곁에 있는 것처럼 "
        "쓰지 않는다.",
        f"- 생각 열기 질문(hints)은 정확히 {HINTS[grade]}개. 장면 그림 속 물건을 가리킬 수 있게 "
        "쓰되 정답·풀이는 주지 않는다.",
    ]
    if day == "FRI":
        lines += [
            f"- 이번 주 큰 질문: {theme['bigQuestion']} / 후보: {', '.join(theme['candidates'])}",
            "- 이번 주 단서(guide에는 코드가 이 목록을 넣으니 guide는 null로 둔다):",
            *[f"  {x}" for x in clue_list(theme, 5)],
            "- 질문은 위 성취기준의 행동을 학생이 직접 하게 하고, 이번 주 단서는 그 소재로 쓸 수 "
            "있다. 큰 질문의 답이 "
            "무엇인지는 질문·생각 열기 질문·예시 답에 쓰지 않는다.",
            "- 돌아보기·쓰기 점검 문제라면 점검하거나 비교할 글(예: 뭉치가 처음 쓴 메모와 고친 "
            "메모)을 question 안에 직접 "
            "넣는다. 예시 답은 질문이 묻는 것(처음 생각·바뀐 생각·까닭 등)을 하나도 빠짐없이 "
            "답한다.",
        ]
    else:
        lines += [
            "- 오늘까지 알려진 사건 단서(대화가 문제 앞에서 따로 전함):",
            *[f"  {x}" for x in clue_list(theme, DAYS.index(day) + 1)],
            "- 오늘 장면과 사건 자료(장소·인물·물건, 위 단서)는 문제 소재로 쓸 수 있다. "
            "성취기준의 행동을 하게 하는 것이 먼저다.",
            "- 큰 질문의 답(어느 후보가 답인지)을 쓰거나 묻지 않는다. 문제를 사건 "
            "풀기(누구·어디·무엇 맞히기)로 만들지 않는다.",
            "- 문제의 답이 단서를 알려 주는 구조로 만들지 않는다(단서는 대화가 전한다).",
        ]
    return "\n".join(lines + knowledge_lines(knowledge))


def mission_extra(
    theme: Theme,
    day: str,
    grade: int,
    theme_feedback: list[str],
    knowledge: list[str] | None = None,
) -> str:
    """미션 초안 생성에 덧붙일 글: 이야기 조각 + 테마 검사·검토 사유(기존 검사 사유는 미션 초안 "
    "장치로)."""
    text = story_text(theme, day, grade, knowledge)
    if theme_feedback:
        fixes = list(dict.fromkeys(theme_feedback))
        text += (
            "\n\n이전 초안이 테마 검사를 통과하지 못했다. 아래를 고쳐서 새로 만든다:\n"
            + "\n".join(f"- {x}" for x in fixes)
        )
    return text


DIALOGUE_SYSTEM = (
    "너는 초등학생 사고력 학습 서비스에서 문제 시작 전에 나오는 짧은 대화를 쓴다. 만든 대화는 "
    "사람이 검수한 뒤에만 공개된다.\n"
    "규칙\n"
    "- 화자(speaker)는 '뭉치'나 주어진 등장인물 이름만. 찾고 있는 대상(사라진 동물·물건)은 말하지 "
    "않고 대화에 나타나지도 않는다.\n"
    "- recap: 화~금은 뭉치가 앞 요일 문제까지 알아낸 것을 한 줄로 요약한다(주어진 '앞 요일까지의 "
    "단서'만, 학생이 문제를 "
    "몰아서 풀 수 있어 '어제'라고 쓰지 않음, 새 사실 금지). 지금까지 빠진 장소·사람만 짧게 말한다. "
    "빠진 것이 아직 없으면 "
    "가장 최근 단서 하나만 짧게. 단서를 나열하지 않는다. 25자 안팎. 월요일은 null.\n"
    "- 오늘 단서 문장은 코드가 대화 마지막 줄로 그대로 넣는다. clueSpeaker에 그 단서를 말할 "
    "사람(뭉치나 등장인물)을 고른다. "
    "단서 문장이 그 사람 이름으로 시작하면 다른 사람을 고른다.\n"
    "- lines: 오늘 상황을 짧게 말해 단서 줄로 이어지게 한다. 단서 내용을 lines에서 다시 말하지 "
    "않는다. 단서에 없는 새 사실을 "
    "더하지 않는다.\n"
    "- 장면 메모를 그대로 옮기지 말고, 인물이 그 자리에서 실제로 할 법한 짧은 말로 쓴다.\n"
    "- 단서가 무엇을 뜻하는지, 어느 장소·사람을 가리키는지 해석하지 않는다(학생이 추리할 몫). "
    "단서에 나온 이름 말고 다른 "
    "장소·사람 이름을 새로 꺼내지 않는다.\n"
    "- lines 줄 수는 주어진 범위(recap·단서 줄 제외, 0줄일 수 있음)를 지킨다. 한 줄에 한 가지만, "
    "25자 안팎(공백 포함 40자를 "
    "넘으면 안 됨).\n"
    "- recap과 text에는 말만 쓰고 앞에 '이름:'을 붙이지 않는다.\n"
    "- 오늘 문제의 값·풀이 방법·답(만들 물건 같은 답이 될 생각 포함), 예시 답 내용, 금지어는 쓰지 "
    "않는다.\n"
    '- 말하는 사람은 자기 이름을 3인칭으로 부르지 않는다("수아: 수아는…" 금지). 학년에 맞는 말투.\n'
)


def llm_line_range(grade: int, day: str) -> tuple[int, int]:
    """LLM이 쓸 lines 줄 수: 학년 범위(recap·단서 줄 포함)에서 단서 줄과 화~금 recap을 뺀 값."""
    lo, hi = DIALOGUE_LINES[grade]
    fixed = 1 + (1 if day != "MON" else 0)
    return max(lo - fixed, 0), max(hi - fixed, 0)


def dialogue_user(theme: Theme, day: str, draft: Draft, grade: int, feedback: list[str]) -> str:
    d = next(x for x in theme["days"] if x["day"] == day)
    i = DAYS.index(day)
    lo, hi = llm_line_range(grade, day)
    count = f"{lo}줄" if lo == hi else f"{lo}~{hi}줄"
    lines = [
        f"학년: 초{grade}",
        f"학년에 맞는 말투: {grade_style(grade)}",
        f"lines 줄 수(recap·단서 줄 제외): {count}",
        f"등장인물: 뭉치, {', '.join(c['name'] for c in theme['characters'])}",
        f"오늘({DAY_KO[day]}요일) 장소: {d['place']}",
        f"오늘 장면: {d['sceneNote']}",
        f"오늘 단서: {d['clue']}",
        f"찾는 대상(대화에서 말하지 않고 나타나지 않음): {theme.get('target') or ''}",
        "앞 요일까지의 단서: "
        + (" / ".join(clue_list(theme, i)) if i else "없음(월요일, recap은 null)"),
        f"오늘 문제(대화 뒤에 나옴, 값·풀이·답을 대화에 쓰지 않음): {draft.question}",
        f"금지어: {', '.join(draft.forbidden_terms) or '없음'}",
    ]
    if feedback:
        lines += [
            "",
            "이전 대화가 검사를 통과하지 못했다. 고칠 점:",
            *[f"- {x}" for x in dict.fromkeys(feedback)],
        ]
    return "\n".join(lines)


REVIEW_SYSTEM = (
    "너는 초등 교육 콘텐츠 검토자다. 주간 테마 초안(이야기 틀·단서·문제 5개·대화 5개)을 아래 다섯 "
    "항목으로 검토한다.\n"
    "항목마다 verdict를 PASS(문제 없음)·WARN(애매해서 사람이 볼 것)·FAIL(분명한 결함, 고쳐야 함) "
    "중 하나로, 문제가 있는 "
    "요일(days)과 근거 한두 문장(reason)을 쓴다.\n"
    "분명한 결함만 FAIL로 한다. 더 좋게 고칠 수 있다는 이유만으로 FAIL로 하지 않는다. 다섯 항목을 "
    "모두 한 번씩 쓴다.\n"
    "판정 눈높이: 이 이야기는 그 학년 아이가 읽는 추리다. 그 학년 아이가 읽고 상식으로 납득하면 "
    "통과다. 이야기에 나오지 "
    "않은 가능성(나중에 옮겨졌을 수도, 다른 소리도 났을 수도, 창문으로 들어갔을 수도 등)을 "
    "상상해서 FAIL로 하지 않는다. "
    "그런 의문은 WARN으로 남긴다(사람 검토에서 판단). FAIL은 글에 실제로 있는 결함에만 준다: 단서 "
    "문장과 조건(특징·허용 "
    "값)이 다름, 이야기 속 사실끼리 모순, 찾는 대상이 종료 이야기 전에 나타나거나 말함, 아직 찾지 "
    "못한 대상 몸·겉의 "
    '자국이나 상태를 직접 본 것처럼 씀(이야기 속 사실끼리 모순), 찾지 못한 것("없었다")만으로 뺌, '
    "장소 설명·일반 상식·"
    "지시를 증거처럼 씀, 목요일 전에 정답이 정해짐.\n"
    "CLUE_LOGIC: 정답 논리(어느 후보가 언제 빠지고 정답만 남는지)는 특징 표(features)와 단서 "
    "조건(condition)으로 코드가 "
    '이미 확인했다. 너는 다음을 본다. 각 단서가 찾는 대상 자체의 흔적·목격·기록으로 "대상이 그 '
    "특징을 가진 곳·사람·때에 "
    '있었다"를 보여 주는지(장소 특징 설명·일반 상식·지시만 말하면 결함). 큰 질문이 지나간 일을 '
    "묻는지. 각 단서의 "
    "evidence(종류·때)가 단서 문장과 맞고, 때가 큰 질문이 묻는 그때를 가리키는지(서로 다른 때의 "
    "증거를 섞지 않는지). 각 "
    "단서 문장이 그 조건(특징·allowed 값)을 그대로 말하고 표에 없는 새 사실을 더하지 않는지. 표의 "
    "값이 그 장소·물건에 "
    "실제로 그럴 법한지. RULE 단서가 찾지 못한 것만으로 빼지 않고 그 값 때문에 답이 될 수 없음이 "
    "그 학년 눈높이에서 "
    "분명한지. HINT 단서가 목요일 전에 정답을 정해 버리지 않는지. 찾는 대상이 종료 이야기 전에 "
    "나타나거나 말하지 않는지. "
    "단서가 그날 장면의 이야기 속 사실인지(문제 활동의 결과가 아닌지).\n"
    "ANSWER_HINT: 종료 이야기(outro) 말고 학생이 보는 글(intro·장면·문제·안내·생각 열기 질문·예시 "
    "답·대화)이 정답을 직접 "
    "쓰거나 목요일 전에 정답을 확정하지 않는지. 월~수의 빈 rulesOut 단서가 정답 하나만 가리키지 "
    "않고 남은 다른 후보에도 "
    "맞는지. 대화가 단서를 해석해 답을 알려 주지 않는지. 장면·대화가 그날 문제의 답(만들 물건·계산 "
    "결과 등)을 미리 알려 "
    "주지 않는지.\n"
    "GRADE_VOCAB: 그 학년이 읽고 풀 수 있는 낱말·분량인지, 그 학년에 배우지 않은 개념이 없는지.\n"
    "STANDARD_FIT: 각 문제가 주어진 성취기준의 행동을 학생이 직접 하게 하고 생각 유형과 맞는지. "
    "학생 혼자 글로 답하는 "
    "미션이므로 협력·발표·실험 수행처럼 혼자 할 수 없는 부분은 보지 않고 핵심 "
    "행동(설명·구분·설계·계산·점검 등)을 본다. "
    "정답 키·예시 답이 문제와 맞는지(계산이면 값이 맞는지).\n"
    "SAFETY: 폭력·범죄·위험·무서운 내용, 차별, 실존 인물·상표, 개인정보가 없는지.\n"
)

MISSION_FIELDS = (
    "title",
    "question",
    "guide",
    "choices",
    "categories",
    "answerKey",
    "exampleAnswer",
    "hints",
)


def review_user(
    request: ThemeDraftRequest,
    theme: Theme,
    drafts: dict[str, Draft],
    dialogues: dict[str, list[dict]],
) -> str:
    days = []
    for d in theme["days"]:
        mission = request.mission_for(d["thinkingType"])
        draft = drafts[d["day"]].model_dump(by_alias=True)
        days.append(
            {
                "day": d["day"],
                "thinkingType": d["thinkingType"],
                "inputType": mission.input_type,
                "standards": [
                    {"code": s.code, "statement": s.statement} for s in mission.standards
                ],
                "place": d["place"],
                "sceneNote": d["sceneNote"],
                "clue": d["clue"],
                "condition": d["condition"],
                "evidence": d["evidence"],
                "rulesOut": d["rulesOut"],
                "mission": {k: draft.get(k) for k in MISSION_FIELDS},
                "dialogue": dialogues.get(d["day"], []),  # 끝내 실패해 빠진 대화는 빈 줄로 검토
            }
        )
    summary = {
        k: theme[k]
        for k in ("title", "world", "intro", "outro", "bigQuestion", "candidates", "answer")
    }
    summary |= {
        "protagonist": "뭉치: 솜뭉치 모양의 주인공 캐릭터(찾는 대상이 아님)",
        "characters": theme["characters"],
        "features": theme["features"],
    }
    return json.dumps(
        {"grade": f"초{request.grade}", "theme": summary, "days": days}, ensure_ascii=False
    )


MISSION_REVIEW_SYSTEM = (
    "너는 초등 교육 콘텐츠 검토자다. 미션(문제) 하나를 아래 세 항목으로 검토한다.\n"
    "항목마다 verdict를 PASS(문제 없음)·WARN(애매해서 사람이 볼 것)·FAIL(분명한 결함, 고쳐야 함) "
    "중 하나로 쓰고 근거 한두 "
    "문장(reason)을 쓴다. 세 항목을 모두 한 번씩 쓴다. 전체 verdict는 항목 중 가장 나쁜 것.\n"
    "분명한 결함만 FAIL로 한다. 더 좋게 고칠 수 있다는 이유만으로 FAIL로 하지 않는다.\n"
    "EXAMPLE_COMPLETE: 예시 답(서술·논술은 exampleAnswer, 고르기·순서·분류·풀이는 answerKey와 예시 "
    "답)이 질문이 묻는 것을 "
    "하나도 빠짐없이 답하는지. 질문이 둘 이상을 물으면(예: 처음 생각·바뀐 생각·까닭) 모두 들어 "
    "있어야 한다. 계산이면 값이 "
    "맞는지.\n"
    "STANDARD_FIT: 질문이 주어진 성취기준의 핵심 행동을 학생이 직접 하게 하고 생각 유형과 맞는지. "
    "학생 혼자 글로 답하는 "
    "미션이므로 협력·발표·실험 수행처럼 혼자 할 수 없는 부분은 보지 않는다.\n"
    "MATERIAL: 답하는 데 필요한 것(읽을 글·비교할 글·수·관찰할 모습)이 질문 글 안에 다 있는지. "
    "그림에만 있는 정보나 주어지지 "
    "않은 글(예: '처음 쓴 글'을 비교하라는데 그 글이 없음)에 기대면 결함. target이 주어지면, "
    "문제가 그 대상을 지금 보거나 "
    "곁에 있는 것처럼 쓰면 결함(아직 찾지 못한 대상).\n"
)


def mission_review_user(
    request: MissionDraftRequest,
    draft: Draft,
    grade: int,
    target: str | None,
    knowledge: list[str] | None = None,
) -> str:
    """미션 하나만 본다(테마 정답·단서 논리는 넣지 않음)."""
    d = draft.model_dump(by_alias=True)
    body: dict = {
        "grade": f"초{grade}",
        "thinkingType": THINKING_LABEL[request.thinking_type],
        "inputType": request.input_type,
        "standards": [{"code": s.code, "statement": s.statement} for s in request.standards],
        "mission": {k: d.get(k) for k in MISSION_FIELDS},
    }
    if knowledge:  # RAG(#470) 근거 자리, 지금은 비움
        body["knowledge"] = knowledge
    if target:
        body["target"] = f"{target}(이야기에서 아직 찾지 못한 대상)"
    return json.dumps(body, ensure_ascii=False)
