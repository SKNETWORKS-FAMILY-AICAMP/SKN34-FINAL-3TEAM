"""주간 테마 초안 프롬프트 (theme-draft@1, #437).

줄거리·미션 이야기 조각·대화·글 검토·미션 검토 묶음.
문구를 바꾸면 PROMPT_VERSION을 올림 (NFR-DAT-02). 문구는 텍스트 시험(2026-11-10, 처음 보는
주제 초3·초4·초5·초6 통과)에서 검증한 것이다. 해결사 뭉치·시작 콘티 순서·증거 발견 줄·수사 연결
문장·단서 미션 뒤 공개(사용자 결정 2026-11-11)는 배포 전이라 같은 버전에서 고쳤고 실제 LLM
실측은 아직이다. LLM 입력에 학생 정보·학생 답은 넣지 않는다.
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
    DIALOGUE_LINES,
    HINTS,
    Theme,
    feature_table,
    text_at,
    text_max,
    theme_day,
)
from app.theme_draft.models import ThemeDraftRequest

PROMPT_VERSION = "theme-draft@1"
# 글로 대신하는 활동 원칙(사용자 결정 2026-11-11). 미션 생성·미션 검토·글 검토·예시 답 고쳐
# 쓰기에 같은 글을 넣어 기준이 어긋나지 않게 함
TEXT_ONLY = (
    "학생은 글로만 답한다. 듣기·말하기·발표·조사·관찰·실험·그리기·만들기·사전 찾기·검색처럼 "
    "글로 직접 할 수 없는 활동은 문제 글에 준 자료(대화·녹음을 옮긴 글, 조사 결과·사례, 관찰·실험 "
    "기록, 사전 뜻풀이, 검색 결과)를 읽고 하는 것으로 대신하고 결과는 글로 쓴다(그림·전개도는 "
    "말로 설명). 이렇게 대신한 것은 성취기준에 맞다고 본다(사용자 결정 2026-11-11). 그 행동의 생각 "
    "부분(요약·정리·분류·비교·판단·표현)은 학생이 답 안에서 직접 한다."
)

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
    "- 주인공은 솜뭉치 캐릭터 '뭉치'(모습은 정해져 있어 characters에 넣지 않는다). 뭉치는 물건을 "
    "잃은 당사자가 아니라 이 테마의 역할(예: 꼬마 탐정단·구조대·안전 순찰대·숲 탐험대)로 사건 "
    "현장에 해결하러 가는 해결사다. 이야기 속 "
    "등장인물(characters)은 "
    "뭉치를 뺀 1~3명, 흔한 이름의 또래나 동네 어른. 찾는 대상의 주인은 등장인물 중 한 명이다. "
    "실존 인물·상표 금지. look은 그림을 그릴 사람이 "
    "장면마다 같은 "
    "모습으로 그릴 수 있게 쓰는 겉모습(옷·머리·소지품).\n"
    "- outfit은 이 테마에서 뭉치가 입는 그 역할 차림. 실제 제복·휘장을 그대로 쓰지 않는다. "
    "styleNote는 이 "
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
    "- intro는 시작 이야기(200자 이내): 주인 인물이 대상을 잃은 사건, 테마 역할의 뭉치가 현장으로 "
    "출동해 큰 질문을 맡는 데까지. outro는 토요일 종료 이야기(300자 "
    "이내): 뭉치가 모은 단서로 정답을 밝히고 "
    "다섯 단서로 어떻게 정답만 남는지 짧게 정리한 뒤, 찾은 대상을 주인에게 돌려준다.\n"
    "- introCuts·outroCuts는 시작·종료 영상 콘티로 각각 정확히 4컷"
    "(무음 영상, 길이는 차례로 4·6·8·6초라 "
    "가장 긴 3번째 컷에 가장 큰 동작을 둔다). scene은 "
    "그 컷 끝에 보이는 장면(누가 어디서, 무엇이 보이는지), action은 그 컷의 동작 하나, caption은 "
    "영상 위에 띄울 짧은 문구(30자 이내, 학년에 맞는 말투). mungchiMood는 그 컷 끝 뭉치 표정으로 "
    "입 모양으로만 나타낸다: smile(웃는 입), surprised(작은 o 입), determined(다문 일자 입). "
    "뭉치가 나오지 않는 컷은 none.\n"
    "- introCuts 순서: 1 사건 장소의 평소 모습과 주인 인물(대상을 지니거나 쓰는 모습은 되지만 "
    "어디에 두는지는 보여 주지 않음, 뭉치 안 나옴), "
    "2 사건(주인이 대상이 사라진 걸 알아채고 당황함, 뭉치 안 나옴), "
    "3 뭉치 출동(테마 차림의 뭉치가 혼자 현장으로 달려감), "
    "4 현장 도착(뭉치와 인물들이 모여 큰 질문을 마주함). "
    "1·2컷의 mungchiMood는 none, 3·4컷은 none이 아니다. "
    "시작 콘티에는 정답 이름·정답 장소를 쓰지 않는다.\n"
    "- outroCuts 순서: 1 뭉치가 모은 단서를 정리함, 2 정답 장소로 감, "
    "3 정답 장소에서 대상을 찾아 주인에게 돌려줌, 4 함께 기뻐함.\n"
    "- 영상 속에는 글자를 넣지 않으므로 scene·action에 글자·숫자가 보이는 "
    "장면(쓰인 간판 등)을 쓰지 않는다.\n"
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
    "place·sceneNote·clue·discovery·missionHook에 쓰지 않는다.\n"
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
    "- 요일마다 clue 하나(학생이 그날 문제를 마친 뒤 한 줄 글로 그대로 보여 주므로 공백 포함 30자 "
    "안팎, 40자를 넘으면 안 됨). "
    "말한 사람은 붙이지 "
    "않는다. 단서는 그날 장면의 이야기 속 사실이다. 그날 문제 활동의 결과(계산값·학생 답)에서 "
    "만들지 않는다.\n"
    "- condition: 그 단서가 말하는 조건. kind는 RULE(후보를 뺌) 또는 HINT(빼지 않고 기울임), "
    "feature는 표의 특징 이름, "
    "allowed는 그 단서로 보아 가능한 값 목록(표에 있는 값만).\n"
    "- clue 문장은 그 condition만 말한다. allowed 값 낱말을 모두 그대로 쓰고(값이 둘이면 '모래나 "
    "나무'처럼 둘 다), 허용 밖 "
    "값 낱말은 쓰지 않는다. 그 특징에 대한 사실만 쓰고 표에 없는 새 사실을 더하지 않는다. 곁 "
    "물건의 종류·이름(예: 흙 포대, 화분, 책장)처럼 표에 "
    "없는 것을 특정하지 않고 특징 값으로만 말한다.\n"
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
    "- RULE: allowed 밖 값을 가진 후보가 빠진다(빠지는 후보 목록은 코드가 표로 계산하므로 쓰지 "
    "않는다). 정답의 값은 allowed 안. 찾지 못한 "
    '것("없었다")만으로 빼지 않고, '
    "그 값 때문에 왜 답이 될 수 없는지 다른 가능성이 남지 않게 쓴다(시간이면 앞뒤가 다 막히게, "
    "크기면 단단한 물건으로).\n"
    "- RULE은 그때까지 남은 후보를 적어도 하나 새로 뺀다(이미 빠진 후보만 빼는 단서는 HINT로 "
    "쓴다).\n"
    "- HINT: 아무 후보도 빼지 않는다. 그때까지 남은 후보는 모두 allowed 값을 가져야 한다. 남은 "
    "후보를 하나라도 빼는 내용이면 "
    "HINT가 아니라 RULE로 쓴다. 이미 빠진 후보는 allowed 밖이어도 된다(그래서 "
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
    "마지막으로 둔 때)와 맞는 때로 쓰고, 다섯 단서가 모두 "
    "같은 그때를 가리킨다. clue 문장이 사진·영상·"
    "녹음·기록·일지·메모를 말하면 kind는 RECORD, 누가 봤다고 하면 SIGHTING, 흔적이면 TRACE로 맞춘다"
    "(코드 검사 CLUE_EVIDENCE). 사진·기록에 찍힌 "
    "그때의 대상 모습은 써도 되지만 지금 있는 곳은 쓰지 "
    "않는다.\n"
    "\n"
    "증거 발견·수사 연결 — 단서는 학생이 그날 문제를 마친 뒤에 보여 준다\n"
    "- discovery: 그날 문제 앞 대화의 끝에서 두 번째 줄로 그대로 나가는 증거 발견 한 줄"
    "(공백 포함 40자 이내, 뭉치가 말함). 그날 evidence 종류에 맞는 증거"
    "(TRACE면 흔적이 남은 물건·자리, SIGHTING이면 "
    "본 사람, RECORD면 사진·기록)를 찾았다는 말만 한다. 단서 결론(allowed 값 낱말)·후보 "
    "이름·정답은 "
    '말하지 않는다. 예: "여기 축제 녹음기가 있어! 그때 소리가 담겼을지도 몰라."\n'
    "- missionHook: 증거 발견 줄 바로 다음, 문제 직전에 뭉치가 말하는 수사 연결 한 줄(공백 포함 "
    "40자 이내). 찾은 증거를 풀려면 그날 문제에서 배울 것이 필요하다는 이유만 말하고 도움을 "
    "청한다. 증거 자체를 살피라고 하지 않는다. 후보 이름·정답은 말하지 않는다. "
    '예: "녹음기 비밀을 풀려면 소리를 알아야 해. 도와줄래?"\n'
    "- 위 예시들은 특징·문장을 정하는 방향일 뿐이다. 예시 낱말·문장을 그대로 쓰지 말고 이 테마에 "
    "맞게 새로 정한다.\n"
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


FIX_SYSTEM = (
    "너는 초등학생용 주간 테마 글에서 검사에 걸린 칸 몇 개만 고쳐 쓰는 편집자다.\n"
    "- 받은 칸만 다시 쓴다. 다른 칸과 이야기 속 사실은 바꾸지 않는다.\n"
    "- 칸마다 적힌 검사 사유와 지킬 점을 고친다. 뜻은 그대로 두고 말을 줄이거나 바꾼다.\n"
    "- 글자 수는 공백·문장부호를 포함해 센다. 상한보다 3~5자 짧게 쓴다.\n"
    "- 출력: fixes에 받은 칸마다 {path, text} 하나씩. path는 받은 그대로 쓴다."
)


def fix_rules(theme: Theme, path: str) -> list[str]:
    """칸 종류별로 줄거리 프롬프트와 같은 지킬 점(검사를 다시 통과하도록)."""
    cands = theme.get("candidates") or []
    names = f"후보 이름({', '.join(cands)})은 쓰지 않는다."
    head, _, key = path.partition(".")
    if key in ("clue", "discovery", "missionHook"):
        day = theme_day(theme, head)
        cond = day.get("condition") or {}
        allowed = cond.get("allowed") or []
        if key == "clue":
            values = (feature_table(theme)[0].get(cond.get("feature") or "") or {}).values()
            others = sorted({v for v in values if v not in allowed})
            return [
                f"특징 '{cond.get('feature')}'의 값 낱말 {allowed}를 모두 그대로 쓴다.",
                f"허용 밖 값 낱말 {others}는 쓰지 않는다." if others else "",
                "말한 사람을 붙이지 않고, 새 사실을 더하지 않는다.",
                names,
            ]
        if key == "discovery":
            kind = (day.get("evidence") or {}).get("kind")
            return [
                f"뭉치가 그날 증거({kind})를 찾았다는 말만 한다.",
                f"단서 결론 낱말 {allowed}은 쓰지 않는다.",
                names,
            ]
        return [
            "찾은 증거를 풀려면 그날 배울 것이 필요하다는 이유만 말하고 도움을 청한다.",
            "증거 자체를 살피라고 하지 않는다.",
            names,
        ]
    if key == "caption":
        return ["영상 위에 띄우는 짧은 문구. 정답 이름·정답 장소를 쓰지 않는다."]
    return ["정답 이름은 종료 이야기(outro)에만 쓴다." if path != "outro" else ""]


def fix_user(theme: Theme, targets: dict[str, list[str]]) -> str:
    lines = [
        f"테마: {theme.get('title')} / 찾는 대상: {theme.get('target')}",
        "",
        "고칠 칸:",
    ]
    for path, reasons in targets.items():
        text = text_at(theme, path)
        lines += [
            f"- path: {path}",
            f"  지금 글({len(text)}자): {text}",
            f"  상한: 공백 포함 {text_max(path)}자",
            f"  검사 사유: {' / '.join(reasons)}",
            *[f"  지킬 점: {r}" for r in fix_rules(theme, path) if r],
        ]
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
    """미션 초안 프롬프트 뒤에 붙이는 테마 이야기 조각(생각 열기 개수·찾는 대상 포함, 정답은 주지
    않음).

    단서는 학생이 그날 미션을 마친 뒤 보여 주므로 그날 단서도 앞 요일 단서 목록도 넣지 않고(학생이
    아직 못 얻었을 수 있음), 그날 증거 발견 줄과 수사 연결 문장을 준다(사용자 결정 2026-11-11).
    """
    d = next(x for x in theme["days"] if x["day"] == day)
    names = ", ".join(c["name"] for c in theme["characters"])
    lines = [
        "",
        "테마 이야기 조각(이 미션은 주간 테마의 한 장면이다):",
        f"- 테마: {theme['title']} / {theme['world']}",
        f"- 등장인물: 뭉치(솜뭉치 모양의 주인공 캐릭터, 사건을 해결하러 온 해결사), {names}",
        f"- 오늘({DAY_KO[day]}요일) 장소: {d['place']}",
        f"- 오늘 장면: {d['sceneNote']}",
        f"- 오늘 찾은 증거(문제 앞 대화의 끝에서 두 번째 줄): {d['discovery']}",
        f"- 문제 바로 앞에 뭉치가 하는 말(수사 연결, 대화 마지막 줄): {d['missionHook']}",
        "테마 규칙:",
        "- 위 두 줄은 대화로 이미 나오므로 question에 다시 쓰지 않는다. "
        "question은 증거 자체(사진·흔적·"
        "기록의 내용)를 살피게 하지 않고, 문제 글에 준 자료로 성취기준의 행동을 학생이 직접 하게 "
        "한다.",
        "- 문제는 이 장소와 장면에서 뭉치와 등장인물이 겪는 일로 쓰고, 이 글만 읽고 풀 수 있게 "
        "한다. 관찰·비교할 내용"
        "(사진·그림 속 모습, 수, 생김새)은 question 글에 직접 쓴다. 그림에만 있는 정보로 풀게 "
        "하지 않는다.",
        "- 사진·녹음·그림·영상·지도·활동지를 보거나 듣게 하려면 그 내용을 question 글에 적는다. "
        "내용을 적지 않은 자료를 살피라고 하지 않는다.",
        "- " + TEXT_ONLY,
        "- 성취기준의 행동을 학생이 답 안에서 직접 하게 "
        "한다. '어떻게 쓸지·만들지·정리할지' 방법이나 "
        "계획을 묻지 않고, 글을 완성해 쓰기·분류한 결과 "
        "쓰기·정리한 내용 쓰기처럼 결과물을 쓰게 한다.",
        "- 다룰 글·작품·대화·메모·자료(감상할 시나 이야기, "
        "요약할 대화, 고칠 문장, 비교할 두 글 등)는 "
        "그 내용을 question 안에 짧게 직접 넣는다. 이름이나 개요만 주지 않는다.",
        "- question이 학생에게 요구하는 것은 요소 "
        "수(2~3가지)만큼만 둔다. 한 문장에 여러 조건(말·목소리·"
        "표정·손짓·까닭 등)을 늘어놓지 않는다.",
        "- 생각 유형 활동(돌아보기·따져 보기 등)은 "
        "성취기준 행동을 한 뒤에 덧붙인다. 성취기준 행동을 "
        "빼고 생각 유형 활동만 묻지 않는다.",
        "- 예시 답은 질문이 요구한 것을 순서대로 하나도 "
        "빠짐없이 답하는 완성된 결과물이다(계획·방법 "
        "설명이 아님). 까닭을 둘 이상 요구하면 서로 다른 까닭을 쓴다.",
        "- 질문이 어떤 글을 비교·점검·고쳐 쓰게 하면(예: 처음 쓴 글과 고친 글) 그 글 자체를 "
        "question 안에 짧게 넣는다. "
        "학생이 질문 글만 읽고 답할 수 있어야 한다.",
        "- 읽을 글·자료가 필요하면 question 안에 넣는다. guide에는 풀이 안내만 쓴다. 읽을 글에 "
        "나오는 낱말·문장은 "
        "forbiddenTerms에 넣지 않는다(학생이 그 글을 읽고 답함). forbiddenTerms에 수는 넣지 "
        "않는다(정답 수는 정답 키로 "
        "따로 검사함).",
        "- 큰 질문의 사건에 관한 새 사실(흔적·목격·기록 등)을 지어내지 않는다.",
        "- 풀이 문제의 최종 답은 계산해서 새로 구하는 "
        "값이다. 문제에 주어진 수 가운데 하나를 고르는 "
        "비교 문제로 만들지 않는다(정답 수가 문제 글에 보이면 유출 검사에 걸림).",
        f"- 찾는 대상: {theme.get('target') or ''}. 아직 찾지 못했으므로 문제에서 지금 보거나 "
        "만지거나 곁에 있는 것처럼 "
        "쓰지 않는다.",
        f"- 생각 열기 질문(hints)은 정확히 {HINTS[grade]}개. question 글에 나온 장소·물건·자료를 "
        "가리켜 생각을 열게 쓰되 정답·풀이는 주지 않는다. question 글에 없는 그림 속 모습·안내판"
        "을 떠올리게 하지 않는다(미션 그림은 question과 생각 열기 질문으로 그림).",
    ]
    lines += [
        "- 오늘 장면과 오늘 찾은 증거(장소·인물·물건·목격·기록)는 문제 소재로 쓸 수 있다. "
        "성취기준의 행동을 하게 하는 것이 먼저다.",
        "- 어느 후보가 답인지는 쓰거나 묻지 않는다. 문제를 사건 "
        "풀기(누구·어디·무엇 맞히기)로 만들지 않는다.",
        "- 이번 주 단서는 학생이 문제를 마친 뒤 화면이 따로 보여 준다. 증거가 무엇을 뜻하는지(단서 "
        "결론)를 문제·안내·생각 열기 질문·예시 답에 쓰지 않고, 문제의 답이 단서가 되게 만들지 "
        "않는다.",
    ]
    if DAY_TYPE[day] == "EVALUATE":
        lines += [
            "- 따져 보기는 자기 주장·근거와 함께 다른 관점(반대 의견·예외)에 답하는 것을 꼭 묻는다"
            "(선택 사항으로 두지 않는다).",
        ]
    if day == "FRI":
        lines += [
            "- 돌아보기·쓰기 점검 문제라면 점검하거나 비교할 글(예: 뭉치가 처음 쓴 메모와 고친 "
            "메모)을 question 안에 직접 "
            "넣는다. 예시 답은 질문이 묻는 것(처음 생각·바뀐 생각·까닭 등)을 하나도 빠짐없이 "
            "답한다.",
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
    "- 대화 끝 두 줄은 코드가 그대로 넣는다: 오늘 증거 발견 줄(discoverySpeaker가 말함), 그다음 "
    "뭉치의 수사 연결 한 줄. discoverySpeaker에 증거 발견 줄을 말할 "
    "사람을 고른다. 보통 뭉치이고, 등장인물이 말하는 편이 자연스러울 때만 그 등장인물. "
    "증거 발견 줄이 그 사람 이름을 부르면 다른 사람을 고른다.\n"
    "- lines: 오늘 상황을 짧게 말해 증거 발견 줄로 이어지게 한다. 끝 두 줄 내용을 lines에서 "
    "미리 말하지 않는다. 증거 발견 줄에 없는 새 사건 사실(흔적·목격·기록)을 "
    "더하지 않는다.\n"
    "- 장면 메모를 그대로 옮기지 말고, 인물이 그 자리에서 실제로 할 법한 짧은 말로 쓴다.\n"
    "- 단서는 학생이 오늘 문제를 마친 뒤 화면이 보여 준다. 증거가 무엇을 뜻하는지(단서 결론), "
    "어느 장소·사람을 가리키는지 말하지 않고, 앞 요일 단서도 요약하지 않는다(학생이 아직 못 얻었을 "
    "수 있음). 주어진 이름 말고 다른 "
    "장소·사람 이름을 새로 꺼내지 않는다.\n"
    "- lines 줄 수는 주어진 범위(끝 두 줄 제외, 0줄일 수 있음)를 지킨다. 한 줄에 한 가지만, "
    "25자 안팎(공백 포함 40자를 "
    "넘으면 안 됨).\n"
    "- text에는 말만 쓰고 앞에 '이름:'을 붙이지 않는다.\n"
    "- 오늘 문제의 값·풀이 방법·답(만들 물건 같은 답이 될 생각 포함), 예시 답 내용, 금지어는 쓰지 "
    "않는다.\n"
    '- 말하는 사람은 자기 이름을 3인칭으로 부르지 않는다("수아: 수아는…" 금지). 학년에 맞는 말투.\n'
)


def llm_line_range(grade: int) -> tuple[int, int]:
    """LLM이 쓸 lines 줄 수: 학년 범위(끝 두 줄 포함)에서 증거 발견 줄·수사 연결 2줄을 뺀 값."""
    lo, hi = DIALOGUE_LINES[grade]
    return max(lo - 2, 0), max(hi - 2, 0)


def dialogue_user(theme: Theme, day: str, draft: Draft, grade: int, feedback: list[str]) -> str:
    """그날 단서는 넣지 않는다(학생이 미션을 마친 뒤 보여 줌). 끝 두 줄이 될 증거 발견 줄과
    수사 연결 문장만 준다."""
    d = next(x for x in theme["days"] if x["day"] == day)
    lo, hi = llm_line_range(grade)
    count = f"{lo}줄" if lo == hi else f"{lo}~{hi}줄"
    lines = [
        f"학년: 초{grade}",
        f"학년에 맞는 말투: {grade_style(grade)}",
        f"lines 줄 수(끝 두 줄 제외): {count}",
        f"등장인물: 뭉치, {', '.join(c['name'] for c in theme['characters'])}",
        f"오늘({DAY_KO[day]}요일) 장소: {d['place']}",
        f"오늘 장면: {d['sceneNote']}",
        f"오늘 증거 발견 줄(코드가 끝에서 두 번째 줄로 그대로 넣음): {d['discovery']}",
        f"뭉치의 수사 연결(코드가 마지막 줄로 그대로 넣음): {d['missionHook']}",
        f"찾는 대상(대화에서 말하지 않고 나타나지 않음): {theme.get('target') or ''}",
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
    "값)이 다름, 이야기 속 사실끼리 모순, 찾는 대상이 종료 이야기 전에 나타나거나 말함"
    "(단, 시작 영상 "
    "1컷에서 주인이 사라지기 전의 대상을 지닌 모습은 허용), 아직 찾지 "
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
    "나타나거나 말하지 않는지(시작 영상 1컷의 사라지기 "
    "전 모습과, 사진·영상·기록에 찍힌 그때(지나간 "
    "때)의 대상 모습은 허용. 지금 있는 곳이 드러나면 결함). "
    "단서가 그날 장면의 이야기 속 사실인지(문제 활동의 결과가 아닌지).\n"
    "ANSWER_HINT: 종료 이야기(outro) 말고 학생이 보는 글(intro·장면·증거 발견 줄·수사 연결 "
    "문장·문제·안내·생각 열기 질문·예시 "
    "답·대화)이 정답을 직접 "
    "쓰거나 목요일 전에 정답을 확정하지 않는지. 월~수의 빈 rulesOut 단서가 정답 하나만 가리키지 "
    "않고 남은 다른 후보에도 "
    "맞는지. 단서는 학생이 그날 미션을 마친 뒤 보여 준다. 증거 발견 줄(discovery)·수사 연결 "
    "문장(missionHook)·대화·미션이 그날 단서 결론이나 정답을 미리 말하지 않는지. 수사 연결 문장이 "
    "그날 배울 개념·방법 이름(예: 분수 곱셈, 넓이 "
    "구하기)을 말하는 것은 설계상 허용이다(단서 결론·정답을 "
    "말할 때만 결함). 장면·대화가 그날 "
    "문제의 답(만들 물건·계산 "
    "결과 등)을 미리 알려 "
    "주지 않는지.\n"
    "GRADE_VOCAB: 그 학년이 읽고 풀 수 있는 낱말·분량인지, 그 학년에 배우지 않은 개념이 없는지.\n"
    "STANDARD_FIT: 각 문제가 주어진 성취기준의 행동을 학생이 직접 하게 하고 생각 유형과 맞는지. "
    "학생 혼자 글로 답하는 "
    "미션이므로 협력처럼 혼자 할 수 없는 부분은 보지 않고 핵심 "
    "행동(설명·구분·설계·계산·점검 등)을 본다. "
    + TEXT_ONLY
    + " 정답 키·예시 답이 문제와 맞는지(계산이면 값이 맞는지, 풀이는 finalAnswer).\n"
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
                "discovery": d["discovery"],
                "missionHook": d["missionHook"],
                "mission": {k: draft.get(k) for k in MISSION_FIELDS},
                "dialogue": dialogues.get(d["day"], []),  # 끝내 실패해 빠진 대화는 빈 줄로 검토
            }
        )
    summary = {
        k: theme[k]
        for k in ("title", "world", "intro", "outro", "bigQuestion", "candidates", "answer")
    }
    summary |= {
        "protagonist": "뭉치: 솜뭉치 모양의 주인공 캐릭터, 테마 역할로 사건을 해결하러 온 "
        "해결사(찾는 대상이 아님)",
        "characters": theme["characters"],
        "features": theme["features"],
        # 시작·종료 영상 콘티(문구는 학생이 영상 위에서 봄)
        "introCuts": theme.get("introCuts") or [],
        "outroCuts": theme.get("outroCuts") or [],
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
    "EXAMPLE_COMPLETE: 예시 답(서술·논술은 exampleAnswer, 고르기·순서·분류·풀이는 answerKey. "
    "풀이(SOLUTION_STEPS)는 미션 초안 형식상 exampleAnswer가 "
    "없어도 되고 answerKey.finalAnswer가 맞는지 "
    "본다)이 질문이 묻는 것을 "
    "하나도 빠짐없이 답하는지. 질문이 둘 이상을 물으면(예: 처음 생각·바뀐 생각·까닭) 모두 들어 "
    "있어야 한다. 계산이면 값이 "
    "맞는지.\n"
    "STANDARD_FIT: 질문이 주어진 성취기준의 핵심 행동을 학생이 직접 하게 하고 생각 유형과 맞는지. "
    "학생 혼자 글로 답하는 "
    "미션이므로 협력처럼 혼자 할 수 없는 부분은 보지 않는다. " + TEXT_ONLY + "\n"
    "MATERIAL: 답하는 데 필요한 것(읽을 글·비교할 글·수·관찰할 모습)이 질문 글 안에 다 있는지. "
    "그림에만 있는 정보나 주어지지 "
    "않은 글(예: '처음 쓴 글'을 비교하라는데 그 글이 없음)에 기대면 결함. 사진·녹음·그림·영상·"
    "지도·활동지를 보거나 듣게 하는데 그 내용이 질문 글에 없으면 결함. target이 주어지면, "
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


EXAMPLE_FIX_SYSTEM = (
    "너는 초등 미션의 예시 답만 고쳐 쓰는 출제자다. 질문·생각 열기 질문은 바꾸지 않는다.\n"
    "- 예시 답은 질문이 묻는 것을 하나도 빠짐없이, 질문에 나온 순서대로 답한다. 질문이 여러 "
    "가지를 물으면(예: 처음 생각·바뀐 생각·까닭, 쓰는 법·처리 방법) 각각 분명히 답한다.\n"
    "- 질문 글에 준 자료만 쓰고 새 사실을 지어내지 않는다. 질문이 쓰라고 한 재료·조건은 모두 "
    "쓴다.\n"
    "- 그 학년 학생이 쓸 만한 말과 길이로 쓴다.\n"
    "- 풀이 문제(inputType SOLUTION_STEPS)면 exampleAnswer에 구할 것·방법·계산·확인을 차례로 쓰고 "
    "finalAnswer에 최종 답(값과 단위)을 쓴다. 풀이가 아니면 finalAnswer는 null.\n"
    "- 검토 사유를 모두 고친다.\n"
    "- 예시 답은 계획·방법 설명이 아니라 질문이 요구한 결과물 자체다. 까닭을 둘 이상 요구하면 서로 "
    "다른 까닭을 쓴다. " + TEXT_ONLY
)


def example_fix_user(
    request: MissionDraftRequest, draft: Draft, grade: int, reasons: list[str]
) -> str:
    key = draft.answer_key
    body = {
        "grade": f"초{grade}",
        "thinkingType": THINKING_LABEL[request.thinking_type],
        "inputType": request.input_type,
        "standards": [{"code": s.code, "statement": s.statement} for s in request.standards],
        "question": draft.question,
        "hints": draft.hints,
        "exampleAnswer": draft.example_answer,
        "finalAnswer": key.final_answer if key else None,
        "reviewReasons": reasons,
    }
    return json.dumps(body, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 그림·영상·움직임 (#437 그림 단계, 사용자 결정 2026-11-11). 그림·영상 모델에 주는 고정 문구는
# 영어, 테마 글(인물 모습·장면 메모·미션 질문·콘티)은 한국어 그대로 넣는다.
# ---------------------------------------------------------------------------
IMAGE_STYLE = (
    "Style: 2D cartoon illustration for children, thick even dark-brown outlines, flat colors "
    "with simple soft shading, simple painted background, not 3D, 16:9."
)
MUNGCHI_LOOK = (
    "Mungchi (the main character): a cream-colored fluffy cotton-ball body with about 12 soft "
    "round bumps, the face low in the center of the body, small dot eyes with a tiny highlight "
    "(no eye whites), pink cheeks, small hands at the lower front on the left and right, short "
    "brown feet. Mungchi wears the theme outfit: {outfit}. Keep Mungchi exactly like the "
    "reference picture."
)
IMAGE_RULES = (
    "Rules: no thought bubbles or speech bubbles. No letters, words or numbers anywhere "
    "(signs, books and labels stay blank). Every face is clearly visible. Leave some empty "
    "space at the top of the picture."
)


def outfit_prompt(theme: Theme) -> str:
    """기본 뭉치 그림을 고쳐 테마 옷만 더하는 지시(모든 그림의 첫 참조가 됨)."""
    return (
        "Edit this picture. Keep the picture exactly as it is: Mungchi's body, face, eyes, "
        "cheeks, feet, hand positions, size, position, colors and the background stay "
        f"identical. Only add the theme outfit: {theme['outfit']}. Nothing in the hands. "
        f"{IMAGE_STYLE}"
    )


def _characters(theme: Theme) -> str:
    looks = "; ".join(f"{c['name']}: {c['look']}" for c in theme["characters"])
    return f"Other characters (draw them the same in every picture, Korean): {looks}"


def _fixes(feedback: list[str]) -> list[str]:
    if not feedback:
        return []
    return ["Fix these problems from the previous attempt:", *[f"- {x}" for x in feedback]]


# 콘티 mungchiMood → 입 모양(표정은 입으로만, 점 눈은 그대로). none·없음은 표정 문구를 넣지 않음
MOOD_MOUTH = {
    "smile": "a small smiling mouth",
    "surprised": "a small round o-shaped mouth",
    "determined": "a closed straight-line mouth",
}


def mood_mouth(cut: dict) -> str | None:
    return MOOD_MOUTH.get(cut.get("mungchiMood") or "none")


def _no_target(theme: Theme) -> str:
    return f"Do not draw {theme.get('target') or 'the missing target'} anywhere in this picture."


def mission_image_prompt(theme: Theme, day: str, draft: Draft, feedback: list[str]) -> str:
    """요일 미션 그림: 스타일·뭉치·인물·그날 장면 + 그날 증거 발견 줄 + 미션 질문·생각 열기 질문.

    증거 발견 줄(discovery)의 증거 물건은 살펴보기 단계에서 학생이 누를 수 있게 보이게 그린다.
    """
    d = next(x for x in theme["days"] if x["day"] == day)
    hints = " / ".join(h for h in draft.hints if h.strip())
    lines = [
        IMAGE_STYLE,
        MUNGCHI_LOOK.format(outfit=theme["outfit"]),
        _characters(theme),
        f"Scene (Korean): 장소 {d['place']}. {d['sceneNote']}",
        "Today's evidence (Korean). Draw the evidence object it mentions clearly visible: "
        f"{d['discovery']}"
        if d.get("discovery")
        else "",
        "Today's question for the student (Korean). Every object or place the question and the "
        f"thinking prompts point to must be visible in the picture: {draft.question}",
        f"Thinking prompts (Korean): {hints}" if hints else "",
        _no_target(theme),
        IMAGE_RULES,
        *_fixes(feedback),
    ]
    return "\n".join(x for x in lines if x)


def cut_shows_target(scene: str, index: int) -> bool:
    """찾는 대상이 나와도 되는 컷: 시작 1컷(주인이 지닌 모습)과 종료 3·4컷(발견·축하)."""
    return (scene, index) in (("INTRO", 1), ("OUTRO", 3), ("OUTRO", 4))


def cut_has_mungchi(scene: str, index: int) -> bool:
    """시작 1·2컷에는 뭉치가 나오지 않는다(뭉치 참조도 넣지 않음)."""
    return not (scene == "INTRO" and index in (1, 2))


def cut_has_characters(scene: str, index: int) -> bool:
    """시작 3컷은 뭉치 혼자 출동(인물 참조를 넣지 않음)."""
    return not (scene == "INTRO" and index == 3)


def cut_image_prompt(theme: Theme, scene: str, index: int, cut: dict, feedback: list[str]) -> str:
    """시작·종료 영상 컷의 첫 그림(영상이 이 그림에서 시작). mungchiMood는 있으면 쓴다."""
    lines = [IMAGE_STYLE]
    if cut_has_mungchi(scene, index):
        lines.append(MUNGCHI_LOOK.format(outfit=theme["outfit"]))
        if mouth := mood_mouth(cut):
            lines.append(f"Mungchi's expression: {mouth}, dot eyes unchanged.")
    else:
        lines.append("Mungchi does not appear in this picture.")
    if cut_has_characters(scene, index):
        lines.append(_characters(theme))
    else:
        lines.append("Only Mungchi is in this picture (no other characters).")
    lines.append(f"Scene (Korean): {cut['scene']}")
    if cut_shows_target(scene, index):
        lines.append(f"{theme.get('target') or 'The missing target'} may appear as the scene says.")
    else:
        lines.append(_no_target(theme))
    lines += [IMAGE_RULES, *_fixes(feedback)]
    return "\n".join(lines)


IMAGE_REVIEW_SYSTEM = (
    "너는 초등학생 학습 서비스의 그림 검토자다. 첫 그림이 검토할 그림이고, 두 번째 그림은 "
    "주인공 뭉치의 기준 모습(테마 옷)이다. 주어진 항목(items)마다 verdict를 PASS(문제 없음)·"
    "WARN(애매해서 사람이 볼 것)·FAIL(분명한 결함, 다시 그려야 함) 중 하나로 쓰고 근거 한 "
    "문장(reason)을 쓴다. 주어진 항목을 모두 한 번씩 쓴다. 분명한 결함만 FAIL로 한다.\n"
    "MUNGCHI: 뭉치가 나와야 하는 그림이면 기준 모습과 같은지(크림색 몽글몽글한 몸, 몸 아래쪽 "
    "가운데 얼굴, 흰자 없는 점 눈, 분홍 볼, 작은 손, 갈색 짧은 발, 테마 옷). 뭉치가 나오지 "
    "않아야 하는 그림이면 나오지 않는지.\n"
    "ANSWER_HINT: 찾는 대상이 나오면 안 되는 그림(targetAllowed false)에 찾는 대상이 보이는지, "
    "정답 장소가 드러나는지(생각 풍선·화살표 등으로 대상이 있는 곳을 보여 주는지).\n"
    "TEXT: 글자·숫자 같은 글이 보이는지(간판·책·표지에 쓴 글 포함).\n"
    "SAFETY: 무섭거나 위험한 모습, 폭력, 실존 인물·상표가 있는지.\n"
    "SCENE_FIT: 주어진 장면(장소·인물·하는 일)과 그림이 맞는지.\n"
    "MISSION_FIT(items에 있을 때만): 미션 질문과 생각 열기 질문이 가리키는 물건·장소, 그날 증거 "
    "발견 줄(discovery)이 말하는 증거 물건이 그림에 다 보이는지.\n"
)


def image_review_user(
    theme: Theme,
    scene_text: str,
    *,
    ids: tuple[str, ...],
    has_mungchi: bool,
    shows_target: bool,
    question: str | None = None,
    hints: list[str] | None = None,
    discovery: str | None = None,
) -> str:
    body: dict = {
        "items": list(ids),
        "scene": scene_text,
        "mungchi": "나와야 함" if has_mungchi else "나오지 않아야 함",
        "characters": theme["characters"],
        "target": theme.get("target") or "",
        "targetAllowed": shows_target,
        "answerPlace": theme.get("answer") or "",
    }
    if question is not None:
        body |= {"missionQuestion": question, "hints": hints or [], "discovery": discovery or ""}
    return json.dumps(body, ensure_ascii=False)


VIDEO_NEGATIVE = (
    "big eyes, eye whites, changing eye shape, body morphing, extra limbs, 3D render, text, "
    "flashing lights, scary, sudden cuts"
)


def video_prompt(theme: Theme, cut: dict, feedback: list[str]) -> str:
    """컷 동작 + 고정 문구(첫 그림만 고정해 그 그림에서 시작)."""
    mouth = mood_mouth(cut)
    lines = [
        f"Action (Korean): {cut['action']}",
        "Keep the 2D cartoon style of the first frame with thick even outlines.",
        "Keep Mungchi's round fluffy shape and small dot eyes unchanged (no eye whites).",
        f"Mungchi's expression: {mouth}." if mouth else "",
        "Natural, simple movement. Only one camera move. No text.",
        f"Do not show where {theme.get('target') or 'the missing target'} is put or hidden.",
        *_fixes(feedback),
    ]
    return "\n".join(x for x in lines if x)


VIDEO_REVIEW_SYSTEM = (
    "너는 초등학생 학습 서비스의 영상 검토자다. 주어진 그림들은 영상 컷 하나에서 2초마다 뽑은 "
    "장면이다. 네 항목마다 verdict를 PASS·WARN·FAIL 중 하나로 쓰고 근거 한 문장(reason)을 쓴다. "
    "네 항목을 모두 한 번씩 쓴다. 분명한 결함만 FAIL로 한다.\n"
    "MORPH: 인물·뭉치의 몸·얼굴·눈 모양이 장면 사이에 녹아내리듯 바뀌거나 팔다리가 늘어나는지, "
    "2D 그림체가 3D로 바뀌는지.\n"
    "ANSWER_HINT: 찾는 대상이 나오면 안 되는 컷(targetAllowed false)에 보이거나 정답 장소가 "
    "드러나는지.\n"
    "TEXT: 글자·숫자가 보이는지.\n"
    "SAFETY: 무섭거나 위험한 모습, 번쩍이는 빛, 폭력이 있는지.\n"
)


def video_review_user(theme: Theme, cut: dict, shows_target: bool) -> str:
    return json.dumps(
        {
            "scene": cut["scene"],
            "action": cut["action"],
            "target": theme.get("target") or "",
            "targetAllowed": shows_target,
            "answerPlace": theme.get("answer") or "",
        },
        ensure_ascii=False,
    )


MOTION_SYSTEM = (
    "너는 초등학생 학습 서비스의 장면 연출을 정한다. 주어진 그림 한 장에 웹이 입힐 움직임 값을 "
    "정한다. 좌표 x·y는 그림 너비·높이에 대한 %(왼쪽 위 0, 오른쪽 아래 100).\n"
    "- transition: 장면이 바뀌는 방식(none·fade·slide-left·slide-right·zoom), transitionSeconds "
    "0.3~1.2.\n"
    "- cameraFrom·cameraTo: 천천히 움직이는 카메라의 시작·끝 중심과 확대(zoom 1.0~1.4), "
    "cameraSeconds 8~20. 장면의 중심 인물이나 물건 쪽으로 부드럽게.\n"
    "- speakers: 주어진 화자 이름(speakers)마다 그림 속 그 인물 얼굴의 중심 x·y. 주어진 이름만 "
    "쓰고, 화자가 없으면 빈 목록. 뭉치는 크림색 솜뭉치 모양의 주인공이다.\n"
    "- effects: 장면 분위기에 맞는 가벼운 효과(눈·꽃잎·잎·물방울 등) 0~2층. color는 #RRGGBB, "
    "count 1~20, size 1~6(그림 너비 %), direction 0~359도(0은 아래로 떨어짐), speed 2~20, "
    "opacity 0.2~0.8. 효과가 어울리지 않으면 빈 목록. 번쩍이거나 무서운 효과는 쓰지 않는다.\n"
    "- spots: dayInfo가 있는 요일 장면만, 문제 전에 학생이 그림에서 눌러 볼 물건 2~3개. 정확히 "
    "하나는 그날 찾은 증거(discovery가 말하는 물건, evidence true), 나머지는 미션 질문·생각 열기 "
    "질문에 나온 물건(evidence false). 그림에 실제로 보이는 물건만 고르고 x·y는 그 물건의 중심. "
    "label은 물건 이름(10자 이내), line은 눌렀을 때 뭉치가 하는 짧은 말(30자 이내, 증거 물건은 "
    "찾았다는 말, 다른 물건은 미션을 떠올리게 하는 말). line에 증거가 무엇을 뜻하는지(단서 결론)·"
    "후보 이름·정답은 쓰지 않는다. dayInfo가 없으면(시작·종료) 빈 목록.\n"
)


def motion_user(
    theme: Theme,
    scene: str,
    scene_text: str,
    speakers: list[str],
    day_info: dict | None = None,
) -> str:
    """day_info: 요일 장면의 살펴보기 재료 {discovery, missionQuestion, hints}(단서는 넣지 않음)."""
    body: dict = {
        "scene": scene,
        "sceneText": scene_text,
        "styleNote": theme.get("styleNote") or "",
        "speakers": speakers,
    }
    if day_info:
        body["dayInfo"] = day_info
    return json.dumps(body, ensure_ascii=False)
