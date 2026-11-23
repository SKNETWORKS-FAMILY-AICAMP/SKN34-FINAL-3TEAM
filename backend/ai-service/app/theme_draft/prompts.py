"""주간 테마 초안 프롬프트 (theme-draft@2, #437·#535·#647).

줄거리·미션 이야기 조각·대화·글 검토·미션 검토 묶음.
문구를 바꾸면 PROMPT_VERSION을 올림 (NFR-DAT-02). 문구는 텍스트 시험(2026-11-10, 처음 보는
주제 초3·초4·초5·초6 통과)에서 검증한 것이다. 해결사 뭉치·시작 콘티 순서·증거 발견 줄·수사 연결
문장·단서 미션 뒤 공개(사용자 결정 2026-11-11)는 배포 전이라 같은 버전에서 고쳤고 실제 LLM
실측은 아직이다. LLM 입력에 학생 정보·학생 답은 넣지 않는다.
theme-draft@2(#535·#647): 증거 종류·기록 매체 배정, 미션 소재(STORY_LINK), 영상 검토(뭉치가 사건
대상을 잡거나 건넴, 차림 소품 쥠은 허용, 영상 생성도 같은 기준), 학생에게 보이는 특징 표
낱말(#647)로 문구가 바뀌어 버전을 올림(@2 배포 전이라 한 번만).
@1을 활성으로 지정한 환경은 배포 때 활성 항목을 바꾸거나 지움(ai.md 7장·17.6).
theme-draft@3(#634): 줄거리 종류(잃어버린 것·보물 쪽지·동물 장난꾸러기·발자국 주인). 공통 규칙은
PLAN_SYSTEM에 두고 종류 규칙 묶음(families.type_rules)을 plan_user가 붙인다. @2가 develop에서 배포될
수 있어 새 버전(NFR-DAT-02, 설계 ai.md 17.8). ②·④(손에 든 것·때·길·방법)도 @3이 배포 전이라 같은
버전에서 더함.
"""

import json
from typing import Any

from app.followup.prompts import grade_style
from app.mission_draft.models import Draft, MissionDraftRequest
from app.mission_draft.prompts import THINKING_LABEL
from app.theme_draft.checks import (
    ASK,
    CANDIDATES,
    CLUE_TYPES,
    DAY_KO,
    DAY_TYPE,
    DIALOGUE_LINES,
    EVIDENCE_KO,
    EXAMPLE_LONG_TYPES,
    EXAMPLE_SENTENCES,
    GRAPH_STANDARDS,
    HINTS,
    INVESTIGATE,
    MATH_AHEAD,
    Theme,
    candidate_words,
    clue_person,
    clue_says,
    day_frames,
    day_use,
    evidence_plan,
    feature_table,
    first_line_text,
    first_speaker,
    flat_features,
    frame_of,
    future_events,
    helper_use_day,
    is_story,
    material_numbers,
    mission_way,
    mission_way_plan,
    plan_for_type,
    plan_slot,
    promise_meaning,
    promise_sense,
    secret_values,
    target_words,
    testimony_day,
    text_at,
    text_max,
    theme_day,
)
from app.theme_draft.families import (
    ALL_CUTS,
    ANIMAL_NO_WINTER,
    SOUND_NO_WINTER,
    SOUNDS,
    STORY_BRANCHES,
    STORY_TYPES,
    StoryType,
    TopicFields,
    branch_option,
    branch_outro,
    branch_rule,
    habitat_animals,
    kept_target,
    parse_topic,
    parse_topic_fields,
    place_sounds,
    season_of,
    story_type,
    theme_branch,
    type_rules,
    valid_branch,
)
from app.theme_draft.models import ThemeDraftRequest

PROMPT_VERSION = "theme-draft@3"
# 글로 대신하는 활동 원칙(사용자 결정 2026-11-11). 미션 생성·미션 검토·글 검토·예시 답 고쳐
# 쓰기에 같은 글을 넣어 기준이 어긋나지 않게 함. #782(사용자 결정 2026-11-19): 대신한 활동을 그
# 이름으로 시키지 않는다('발표 글을 써 봐'·'그리는 순서를 글로'·'끊어 읽을 곳 표시'). 11-11의
# 괄호(그림은 말로 설명, 소리 내어 읽기는 끊어 읽기 표시로)를 생각 부분으로 바꿈. 코드 검사 ACT_NAME
TEXT_ONLY = (
    "학생은 글로만 답한다. 듣기·말하기·발표·조사·관찰·실험·그리기·만들기·사전 찾기·검색처럼 "
    "글로 직접 할 수 없는 활동은 문제 글에 준 자료(대화·녹음을 옮긴 글, 조사 결과·사례, 관찰·실험 "
    "기록, 사전 뜻풀이, 검색 결과)를 읽고 하는 것으로 대신하고 결과는 글로 쓴다. 이렇게 대신한 "
    "것은 성취기준에 맞다고 본다(사용자 결정 2026-11-11). 그 행동의 생각 "
    "부분(요약·정리·분류·비교·판단·표현·계산·해석)은 학생이 답 안에서 직접 한다. 대신한 활동은 "
    "그 이름으로 시키지 않는다: '발표 글·발표 자료를 써', '같이 발표해 볼래?', '목소리·몸짓을 "
    "괄호에 넣어 써', '그리는 순서·과정을 글로 써', '컴퍼스로 그려', '그래프로 나타내', '그림을 "
    "살펴', '끊어 "
    "읽을 곳을 표시해', '검색해 봐', '토의 글을 써'처럼 쓰지 않고 그 생각 부분만 이야기 안의 "
    "목적으로 시킨다(예: '본 모습을 두 문장으로 정리해 ○○에게 알려 줘', '반지름이 몇 cm여야 "
    "하는지 구하고 까닭을 써', '눈금 한 칸을 얼마로 할지 정하고 가장 많은 날을 찾아 써', '이 글을 "
    "어떤 마음으로 읽으면 좋을지 글 속 낱말을 근거로 써')."
)
# 수사 연결 문장의 <활동> 자리(#782 사용자 결정 2026-11-19). 그날 성취기준 이름을 그대로 넣어 '같이
# 발표 글 써 볼래?'가 나왔음(지금 커밋 실측 미션 180개 중 8개). 줄거리·칸 고쳐 쓰기·미션 뒤 고쳐
# 쓰기에 같은 글
HOOK_ACT_RULE = (
    "<활동>은 학생이 글로 하는 생각 활동(정리·요약·비교·판단·계산 등)으로 쓰고 발표·토의·그리기·"
    "소리 내어 읽기·검색처럼 글로 할 수 없는 활동 이름은 쓰지 않는다(코드 검사 ACT_NAME, 예: '같이 "
    "발표 글 써 볼래?' 대신 '같이 정리해 볼래?')."
)
# 예시 답이 질문 요구를 채우는 법. 미션 생성(story_text)과 예시 답 고쳐 쓰기(EXAMPLE_FIX_SYSTEM)에
# 같은 글을 넣음. 실측 2026-11-15 닫기 2차 미션 검토 EXAMPLE_COMPLETE 15번 중 같은 뜻 까닭 4·
# 표정·몸짓 빠짐 2·문장 수 어김 1·설명과 실제 글 어긋남 3(그중 고쳐 써도 같은 사유로 다시 실패 8),
# 닫기 3차 2번째 실측 11번 중 새 글·요약을 방법·주제만 씀 4·풀이 확인이 계산 되풀이 1
EXAMPLE_RULES = (
    "질문이 정한 개수·형식(한 문장, 두 가지 등)을 그대로 지킨다. 까닭을 둘 이상 요구하면 서로 다른 "
    "쪽에서 찾은 까닭을 쓴다(같은 뜻을 말만 바꾼 것은 서로 다른 까닭이 아님. 예: 읽는 사람에게 "
    "좋은 점과 쓰는 사람에게 좋은 점). 질문이 말한 조건(표정·몸짓·목소리, 처음과 나중, 누구의 "
    "생각과 같은지 등)은 하나씩 그 낱말이 드러나게 쓴다. 질문이 둘 이상을 각각 물으면(햇살과 "
    "나무, 단어와 띄어쓰기 등) 하나씩 따로 답한다. 문장 수를 정하면 인사말까지 세어 그 수로 "
    "쓴다. 비교·판단하라고 하면 결과와 함께 어떻게 비교했는지도 쓴다. 새 글·안내·요약·발표 "
    "자료·전할 말을 쓰라고 하면 그 글의 실제 내용을 끝까지 쓴다(제목·주제·만드는 방법만 쓰지 "
    "않음). 풀이의 확인은 계산을 되풀이하지 않고 거꾸로 계산하기 등 다른 방법으로 맞는지 "
    "확인한다. 예시 답 안의 "
    "설명은 예시 답에 실제로 쓴 글·질문에 나온 사실과 맞게 쓰고, 질문에 없는 행동을 지어내 "
    "까닭으로 쓰지 않는다."
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
    "잃은 당사자가 아니라 주제에 맞는 이 테마의 역할로 사건 "
    "현장에 해결하러 가는 해결사다. 이야기 속 "
    "등장인물(characters)은 "
    "뭉치를 뺀 1~3명. 이름은 주어진 이름 목록에서만 "
    "고르고(어른은 이름 대신 '떡집 사장님'·'등대지기 "
    "할아버지'처럼 하는 일·관계로 불러도 됨), 같은 반 친구만으로 채우지 말고 장면에 맞게 가족·이웃 "
    "어른·가게 주인·선생님 등을 섞는다. 사건의 중심 아이(학생 또래)는 줄거리 종류 규칙대로 "
    "등장인물 중 한 명이다. "
    "실존 인물·상표 금지. look은 그림을 그릴 사람이 "
    "장면마다 같은 "
    "모습으로 그릴 수 있게 쓰는 겉모습(옷·머리·소지품).\n"
    "- outfit은 이 테마에서 뭉치가 입는 역할 차림이다. "
    "그 역할을 한눈에 알아보게 머리에 쓰거나 몸·목에 "
    "거는 것 1~2개를 꼭 넣는다. 손에 드는 "
    "물건은 넣지 않는다. 경찰관·소방관 같은 제복 모양은 되지만 실제 기관 휘장·글자는 쓰지 "
    "않는다. "
    "styleNote는 이 "
    "테마 그림의 색·분위기 메모.\n"
    "- 주제가 '줄거리: … / 뭉치 역할: … / 장소: … / 찾는 대상(또는 밝힐 것·손에 든 것): …' "
    "형식이면 "
    "넷을 그대로 따른다: 줄거리 종류는 storyType과 아래 줄거리 종류 규칙으로, 뭉치 역할과 괄호 속 "
    "차림은 outfit에, 장소는 사건이 일어나는 곳(장면·후보는 그 장소 안이나 둘레)으로, 넷째 칸 "
    "글은 target으로(글 그대로). 주제가 그냥 글이면 그 주제에 맞게 고른다.\n"
    "- storyType은 줄거리 종류 코드(아래 줄거리 종류 규칙). 동물 주인공 종류(PRANK·FOOTPRINT)는 "
    "incident·answerLook을, 소리 탐정(SOUND)은 answerLook을 반드시 채운다(비우면 코드 검사 "
    "REQUIRED). 그 밖은 null.\n"
    "- 학생이 집·학교·마을에서 직접 보는 사물과 일만. 범죄·폭력·위험·무서운 일 금지. 사람이 "
    "동물 먹이(사료·동물 간식)를 먹거나 동물에게 사람 음식을 먹이는 장면도 쓰지 않는다. 시각은 "
    "오전·오후를 붙인 12시간제로 쓰고 이야기에 맞는 때를 고른다.\n"
    "- days는 MON~FRI 다섯 장면이고 thinkingType은 주어진 요일 배치 그대로. place는 그날 장소(20자 "
    "이내), 다음 날 장소는 "
    "걸어서 이어지는 가까운 곳. sceneNote는 그 장면 메모(150자 이내): 누가 어디서 무엇을 하고 "
    "무엇이 보이는지. 그날 문제의 "
    "성취기준 활동이 자연스럽게 나올 거리(물건·불편한 일·상황)를 넣되, 그날 문제의 답(만들 "
    "물건·계산 결과·고를 답·바뀐 "
    "생각)은 쓰지 않는다(학생이 생각할 몫). 그날 단서 결론(그날 단서 특징의 값, 예: 증거가 남은 "
    "바닥이 젖었는지)도 쓰지 않는다(단서는 문제 뒤에 보여 줌). 뭉치가 지나는 길에 탁자 같은 "
    "물체를 두지 않고, 소품은 "
    "쓰임새대로 쓴다. 그림에는 글자·숫자를 그리지 않으므로 쓰인 내용·정확한 개수처럼 글로만 보이는 "
    "것과 생각·떠올리기처럼 그릴 수 없는 행동은 sceneNote에 "
    "쓰지 않는다(그런 내용은 문제 글이 준다).\n"
    "- intro는 시작 이야기(200자 이내, 시작 상황은 줄거리 종류 규칙). outro는 토요일 종료 이야기의 "
    "마무리 장면(160자 이내, 줄거리 종류 규칙의 결말 장면만). "
    "다섯 단서로 어떻게 정답만 남는지의 정리는 코드가 특징 표로 계산해 앞에 붙이므로 "
    "쓰지 않는다(요일 이름·빠진 "
    "후보를 쓰지 않음).\n"
    "- intro·outro·콘티의 때와 상황은 단서 evidence.when이 가리키는 그때와 맞춘다(증거가 '준비를 "
    "마친 때'면 이야기에서도 그때 준비가 끝나 있음).\n"
    "- introCuts·outroCuts는 시작·종료 영상 콘티로 각각 정확히 4컷"
    "(무음 영상, 길이는 차례로 4·6·8·6초라 "
    "가장 긴 3번째 컷에 가장 큰 동작을 둔다). scene은 "
    "그 컷 끝에 보이는 장면(누가 어디서, 무엇이 보이는지), action은 그 컷의 동작 하나, caption은 "
    "영상 위에 띄울 짧은 문구(30자 이내, 학년에 맞는 말투). mungchiMood는 그 컷 끝 뭉치 표정으로 "
    "입 모양으로만 나타낸다: smile(웃는 입), surprised(작은 o 입), determined(다문 일자 입). "
    "뭉치가 나오지 않는 컷은 none.\n"
    "- introCuts·outroCuts 순서는 줄거리 종류 규칙의 콘티 틀을 따른다. 시작 1·2컷에는 뭉치가 "
    "나오지 않고 3(뭉치 출동)·4(현장 도착)에는 나온다: 1·2컷의 mungchiMood는 none, 3·4컷은 "
    "none이 아니다. "
    "시작 콘티에는 정답 이름·정답 장소를 쓰지 않는다. 종료 4컷에는 모두 뭉치가 나온다"
    "(mungchiMood는 none이 아님). 종료 콘티는 정답 공개 뒤라 정답 이름·정답 장소를 써도 된다"
    "(단, 대상·후보가 그림에 나오지 않는 컷은 줄거리 종류 규칙대로 그 이름을 쓰지 않음).\n"
    # #765: 컷 scene은 그 컷 그림 지시·그림 검토에 그대로 들어감(그림에 없는 것을 쓰면 검토가 실패)
    "- scene·action에는 그 컷 그림에 보이는 것만 쓴다. 그림에 나오지 않는 것을 '○○는 보이지 "
    "않는다'처럼 쓰지 않는다.\n"
    "- action은 그 자리에서 하는 작은 동작 하나. 뭉치는 팔이 없어(아래쪽 작은 손만) 뭉치의 동작은 "
    "제자리에서 작게 통통 튀기·고개 갸웃·몸 살짝 흔들기·표정 바꾸기만 쓴다. 손 흔들기·손 들기·"
    "가리키기·짚기·건네기·안기·모으기·놓기·뛰기처럼 손이나 팔다리를 쓰는 동작은 사람만 한다"
    "(예: '사람들이 손뼉을 치고 뭉치는 제자리에서 통통 튄다'). 인물·뭉치가 화면 쪽으로 다가오거나 "
    "멀어지지 않고, 걸어서 화면 밖으로 나가거나 새 인물이 들어오지 않는다. 컷 끝까지 scene에 나온 "
    "인물이 모두 화면 안에 있다.\n"
    "- 영상 속에는 글자를 넣지 않으므로 scene·action에 글자·숫자가 보이는 "
    "장면(쓰인 간판 등)을 쓰지 않는다.\n"
    "\n"
    "큰 질문·후보·정답\n"
    "- bigQuestion은 답이 후보 하나로 정해지는 지나간 일 질문(40자 이내). 무엇을 묻고 후보가 "
    "무엇인지(장소·동물)는 줄거리 종류 규칙을 따른다. 누가 "
    "가져갔는지처럼 사람을 탓하는 질문은 쓰지 않는다. "
    '"지금 어디에 있을까"처럼 현재를 묻지 않는다(지난 '
    "흔적·목격으로는 지금 위치를 "
    "증명할 수 없음). 장소는 학교만이 아니라 주제에 맞게 시장·공원·바닷가·숲·박물관·농장·캠핑장·"
    "동네 골목 등으로 고른다. candidates는 주어진 "
    "개수, 각 2~10자 명사로 구체적으로 짓는다(같은 범주끼리). 후보 이름에 색 "
    "낱말(빨간·파란·노란·초록 등)을 "
    "쓰지 않는다. answer는 후보 중 하나.\n"
    "- 정답 이름은 outro와 outroCuts에만 쓴다. "
    "title·world·intro·bigQuestion·styleNote·outfit과 days의 "
    "place·sceneNote·clue·discovery·missionHook, introCuts에 쓰지 않는다.\n"
    "\n"
    "특징 표(features) — 정답 논리는 이 표로 코드가 확인한다\n"
    "- 후보를 가려낼 특징 2~5개. 특징마다 name과 values(후보마다 값 하나, [{candidate, value}]). "
    "값은 짧은 낱말이고, "
    "같은 특징 안에서 같은 값은 같은 낱말로 쓴다. 특징 이름과 값은 학생이 그날 단서를 얻은 "
    "뒤 단서 근거로 그대로 보므로(#647) 그 학년이 읽는 쉬운 우리말로 쓴다(예: 이름 '바닥 재질', "
    "값 '나무').\n"
    "- 같은 특징의 서로 다른 값은 뜻이 겹치지 않아 값만 보고 바로 가를 수 있어야 한다. 비슷한 "
    "말(환한·밝은), 한쪽이 다른 쪽을 포함하는 말(정사각형은 직사각형이기도 함), 후보 이름과 "
    "어긋나는 값(이름이 '○○ 옆'인데 거리가 '멀리')을 쓰지 않는다.\n"
    "- 특징은 되도록 그 주 요일별 성취기준 내용에서 고른다(예: 사는 곳·환경을 배우면 주변 바닥이나 "
    "물기, 길이·거리를 "
    "계산하면 거리, 무게를 비교하면 무게). 어울리는 것이 없으면 장면에서 고른다.\n"
    "- 값은 그 장소·물건에 실제로 그럴 법해야 한다. 값에 등장인물 이름을 쓰지 않는다(목격 증거 "
    "발견 줄이 본 사람을 말하므로 그 이름이 단서 결론이 되어 버림).\n"
    "- standardCode: 그 특징을 그날 성취기준 내용에서 골랐으면 그 성취기준 코드, 장면에서 골랐으면 "
    "null. 성취기준에서 고르더라도 그때 본 사람이 보고 알 수 있는 후보의 실제 성질(크기·모양·거리 "
    "등)만 고른다(말투·표현 방법 같은 배울 내용 자체는 특징이 아님 — 실측 '안내 말투 방언'이 "
    "'새봄이 방언으로 안내했다' 단서가 됨).\n"
    "\n"
    "단서\n"
    "- 요일마다 clue 하나(학생이 그날 문제를 마친 뒤 한 줄 글로 그대로 보여 주므로 공백 포함 32자 "
    "이내로 짧게, 40자를 넘으면 안 됨. 기록 매체 낱말도 이 안에 넣는다. TRACE 날은 누구의 흔적인지 "
    "찾는 대상 낱말을 꼭 넣고 38자 안팎, 46자를 넘으면 안 됨). "
    "'○○가 말했다'처럼 말한 사람 이름을 붙이지 "
    "않는다(부탁 날은 돕는 사람이 자기 말로 알려 주듯 쓰되 이름은 붙이지 않음). 단서는 그날 "
    "장면의 이야기 속 사실이다. 그날 문제 활동의 결과(계산값·학생 답)에서 "
    "만들지 않는다.\n"
    "- condition: 그 단서가 말하는 조건. kind는 RULE(후보를 뺌), HINT(빼지 않고 새 특징 값을 "
    "알려 줌), STORY(사건 단서, 아래) 중 하나, "
    "feature는 표의 특징 이름, "
    "allowed는 그 단서로 보아 가능한 값 목록(표에 있는 값만). allowed가 그 특징 값 전부가 되면 "
    "아무것도 알려 주지 않는 단서다('마른 땅이나 젖은 땅'). HINT는 그때 남은 후보 값만 allowed에 "
    "넣고, 그것이 곧 그 특징 값 전부면 이미 빠진 후보와 값이 갈리는 다른 특징을 고른다(코드 검사 "
    "CLUE_EMPTY).\n"
    # #782 설계 v3(사용자 결정 2026-11-21): 직접 본 사람은 하나만 봤으므로 'A나 B'로 말하지 않음
    # (전에는 '모래나 나무처럼 나로 이어'라고 시켜 2차 측정 통과 31개에 14건)
    "- clue 문장은 그 condition만 말한다. 특징이 무엇에 대한 것인지(바닥·바람·빛처럼) 밝혀 쓴다. "
    # #782 설계 v9: 6차 글 검토 CLUE_LOGIC 2건('발자국 발 수'에 '두 발을 봤어', '집 앞 길 모양'에
    # '길'만). 코드로 보면 213일 중 107일이 걸려 지시문으로만
    "특징 이름에 붙은 대상·자리 말(예: '발자국 발 수'면 발자국, '집 앞 길 모양'이면 집 앞 길)을 "
    "단서에 넣는다. "
    "allowed가 값 하나면 그 값 낱말을 그대로 쓴다(예: '바닥은 흙이었어!'). allowed가 둘 이상이면 "
    "늘어놓지 않고 빠지는 값(그 특징 값 중 allowed 밖, 한두 개)을 부정으로 쓴다(예: 바닥 값이 "
    "모래·돌·잔디·나무이고 allowed가 모래·돌·잔디면 '끈이 스친 바닥은 나무는 아니었어!' — allowed "
    "값 낱말은 쓰지 않음, 'A나 B'로 쓰면 코드 검사 CLUE_TEXT). 그래서 condition은 값 하나이거나 "
    "빠지는 값이 한두 개인 꼴로만 정한다(코드 검사 CONDITION). 어느 꼴이든 '모두·전부·둘 "
    "다'처럼 여러 값이 함께 있었던 것처럼 쓰지 않는다(코드 검사 CLUE_WORDING). 허용 밖 값 낱말은 "
    "쓰지 않는다(부정형으로 말하는 빠지는 값만 됨). 그 특징에 대한 사실만 쓰고 표에 없는 새 "
    "사실을 더하지 않는다. RULE 단서는 단정해서 쓰고 '~수도 있다·~것 같다·~듯'처럼 흐리게 쓰지 "
    "않는다. 곁 물건의 종류·이름(예: 흙 포대, 화분, 책장)처럼 표에 "
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
    "쓰지 않는다. (손에 든 것 종류는 대상이 처음부터 손에 있어 대상 겉에 묻은 것·대상 자체도 "
    "증거다 — 줄거리 종류 규칙)\n"
    "- RULE: allowed 밖 값을 가진 후보가 빠진다(빠지는 후보 목록은 코드가 표로 계산하므로 쓰지 "
    "않는다). 정답의 값은 allowed 안. 찾지 못한 "
    '것("없었다·못 봤다·안 들렸다")으로 빼지 않고(빠지는 값은 본 것·들은 것이 그 값이 '
    "아니었다고 씀, 코드 검사 CLUE_TEXT — #782 설계 v8), "
    "그 값 때문에 왜 답이 될 수 없는지 다른 가능성이 남지 않게 쓴다(시간이면 앞뒤가 다 막히게, "
    "크기면 단단한 물건으로).\n"
    "- RULE은 그때까지 남은 후보를 적어도 하나 새로 뺀다(이미 빠진 후보만 빼는 단서는 HINT로 "
    "쓴다).\n"
    "- HINT: 아무 후보도 빼지 않는다. 그때까지 남은 후보는 모두 allowed 값을 가져야 한다. 남은 "
    "후보를 하나라도 빼는 내용이면 "
    "HINT가 아니라 RULE로 쓴다. 이미 빠진 후보는 allowed 밖이어도 된다. 앞 요일과 같은 단서(같은 "
    "특징·같은 값)는 쓰지 않는다(코드 검사 CLUE_REPEAT). 새로 알려 줄 특징 값이 없으면 STORY로 "
    "쓴다.\n"
    "- STORY(사건 단서): 아무 후보도 빼지 않는 날에, 그날 찾은 증거에서 사건이 어떻게 벌어졌는지 "
    "새 사실을 준다(찾는 대상이 지나간 길·한 일·남긴 것. 예: '부스러기가 창틀 쪽으로 이어져 "
    "있었어!', '창밖 나뭇가지에 떡 조각이 걸려 있었어!'). feature는 '', allowed는 [] 로 쓴다. "
    "후보 이름과 특징 표의 값 낱말을 쓰지 않고(코드 검사 STORY_VALUE), 다른 요일 특징의 이름 "
    "낱말도 쓰지 않으며(예: 금요일 특징이 '출입문과 거리'면 '출입문 쪽으로'를 쓰지 않음, 코드 검사 "
    "STORY_FEATURE, #782 설계 v12), 남은 어떤 후보와도 "
    "어긋나지 않게 쓴다(상식으로 한 후보를 빼거나 가리키면 안 됨 — 예: 생쥐가 후보에 남았는데 "
    "'높은 나무 위로 갔다'). 시작 이야기(intro)에서 아이가 이미 본 모습(예: 빈 접시·흩어진 "
    "부스러기)은 새 사실이 아니라 쓰지 않는다(#782 설계 v9). 사건 단서는 다음 날 장소의 근거가 "
    "되어 한 주 이야기가 앞으로 "
    "나아가게 한다(예: 화 '창틀 쪽으로 이어진 부스러기' → 수 장소 '창틀 아래 마당').\n"
    "- 정답은 어떤 단서로도 빠지지 않는다. 틀린 후보는 각각 적어도 한 RULE 단서에서 빠진다. 마지막 "
    "틀린 후보는 금요일(FRI) 단서에서 빠져 그날 정답을 찾는다(목요일까지는 후보가 2개 이상 남음, "
    "#782 테마 짜임 사용자 결정 2026-11-19).\n"
    "- target은 찾는 대상(사라진 동물·물건)·밝힐 것(일을 한 동물·그 일을 한 때·타고 온 탈것)·손에 "
    "든 것이다(줄거리 종류 규칙). 손에 든 것 종류가 아니면 그 대상은 종료 이야기 전까지 찾지 "
    "못한 상태다. 어느 "
    "장면에서도 지금 있는 곳이 보이거나 말을 하지 않는다. 목격은 지나간 일로 쓴다. 장면에서 대상을 "
    "보거나 펼치거나 만지지 않는다. 같은 종류의 다른 물건이 나오면 '다른 그림책'처럼 찾는 대상이 "
    "아님을 밝힌다.\n"
    "- clueType은 주어진 종류 중 하나이고 다섯 단서가 모두 다른 종류다. '목격'은 SIGHTING 날, "
    "'기록'은 RECORD 날, '발자국'은 TRACE 날에만 쓴다. 같은 증거 종류가 두 날이면 그중 한 날만 "
    "'목격'·'기록'·'발자국'을 쓰고 다른 날은 그날 특징에 맞는 다른 종류(소리·시각·색·물기 등)를 "
    "쓴다.\n"
    "- evidence: 단서의 증거 종류(kind)와 그 증거가 생긴 때(when). kind는 TRACE(대상이 지나가거나 "
    "머문 곳에 남은 흔적), "
    "SIGHTING(대상을 본 사람의 목격), RECORD(대상을 찍은 사진·적은 기록) 중 하나이고 요일마다 "
    "주어진 '증거 종류 배정'을 그대로 쓴다(코드가 정함. 그날 특징에 맞는 증거 물건·사람을 골라 "
    "그 종류로 쓴다). TRACE 날의 단서 특징은 흔적에 남을 수 있는 것(대상이 닿은 바닥·면의 "
    "재질·물기·무늬, 자리의 모양·크기·무게, 동물 주인공 종류는 동물 몸이 남긴 발자국·발톱·꼬리·"
    "털 자국도)으로 고른다. 빛·그늘·소리·냄새·바람·거리·때·주변 색은 "
    "흔적에 남지 않으므로 TRACE 날 특징으로 쓰지 않는다(맞지 않으면 코드가 배정을 다른 날과 바꿈). "
    "when은 큰 질문이 "
    "묻는 그때(예: "
    "마지막으로 둔 때)와 맞는 때로 쓰고, 다섯 단서가 모두 "
    "같은 그때를 가리킨다. clue에는 시각을 쓰지 않는다. "
    # #782 미션 방식(사용자 결정 2026-11-20): 전에는 모든 날 '발견 장면 대사' 예시 하나라 방식
    # 규칙과 부딪혀 단서가 그날 일과 따로 놀았음(작은 생성 r782-ways-rd3)
    "clue는 그날 미션 방식대로 한 줄 말로 쓴다. 부탁 날은 helper가 도와준 아이에게 자기가 본 것·"
    "가진 것을 직접 알려 주는 말(본 것 '그때 공 바구니 곁에서 인형을 봤어!', 흔적 '창고 앞 "
    "흙길에서 "
    "내가 강아지 발자국을 봤어!', 기록 '내 사진에 털이 긴 꼬리가 찍혀 있어!', 들은 것 '그때 "
    "내가 들은 소리는 따르릉 소리는 아니었어!'). 전해 들은 말"
    "('~였대·~났대')로 쓰지 않고, 흔적 날은 helper가 본 흔적임을 밝힌다(코드 검사 CLUE_SOURCE). "
    # #782 설계 v12: 12차 snd4 '내가 직접 본 소리 난 곳은'(약속은 들은 소리)
    "특징이 소리(소리 종류·소리 난 곳·움직임 등)인 날은 들은 것으로 쓰고 '본'·'눈으로'를 쓰지 "
    "않는다(예: '내가 들은 소리가 난 곳은 지붕 위가 아니었어!', 코드 검사 SOUND_SEEN). "
    # #782 설계 v4: 3차 측정 '내 일지' 약속 뒤 남의 일지, '본 흔적'인데 소리
    "기록 날은 helper 자신의 기록이라 '내 {매체}'로 쓰고(남이 쓴 기록 아님, '내 일지엔 ~래'처럼 "
    "남의 말로 끝내지 않음 — 코드 검사 RECORD_HEARSAY, #782 설계 v12), 흔적 날 "
    "소리·냄새·맛은 "
    "눈으로 본 것이 아니라 '내가 흔들어 보니·맡아 보니·맛보니'로 쓴다. "
    # #782 설계 v13: 지문에 없는 사실을 단서가 말해 글 검토 CLUE_LOGIC → 줄거리를 통째로 다시
    # (10~13차 느린·실패 테마가 매번 같은 수사 날 요청)
    "수사 날은 그 증거를 따져 확실해진 사실, 곧 지문 증언 속 그 내용이다(증언에 없는 내용을 더하지 "
    "않음, 예: '끈이 스친 자국 밑에 나무 바닥이 보였어!'). "
    "'고마워!' 같은 앞말은 붙이지 않는다(웹 단서 목록에 한 줄씩 모여 보임). "
    "'바닥 재질은 나무였고'처럼 특징 이름을 늘어놓지 않는다"
    "(#782 테마 짜임). clue·discovery는 "
    "배정된 종류에 맞춘다: RECORD 날은 배정된 기록 매체 "
    "낱말(사진·영상·메모·일지·녹음 중 하나)을 clue와 discovery에 그대로 쓰고, SIGHTING 날은 본 "
    "사람의 목격, TRACE 날은 남은 흔적으로 쓰며 두 날 clue에는 사진·영상·녹음·기록·일지·메모를 "
    "쓰지 않는다(코드 검사 CLUE_EVIDENCE). 사진·기록에 찍힌 "
    "그때의 대상 모습은 써도 되지만 지금 있는 곳은 쓰지 "
    "않는다.\n"
    "\n"
    "오늘 온 까닭·돕는 사람·오늘 할 일(문제 앞 대화를 쓰는 재료, 대화 모델이 자기 말로 풀어 "
    "씀) — 단서는 학생이 그날 문제를 마친 뒤에 보여 준다\n"
    # #782 테마 짜임(사용자 결정 2026-11-19 "어제 한 일만 잇기"·"줄거리가 요일마다 한 걸음"): 대화
    # 규칙이 앞 요일을 말하지 못하게 해 요일마다 새 장면이 됐음(문제 전 대화에 찾는 대상 낱말이 나온
    # 날 25/179)
    # #782 설계 v7(사용자 결정 2026-11-22): 코드 문장(v3)은 한 주가 같은 꼴이라 거절됨("너무 똑같이
    # 반복"). 어제 돕는 사람 이름을 꼭 넣게 한 v5는 그 사람이 하지 않은 부탁·소개·지시를 지어냈음
    # (5차 화~금 92줄 중 들은 것만 말한 줄 10) → 오늘 여기 온 까닭을 쓰고 어제 일은 들은 것만
    "- dayStep: 오늘 이 장소에 온 까닭 한 줄(공백 포함 32자 안팎, 40자를 넘으면 안 됨). 대화 첫 "
    "줄로 첫 등장인물이 직접 하는 말이라 '나'의 말로 쓰고 그 인물의 이름은 쓰지 않는다(코드 검사 "
    "SELF_NAME). 월요일은 시작 이야기의 사건 직후 첫 조사 장소로 온 까닭(첫날이라 '어제'라고 쓰지 "
    "않음, 코드 검사 DAY1_TIME). 화~금은 오늘 장소·그곳 사람이 사건과 어떻게 닿는지에서 까닭을 "
    "찾는다(예: '고양이가 빵집 앞을 지났을지 몰라 와 봤어', '장터에서 사람이 제일 많이 오가는 "
    "쉼터라면 누가 봤을 거야'). 어제 일은 넣지 않아도 되고, 넣을 때는 어제 들은 것만 쓴다(예: "
    "'정자 할머니 말을 듣고 냇가 쪽도 살펴보러 왔어'). 어제 돕는 사람이 부탁·소개·지시하거나 "
    "자료를 건넸다고 쓰지 않고, 오늘 할 일(부탁)도 쓰지 않는다 — 부탁은 대화에서 그날 사람이 "
    "한다(코드 검사 DAY_STEP_MADE). '어제 ~'라고 쓰면 어제 단서·장면에 있던 일만 쓴다(11차 "
    "way3b 화요일에 없던 '어제 포장 끈이 날아간 쪽'). 앞 요일 기록을 대면 그 기록 단서에 있는 "
    "것만 댄다(예: 목요일 "
    "일지가 '뒷문이 닫혀'면 금요일에 '일지에 나온 포장방 문턱'이라 쓰지 않음, #782 설계 v12). "
    "요일마다 말투를 바꿔 같은 꼴을 되풀이하지 않는다. 앞 요일 "
    "단서가 무엇이었는지(그날 allowed 값)·오늘 단서 결론·후보 이름·정답은 말하지 않는다(코드 검사 "
    "PREV_CLUE·CLUE_EARLY).\n"
    # #782 테마 짜임(사용자 결정 2026-11-20 "부탁을 들어주면 알려 줌"·"세 가지 섞기"): 미션을 사건
    # 증거 속에 끼워 넣으면 성취기준이 정한 미션(삼각형·방언·시 감상)이 사건과 상관없어 억지였음
    # (사람 판단 살피기 날 6/6 억지). 해결사가 수사하러 간 김에 그곳 사람을 돕고 그 보답·과정으로
    # 단서를 얻는다
    # #782 설계 v3(사용자 결정 2026-11-21): 일 → 사람 → 장소. 장소 사람에게 일을 맡기니 "운동장
    # 선생님이 모래밭에서 시 감상 글"처럼 동떨어졌음(2차 측정 억지 30일 중 13일)
    # #782 설계 v10: 코드가 준 호칭 둘 중에서 고르게 하니 같은 호칭이 되풀이됨(7차 17번). 영역의
    # 일 종류만 주고 일 → 사람 → 쓰임 → 장소 순서로 모델이 정함
    "- helper: 사용자 글에 '국어 부탁 날 그날 성취기준의 일'이 있는 날은 이 순서로 정한다: ① 그날 "
    "성취기준의 일(주어진 일 종류 안에서 그날 성취기준 활동이 그대로 쓰이는 일) → ② 그 일을 "
    "늘 하는 사람(helper, 공백 포함 12자 이내) → ③ 아이 답이 그 사람 일에 쓰이는 곳(helperUse) → "
    "④ 그 사람이 그 일을 하는 자리(place). 장소를 먼저 두고 그 장소 사람에게 성취기준 일을 "
    "맡기지 않는다(예: 운동장 선생님이 모래밭에서 시 감상을 부탁하면 억지). "
    "그 밖의 날은 그날 장소에 있는 사람 호칭(공백 포함 12자 이내, 예: '떡집 사장님'·'정자 "
    "할아버지'·'축제 진행자'). 등장인물(characters)이 아닌 그날만 나오는 사람이고, 요일마다 "
    "다른 사람이다(같은 사람이 매일 부탁하면 '왜 처음부터 안 알려 줘?'가 됨, 코드 검사 "
    "HELPER_SAME). 후보·찾는 대상·뭉치가 "
    "아니고, 그날 장소에 어울리는 사람이다. sceneNote에 그 사람이 그 자리에서 하는 일을 함께 "
    "쓴다. 부탁 날 sceneNote에는 증거·흔적·자국을 쓰지 않는다(그날 증거는 문제를 마친 "
    "뒤 단서로 나오고, 장면 메모는 문제 전 대화·그림 재료라 새어 나감, 코드 검사 "
    "EVIDENCE_EARLY).\n"
    # #782 설계 v10: 쓰임이 없음 46일 중 32일 — 쓰임을 모델이 칸으로 정하고 미션 글이 그 낱말을 씀
    "- helperUse: 국어 부탁 날(위 '그날 성취기준의 일'이 있는 날)만 쓴다. 아이가 쓴 답이 helper의 "
    "일에 실제로 쓰이는 곳을 helper의 말 한 줄로(공백 포함 40자 이내, 예: '책 추천 카드에 "
    "붙일게'). 쓰이는 곳 낱말(두 글자 이상)을 '~에·~에다·~으로·~로' 바로 앞에 쓴다 — 미션 문제 "
    "글이 이 낱말 중 하나를 써야 한다(코드 검사 USE_MISSING). 비우면 코드 검사 REQUIRED. 그 밖의 "
    "날은 빈 문자열.\n"
    "- 미션 방식: 사용자 글의 '미션 방식 배정'을 그대로 따른다(코드가 정함). 그날 미션(문제)이 "
    "이야기에 들어오는 길이다.\n"
    "  - 부탁: helper가 자기 일로 곤란해한다 → 뭉치와 아이가 도와준다(그날 미션) → helper가 "
    "고마워하며 본 것·가진 것을 알려 준다(그날 단서). missionHook은 helper의 부탁 한 줄(예: '떡 "
    "상자 나누는 계산 좀 도와줄래? 그럼 그날 본 걸 말해 줄게'), missionMaterial은 그 일의 "
    "자료(helper의 안내문·쪽지·지은 시·셀 수 등), clue는 helper가 알려 주는 말(예: '그날 "
    "창틀로 날아가는 긴 꼬리를 봤어!').\n"
    "  - 수사: helper가 가진 증거(본 사람의 말·적은 기록)를 같이 읽고 따진다(그날 미션) → 따져서 "
    "확실해진 사실이 그날 단서다(기록 날도 지문이 그 기록이라 '메모에는 ~라고 적혀 있어'로 "
    "옮기지 않고 '메모를 따져 보니 ~'처럼 따져서 확실해진 사실로 씀, 코드 검사 CLUE_SOURCE — "
    "#782 설계 v9). missionHook은 증거를 같이 읽고 따져 보자는 말 한 줄, "
    # #782 설계 v11: v10 수사 날 두 증언 비교를 v9로 되돌림(8차 따져 보기 날 예시 답 길이 실패
    # 6 → 19)
    # #782 설계 v13: v11의 '지문에 단서 특징을 쓰지 않음'은 따져서 확실해진 것이 단서가 될 수 없어
    # 글 검토 CLUE_LOGIC "지문에 없는 결론"과 부딪힘(10~13차 느린·실패 테마, 13차 치명 snd3). v10의
    # 두 말 견주기는 예시 답이 길어져(8차 6 → 19) 증언 하나로
    "missionMaterial은 그 증거의 내용(그때 찾는 대상·사건에 관한 말·글)으로, 그때 직접 보거나 "
    "듣거나 그때 적은 사람의 증언 하나다. 증언에는 그날 단서 내용이 그대로 들어간다(특징 단서 "
    "날은 단서가 말하는 값 낱말을 단서와 같은 꼴로 — 빠지는 값이면 '갈색 대문은 아니었어요'처럼, "
    "사건 단서 날은 그 사건 내용, 코드 검사 TESTIMONY_MISSING). 직접 보거나 그때 적었다는 것이 "
    "드러나게 쓴다(학생이 믿을 만한지 따질 근거). 짐작·의견을 한 마디 섞어도 되지만 단서 내용은 "
    "직접 본 사실 쪽에 둔다. clue는 따져서 확실해진 그 증언 내용이다(증언에 없는 내용을 더하지 "
    "않음). 후보 이름·정답은 쓰지 않는다. 지문은 그때 본 사람·적은 사람의 "
    "말·글이고(흔적 날도 그 흔적을 처음 본 사람의 말·적어 둔 글로) "
    "따지는 것도 그 사람의 말·글이다. helper 자신의 생각·마음을 추측하게 하지 "
    "않는다('내 생각을 추론해 볼래?' 금지, 코드 검사 HOOK_SELF). 수사 날은 '따지기' 성취기준"
    "(사실·의견 구별, 출처·매체가 믿을 만한지) 날에만 배정되므로 문제는 그 말·글이 사실인지·믿을 "
    "만한지 따지게 한다. 문제는 지문만 보여 주고 '○○가 그때 본 일을 설명하고'처럼 지문에 없는 "
    "증언을 준다고 쓰지 않는다(9차 new3, 코드 검사 MISSION_TESTIMONY, #782 설계 v12).\n"
    # 사용자 결정 2026-11-20 "서술·논술·성취기준과 잘 맞게": 부탁 날 아이가 쓴 서술 답이 곧 그
    # 사람에게 주는 도움. 그 사람의 글은 사건과 같은 주제로(실측: 인형 사건에 '종이와 연필을
    # 챙기세요' 쪽지)
    "  - 부탁 날 helper의 글(missionMaterial)은 사건과 같은 주제(잃어버린 물건 안내, 밤 소리 "
    "안내, 축제 정리 등 그 장소·사건 분위기)로, 그날 성취기준이 요구하는 글 종류(문학이면 "
    "시·이야기, 문장 성취기준이면 고칠 문장이 있는 쪽지, 매체면 기사·안내 글, 예측하며 읽기면 "
    "뒷이야기가 궁금하게 끝나는 이야기의 앞부분)로 쓴다. 아이가 쓴 "
    "답이 그대로 helper의 일에 쓰이게 한다(예: 아이가 쓴 요약이 안내판에 붙음). 국어 부탁 날은 "
    "helperUse의 쓰임 그대로 쓴다(#782 설계 v10).\n"
    # 사용자 결정 2026-11-20 "A+C": 40개 측정 r782-final40 억지 판정 46일 중 32일이 "아이가 쓴 답이
    # 돕는 사람의 일에 안 쓰임" — 주로 금(돌아보기 16)·화(주장 14). 그 날 문제는 아이 자신의 생각·
    # 경험을 쓰게 해서, 시집 정리를 부탁받아도 아이의 경험이 그 일에 쓰일 수 없었음
    "  - 그날 문제가 아이 자신의 생각·주장·경험을 쓰게 하는 날(돌아보기, 주장 쓰기, 감상 등)은 "
    "helper가 바로 그것을 필요로 하는 일을 부탁한다: 그 사람의 일(helper·helperUse, "
    "돌아보기 날도 같음 — #782 설계 v9·v10)에 아이의 생각·경험이 들어가는 자리(예: '책을 읽은 "
    "아이들 생각을 모으고 있어. 써 주면 소식지 읽은 생각 칸에 실을게', '내 시를 읽은 아이 감상을 "
    "모으고 있어. 써 주면 시집 뒤에 실을게', '손님 의견판에 붙일 네 생각을 까닭과 함께 써 "
    "줄래?'). helper의 글을 대신 정리해 달라고 하지 않는다(아이 자신의 경험이 그 정리에 쓰일 수 "
    "없음).\n"
    "  - 부탁 날의 미션은 helper의 일이라 사건 증거가 아니어도 된다(사건인 척 지어내지 "
    "않음). 그날 성취기준·생각 유형 활동이 자연스러운 helper의 일을 고른다(분석: 긴 안내문 "
    "간추리기, 따져 보기: 손님 의견판에 붙일 내 주장, 새로 만들기: 새 팻말·안내 방법, 문제 해결: "
    "나누기·재기·셈, 돌아보기: helper의 글을 읽은 아이의 달라진 생각·경험을 모으기 등).\n"
    "- discovery: 그날 단서가 나오는 증거 한 줄(공백 포함 32자 안팎, 40자를 넘으면 안 됨). 그림이 "
    "이 증거를 그린다. 그날 evidence 종류에 맞는 증거(TRACE면 흔적이 남은 물건·자리, SIGHTING이면 "
    "본 사람, RECORD면 사진·기록)다. 부탁 날은 helper가 본 것·가진 것, 수사 날은 helper가 "
    "가진 증거다. 단서 결론(allowed 값 낱말)·후보 이름·정답은 "
    "말하지 않는다.\n"
    "- missionHook: 위 미션 방식대로 helper가 하는 부탁·증거를 같이 보자는 말 한 "
    '줄(공백 포함 32자 안팎, 40자를 넘으면 안 됨). 대화 마지막에 뭉치가 받아 "같이 해 보자"고 '
    "잇는 재료다. 그 일과 활동을 함께 말한다. "
    + HOOK_ACT_RULE
    + " '<증거>를 풀려면 <배울 것>이 필요해'처럼 그 일과 상관없는 활동이 증거를 풀어 준다고 "
    "쓰지 않는다(#782 C안)."
    " 글로 할 수 없는 활동(그래프 그리기·만들기·재기·걷기)을 시키지 않는다(코드 검사 ACT_NAME, "
    "#782 설계 v8)."
    # #782 설계 v9: 6차 억지 13일 중 6일이 목요일 수학 "구한 값을 그 일에 어떻게 쓰는지 안 나옴"
    " 수학 부탁 날은 구한 값을 그 사람이 어디에 쓰는지 함께 말한다(예: '상자마다 리본을 "
    "자르려는데 한 상자 몫을 구해 줄래?' — '계산해 줄래?'만 쓰지 않음)."
    # #782 설계 v10
    " 국어 부탁 날 부탁은 helperUse의 쓰임과 같은 일을 가리킨다(다른 일로 바꾸지 않음)."
    " 그 안에서 학생이 고르거나 답할 것(계산 결과, 중심 생각, 고를 자료)은 말하지 않는다(글 "
    "검토 ANSWER_HINT). 그날 단서 결론(allowed 값)·후보 이름·정답은 말하지 않는다.\n"
    # #782: 이름만 정하면 미션 단계가 내용을 지어내 사건·일과 무관한 글로 빠졌다(실측 3건). 이야기
    # 전체를 아는 이 단계가 내용까지 써 두고 미션은 그대로 쓴다
    "- missionMaterial: 그날 할 일의 실제 자료(공백 포함 60~120자, 150자를 넘으면 안 됨). 그날 "
    "문제의 지문으로 그대로 들어가 학생이 문제 전에 읽는다. 부탁 날은 helper의 일의 "
    "자료(안내문·쪽지·지은 시·후기·셀 수), 수사 날은 helper가 가진 증거의 내용이다. 그날 성취기준 "
    "활동을 그 지문만으로 할 수 있게 쓴다: 문장을 다루는 국어면 두세 문장의 말·글(읽기·감상·매체를 "
    "다루면 세 문장 안팎), 계산하는 수학이면 같은 단위로 견줄 수 있는 수 두세 개이고 문제의 최종 "
    "답은 그 수로 계산해 새로 나오는 값이 되게 한다(지문의 수 하나가 그대로 답이면 정답 유출 "
    "LEAK). 후보 이름·정답·지금 대상이 있는 곳은 쓰지 않는다(코드 검사 ANSWER_LEAK). 부탁 날 "
    "지문에는 그날 단서 결론(allowed 값 낱말)·단서 특징에 대한 말도 쓰지 않는다(코드 검사 "
    "CLUE_EARLY — 수사 날은 위 수사 규칙대로 증언에 넣음, #782 설계 v13). "
    "이야기 속 다른 사실(단서·장면 메모)과 "
    "어긋나지 않게 쓴다. 지문은 자료만 쓰고 부탁·쓰임 문장('~에 실으려 해요'·'~해 줄래?')과 "
    "시키는 말('그래프로 나타내 보자'·'줄자로 재 보세요')은 쓰지 않는다 — 부탁은 missionHook과 "
    "대화가 한다(코드 검사 ACT_NAME, #782 설계 v8). 부탁 날 지문은 helper 자신의 기록(내 메모·"
    "일지·사진 — 그날 증거)이 아니다: 기록은 미션을 마친 뒤 단서로 나온다(코드 검사 "
    "MATERIAL_RECORD). 수학 지문은 그 학년이 배운 셈으로 풀리게 쓴다(초3은 분수를 더하거나 빼지 "
    "않음, 코드 검사 GRADE_MATH — #782 설계 v9).\n"
    # #782 확정 코드 40건 실패 원인(문제 글 확인): 수학 지문 조건 부족·모순(way5·snd6b), 지문이
    # 수사를 마친 뒤의 회고라 단서의 그때와 어긋남(auto6b), 문학 작품 성취기준인데 지문이
    # 목격담(hand5)
    "  - 수학 지문은 문제를 푸는 데 필요한 조건(개수·모양·방향·배치·단위)을 빠짐없이 쓰고 서로 "
    "어긋나지 않게 쓴다(예: '조각 네 개'만이 아니라 '같은 크기의 정사각형 조각 네 개를 위·아래·"
    "왼쪽·오른쪽에', 쌓은 수와 바닥에 닿은 수가 함께 성립하게).\n"
    "  - 수사 날 지문은 단서의 그때와 같은 때의 내용만 쓴다. 수사를 마친 뒤의 회고·나중에 알게 "
    "된 일·이번 주 전체를 돌아본 말은 쓰지 않는다(기록·영상은 그때 찍히거나 적힌 것).\n"
    "  - 그날 성취기준이 특정한 글 종류(문학 작품·시·이야기·안내문·광고·면담 기록 등)를 읽거나 "
    "다루게 하면 지문을 그 종류로 쓴다. 부탁 날은 helper가 쓰거나 가진 글(예: 정자 "
    "할머니가 손주에게 보내려고 지은 시), 수사 날은 그때 이번 일을 겪은 사람이 쓰거나 말한 "
    "것이다.\n"
    # #782 설계 v10(2.3): 종류와 상관없이(5·7차 hand5 '대회에서 본 떡'·'대회장 안으로', auto4b
    # '별빛 캠핑을 마친')
    "- 시작 이야기에서 앞으로 열릴 행사(예: '토요일 떡 대회', '별 보기 모임 직전')는 끝 이야기 "
    "전까지 열리지 않았다. clue·missionMaterial·미션 글에서 그 행사를 이미 열린 것처럼('대회에서 "
    "본'·'대회장 안으로 간'·'모임을 마친') 쓰지 않고 '~에 낼·나갈·가져갈·준비·앞둔'처럼 앞일로만 "
    "쓴다(코드 검사 EVENT_LATER).\n"
    # 예시를 녹음기로 두었더니 초안 155개 중 55개(35%)에 녹음이 들어감(2026-11-11 집계). 증거
    # 매체 낱말은 예시로 주지 않는다(탐정 모자 예시 13건과 같은 따라 쓰기)
    "- 위 예시들은 특징·문장을 정하는 방향일 뿐이다. 예시 낱말·문장을 그대로 쓰지 말고 이 테마에 "
    "맞게 새로 정한다.\n"
)


# 등장인물 이름은 코드가 고른다(LLM이 고르면 민지·준호가 반복, 실측 19개 테마 중 9·8번).
# 같은 요청(주·학년)은 같은 이름이 나오게 정해진 씨앗으로 고른다(다시 생성해도 인물이 바뀌지 않게)
NAME_POOL = (
    "하준",
    "서윤",
    "도윤",
    "지안",
    "시우",
    "하은",
    "예준",
    "수아",
    "주원",
    "지유",
    "은우",
    "채원",
    "로운",
    "다인",
    "이안",
    "윤슬",
    "선우",
    "아린",
    "태오",
    "하린",
    "건우",
    "소율",
    "유찬",
    "나은",
    "한결",
    "예린",
    "도하",
    "가온",
    "민결",
    "세아",
    "라온",
    "보민",
    "단우",
    "새봄",
    "이든",
    "누리",
    "온유",
    "해솔",
    "리안",
    "다온",
)
NAMES_PER_THEME = 6


def plan_seed(request: ThemeDraftRequest) -> str:
    """코드가 고르는 값(이름·증거 배정)의 씨앗: 같은 요청(주·학년)이면 같은 값."""
    return f"{request.week_start.isoformat()}-{request.grade}"


def names_for(request: ThemeDraftRequest) -> list[str]:
    import random

    rng = random.Random(plan_seed(request))
    return rng.sample(NAME_POOL, NAMES_PER_THEME)


WAY_KO = {ASK: "부탁", INVESTIGATE: "수사"}


def day_plans_for(
    request: ThemeDraftRequest,
) -> tuple[dict[str, str], dict[str, dict[str, str | None]]]:
    """요일마다 미션 방식과 증거 종류·기록 매체 배정을 함께(#782 미션 방식, 코드가 정함 — 이름
    고르기와 같은 씨앗이라 다시 생성해도 같음). 방식이 그날 증거 종류에 맞게 증거 배정의 요일 순서를
    맞춘다(checks.mission_way_plan)."""
    import random

    days = []
    for day, thinking in DAY_TYPE.items():
        mission = request.mission_for(thinking)  # type: ignore[arg-type]
        days.append((day, [s.code for s in mission.standards], mission.input_type))
    # 흔적으로 알 수 있는 특징이 없는 종류(시간 탐정)는 흔적을 목격으로 바꿔 줌(#634 ④)
    kind = parse_topic(request.topic)
    plan = plan_for_type(evidence_plan(plan_seed(request)), kind)
    return mission_way_plan(days, plan, random.Random(f"{plan_seed(request)}-way"))


def day_frames_for(request: ThemeDraftRequest) -> dict[str, dict[str, Any]]:
    """요일마다 성취기준 코드와, 국어 부탁 날이면 돕는 사람 호칭 후보 둘·아이 답의 쓰임(#782
    설계 v3,
    코드가 정함 — 같은 씨앗이면 같음). plan_theme이 줄거리 내부 칸 dayFrames에 넣는다."""
    import random

    days = []
    for day, thinking in DAY_TYPE.items():
        mission = request.mission_for(thinking)  # type: ignore[arg-type]
        days.append((day, [s.code for s in mission.standards], thinking))
    ways = mission_ways_for(request)
    return day_frames(days, ways, random.Random(f"{plan_seed(request)}-helper"))


def mission_ways_for(request: ThemeDraftRequest) -> dict[str, str]:
    """요일마다 미션 방식. plan_user가 알리고 plan_theme이 줄거리 내부 칸 missionWay에 넣는다."""
    return day_plans_for(request)[0]


def evidence_plan_for(request: ThemeDraftRequest) -> dict[str, dict[str, str | None]]:
    """요일별 증거 종류·기록 매체 배정(#535). plan_theme이 줄거리에 evidencePlan으로 붙여
    검사한다(다시 생성해도 같은 배정, 요일 순서는 미션 방식에 맞춤 — day_plans_for)."""
    return day_plans_for(request)[1]


def candidate_group_for(request: ThemeDraftRequest) -> str | None:
    """범주가 있는 사실표 종류(소리 탐정)의 이번 테마 후보 범주(동물·물건). 이름·증거 배정과 같은
    씨앗이라 다시 생성해도 같고, 주·학년마다 섞인다. 모델에 맡기면 작은 실측 4건 모두 같은 동물
    4마리를 골라 물건 범주가 나오지 않았음(#634 ⑤). 씨앗 주제가 아니거나 범주가 없으면 None.
    주제 글 끝 칸 갈래가 범주 이름(동물·물건)이면 그 범주(#782 기준안 — 확인 전)."""
    import random

    fields = parse_topic_fields(request.topic)
    if fields is None:
        return None
    found = fields.story_type
    if found.facts is None or not found.facts.groups:
        return None
    groups = sorted(set(found.facts.groups.values()))
    if fields.branch in groups:
        return fields.branch
    return random.Random(f"{plan_seed(request)}-group").choice(groups)


def group_pool(request: ThemeDraftRequest, fields: TopicFields, group: str | None) -> list[str]:
    """범주가 있는 사실표 종류(소리 탐정)의 그 범주 후보 풀(표 순서). 성격 칸 태그와 어울리는 줄만
    (기준안 families.SOUND_PLACES, #782). 성격 칸이 없거나 맞는 줄이 후보 개수보다 적으면 태그로는
    거르지 않되, 겨울에 빼는 줄(개구리)은 겨울에 늘 뺌(candidate_pool의 동물 거르기와 같은 방식)."""
    table = fields.story_type.facts
    assert table is not None
    names = [c for c in table.rows if table.group(c) == group]
    if table is not SOUNDS:
        return names
    month = request.week_start.month
    fit = [c for c in place_sounds(fields.traits, month) if c in names] if fields.traits else []
    if len(fit) >= CANDIDATES[request.grade]:
        return fit
    if season_of(month) == "겨울":
        return [c for c in names if c not in SOUND_NO_WINTER]
    return names


def candidate_pool(request: ThemeDraftRequest, fields: TopicFields) -> list[str]:
    """범주가 없는 사실표 종류의 후보 풀(표 순서). 장소가 맞아야 둘 수 있는 이름(탈것의 여객선은
    장소 칸이 물가이거나 성격 태그에 물가·바다가 있을 때만, VEHICLE_PLACE)을 빼고, 동물은 성격 칸
    태그와 사는 곳·계절이 맞는 동물만(기준안 families.ANIMAL_HABITATS). 성격 칸이 없거나 맞는
    동물이 후보 개수보다 적으면 사는 곳으로는 거르지 않되, 겨울잠 동물은 겨울에 늘 뺀다(#782: 성격
    칸이 없는 겨울 주에 다람쥐가 정답이 되던 것). 성격 태그에 섬이 있으면 기차를 뺀다(#782 기준안
    — 확인 전, 섬에는 기차가 다니지 않음)."""
    t = fields.story_type
    names = list(t.facts.rows) if t.facts else []
    tags = {x.split()[0] for x in fields.traits if x.split()}
    water = bool({"물가", "바다"} & tags)
    for name, place in t.place_needs:
        if not (place.search(fields.place) or water):
            names = [n for n in names if n != name]
    if "섬" in tags:
        names = [n for n in names if n != "기차"]
    if t.animal:
        fit = habitat_animals(fields.traits, request.week_start.month) if fields.traits else []
        if len(fit) >= CANDIDATES[request.grade]:
            names = [n for n in names if n in fit]
        elif season_of(request.week_start.month) == "겨울":
            names = [n for n in names if n not in ANIMAL_NO_WINTER]
    return names


def candidate_plan_for(request: ThemeDraftRequest) -> dict[str, Any] | None:
    """사실표 종류의 후보 4개와 정답(코드가 정함, 이름·증거 배정과 같은 씨앗이라 다시 생성해도
    같고 주·학년마다 섞인다). 씨앗 주제가 아니거나 사실표가 없는 종류면 None.

    범주가 있는 종류(소리 탐정)는 범주를 먼저 고르고 그 범주에서 4개(#782: 성격 태그로 거른 줄
    group_pool에서. #634 ⑤ 작은 실측: 범주만
    정하면 동물 4건 모두 부엉이·고양이·생쥐·너구리, 물건 4건 중 정답 바람개비 3건). 표의 줄은 소리
    난 곳이 모두 달라 어떤 4개를 골라도 정답을 가를 수 있음(FactTable.blocked가 비어 있음, 시험).
    그 밖 종류(동물·선물·재료·시각·탈것)는 모델이 표에서 '그 장소에 어울리는 4개'를 골라 같은
    씨앗이 돌아오면 같은 정답이 되풀이됐음(#782: 떡집 5번 모두 너구리) — 정답을 먼저 고르고 나머지
    후보는 정답과 FactTable.blocked로 막힌 이름(시각: 오전 10시 ↔ 낮 12시·오후 3시)을 뺀 풀에서."""
    import random

    fields = parse_topic_fields(request.topic)
    if fields is None or (table := fields.story_type.facts) is None:
        return None
    k = CANDIDATES[request.grade]
    rng = random.Random(f"{plan_seed(request)}-candidates")
    if table.groups:
        group = candidate_group_for(request)
        names = group_pool(request, fields, group)  # #782 성격 태그·겨울로 거른 그 범주 줄
        cands = rng.sample(names, k)
        return {"group": group, "candidates": cands, "answer": rng.choice(cands)}
    pool = candidate_pool(request, fields)
    blocked = table.blocked()

    def others(answer: str) -> list[str]:
        return [c for c in pool if c != answer and c not in blocked.get(answer, [])]

    answers = [a for a in pool if len(others(a)) >= k - 1]
    if not answers:
        return None
    answer = rng.choice(answers)
    cands = [answer, *rng.sample(others(answer), k - 1)]
    rng.shuffle(cands)  # 정답이 늘 같은 자리에 있지 않게
    return {"candidates": cands, "answer": answer}


def evidence_plan_lines(plan: dict[str, dict[str, str | None]]) -> list[str]:
    lines = ["", "증거 종류 배정(evidence.kind, 코드가 정함. 요일마다 그대로 따른다):"]
    for day, slot in plan.items():
        kind = str(slot["kind"])
        medium = f", 기록 매체: {slot['medium']}" if slot.get("medium") else ""
        lines.append(f"- {day}({DAY_KO[day]}): {kind}({EVIDENCE_KO[kind]}){medium}")
    return lines


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
    lines.append(f"등장인물 이름 목록(이 안에서만, 필요한 만큼): {', '.join(names_for(request))}")
    lines += [
        "",
        "요일 배치와 그날 문제의 성취기준(문제는 따로 만든다. 장면에 그 활동이 자연스럽게 나올 "
        "거리를 넣는다):",
    ]
    for day, thinking in DAY_TYPE.items():
        mission = request.mission_for(thinking)  # type: ignore[arg-type]
        standards = "; ".join(f"{s.code} {s.statement}" for s in mission.standards)
        lines.append(f"- {day}({DAY_KO[day]}): {THINKING_LABEL[thinking]} / {standards}")
    lines += evidence_plan_lines(evidence_plan_for(request))
    lines += [
        "",
        "미션 방식 배정(코드가 정함. 요일마다 그대로 따른다, 규칙은 시스템 지시의 '미션 방식'):",
    ]
    lines += [
        f"- {day}({DAY_KO[day]}): {WAY_KO[way]}({way})"
        for day, way in mission_ways_for(request).items()
    ]
    # #782 설계 v10: 호칭·쓰임 목록 대신 영역의 일 종류만(호칭·쓰임은 대신용 틀로 dayFrames에만)
    frames = {d: f for d, f in day_frames_for(request).items() if f.get("work")}
    if frames:
        lines += [
            "",
            "국어 부탁 날 그날 성취기준의 일(일 종류, 코드가 정함. 그날 성취기준의 일 → 그 일을 "
            "하는 사람(helper) → 아이 답의 쓰임(helperUse) → 장소(place) 순서로 정한다):",
            *[f"- {day}({DAY_KO[day]}): {f['work']}" for day, f in frames.items()],
        ]
    lines += ["", *story_type_lines(request)]
    if feedback:
        lines += ["", "이전 테마가 검사를 통과하지 못했다. 아래를 고쳐서 새로 만든다:"]
        lines += [f"- {stage}: {reason}" for stage, reasons in feedback for reason in reasons]
    return "\n".join(lines)


def seed_story_type(request: ThemeDraftRequest) -> str | None:
    """주제가 learning 씨앗이면 그 종류 코드(plan_theme이 줄거리 storyType을 이 값으로 덮어씀)."""
    found = parse_topic(request.topic)
    return found.code if found else None


def seed_branch(request: ThemeDraftRequest) -> tuple[bool, str | None]:
    """씨앗 주제의 갈래를 코드가 정하는지와 그 값(#782 기준안 — 확인 전).

    - 주제 글 끝 칸에 갈래가 있음: (True, 그 값). 그 종류 목록 밖이면 무시하고 (True, None)
    - 갈래 칸이 없고 후보 범주를 코드가 고른 종류(소리 탐정): (True, 그 범주) — 갈래가 곧 범주라
      모델이 다른 값을 고르면 후보와 어긋남
    - 갈래가 없는 종류: (True, None)
    - 그 밖(갈래가 있는 종류의 예전 초안·관리자 자유 글): (False, None) — 모델이 목록에서 고름
    """
    fields = parse_topic_fields(request.topic)
    if fields is None:
        return False, None
    code = fields.story_type.code
    if fields.branch is not None:
        return True, valid_branch(code, fields.branch)
    if code not in STORY_BRANCHES:
        return True, None
    plan = candidate_plan_for(request)
    if plan and plan.get("group"):
        return True, valid_branch(code, plan["group"])
    return False, None


def branch_for(request: ThemeDraftRequest, theme: dict[str, Any]) -> str | None:
    """줄거리 내부 칸 branch의 값(plan_theme이 storyType을 덮어쓴 뒤 부름). 코드가 정하면 그 값,
    아니면 모델 값(그 종류 목록 밖이면 None)."""
    decided, value = seed_branch(request)
    return value if decided else valid_branch(theme.get("storyType"), theme.get("branch"))


def branch_lines(request: ThemeDraftRequest, t: StoryType) -> list[str]:
    """씨앗 종류의 갈래 줄(#782 기준안 — 확인 전): 정한 갈래면 그 규칙·마무리 장면 줄, 갈래가 있는
    종류의 예전 초안이면 목록과 갈래별 규칙을 주고 모델이 고르게, 갈래가 없으면 null."""
    decided, branch = seed_branch(request)
    if branch is not None:
        return [
            f"branch: {branch}(갈래, 주제가 정함, 그대로 쓴다)\n"
            + branch_rule(t.code, branch)
            + branch_outro(t.code, branch)
        ]
    if decided:
        return ["branch: null(이 테마는 갈래를 쓰지 않는다)"]
    options = STORY_BRANCHES[t.code]
    return [
        f"branch: 갈래를 {'·'.join(options)} 가운데 주제·대상에 맞는 하나로 골라 쓰고 고른 갈래 "
        "줄만 따른다(목록 밖 값은 코드가 null로 바꿈).\n"
        + "".join(branch_option(t.code, b) for b in options)
    ]


def story_type_lines(request: ThemeDraftRequest) -> list[str]:
    """줄거리 종류 규칙 묶음(#634). 씨앗이면 그 종류 하나, 관리자 자유 글·주제 없음이면 모두 주고
    모델이 고르게 한다(사람을 탓하는 주제여도 이 종류들 안에서). 갈래 줄(#782)은 종류 규칙 뒤에."""
    found = parse_topic(request.topic)
    if found:
        rules = type_rules(found)
        plan = candidate_plan_for(request) if found.facts is not None else None
        if plan and found.facts is not None:
            # 코드가 후보·정답을 정한 종류: 사실표 규칙의 '그 장소·이야기에 어울리는 4개를 고른다'를
            # '코드가 정한 이름을 그대로'로 갈아 끼움(두 문구가 함께 있으면 모델이 장소에 맞춰 바꿈)
            rules = rules.replace(found.facts.rule(), found.facts.rule(fixed=True))
        lines = [f"storyType: {found.code}(주제가 정함, 그대로 쓴다)", rules]
        if plan and found.facts is not None:
            flat = flat_features(found.facts, plan["candidates"])
            group = f", 범주 {plan['group']}" if plan.get("group") else ""
            # 후보끼리 값이 모두 같은 특징을 막는 코드 검사는 strict_facts 종류(소리 탐정)만
            flat_check = "(코드 검사 FACT_TABLE)" if found.strict_facts else ""
            lines.append(
                f"이번 테마 후보(코드가 정함{group}): candidates는 "
                f"{'·'.join(plan['candidates'])}, answer는 {plan['answer']}(그대로 쓴다, 코드 검사 "
                "SAME_KIND). 정답 이름은 엔딩 전 글에 쓰지 않는다."
                + (
                    f" 이 후보끼리 값이 모두 같은 특징({'·'.join(flat)})은 단서가 될 수 없어 "
                    f"features에 넣지 않는다{flat_check}."
                    if flat
                    else ""
                )
            )
        return [*lines, *branch_lines(request, found)]
    return [
        "줄거리 종류: 주제에 가장 맞는 종류 하나를 골라 storyType에 쓰고 그 종류 규칙만 따른다.",
        # #782 기준안(확인 전): 관리자 자유 글은 고른 종류의 갈래 목록에서 모델이 고름
        "branch(갈래): 고른 종류에 갈래 목록이 있으면 그 가운데 주제·대상에 맞는 하나를 쓰고 고른 "
        "갈래 줄만 따른다. 갈래 목록이 없는 종류는 null(목록 밖 값은 코드가 null로 바꿈).",
        *(type_rules(t) + free_branch_lines(t) for t in STORY_TYPES.values()),
    ]


def free_branch_lines(t: StoryType) -> str:
    """관리자 자유 글 줄거리 프롬프트의 그 종류 갈래 목록(#782 기준안). 갈래가 없는 종류는 빈 글."""
    options = STORY_BRANCHES.get(t.code)
    if not options:
        return ""
    return f"- branch(갈래) 목록: {'·'.join(options)}\n" + "".join(
        branch_option(t.code, b) for b in options
    )


def cut_roles(theme: Theme, key: str) -> tuple[str, str, str, str]:
    """그 줄거리 종류의 콘티 컷 역할(줄거리 규칙의 introCuts·outroCuts 순서와 같게). 칸 하나만 고쳐
    쓸 때 역할을 잃지 않게."""
    t = story_type(theme)
    return t.intro_cuts if key == "introCuts" else t.outro_cuts


FIX_SYSTEM = (
    "너는 초등학생용 주간 테마 글에서 검사에 걸린 칸 몇 개만 고쳐 쓰는 편집자다.\n"
    "- 받은 칸만 다시 쓴다. 다른 칸과 이야기 속 사실은 바꾸지 않는다.\n"
    "- 칸마다 적힌 검사 사유와 지킬 점을 고친다. 뜻은 그대로 두고 말을 줄이거나 바꾼다.\n"
    "- 글자 수는 공백·문장부호를 포함해 센다. 상한보다 3~5자 짧게 쓴다.\n"
    "- 출력: fixes에 받은 칸마다 {path, text} 하나씩. path는 받은 그대로 쓴다."
)


# 단서 칸 고쳐 쓰기: 증거 종류(evidence.kind)는 바꾸지 않고 문장을 그 종류에 맞춤
# (코드 검사 CLUE_EVIDENCE). 배정과 종류가 달랐으면 fix_theme이 먼저 종류를 배정대로 바꿈(#535)
RECORD_LIST = "사진·영상·녹음·기록·일지·메모"
EVIDENCE_CLUE_RULE = {
    "RECORD": f"증거 종류가 기록이라 {RECORD_LIST} 중 하나를 말한다.",
    "SIGHTING": f"증거 종류가 목격이라 본 것으로 쓰고 {RECORD_LIST}는 말하지 않는다.",
    "TRACE": f"증거 종류가 흔적이라 남은 흔적으로 쓰고 {RECORD_LIST}는 말하지 않는다.",
}
# 증거 발견 줄이 그 종류에서 찾았다고 말할 것(PLAN_SYSTEM discovery 규칙과 같음)
EVIDENCE_FOUND = {
    "TRACE": "흔적이 남은 물건·자리",
    "SIGHTING": "그때 대상을 본 사람",
    "RECORD": "그때를 담은 기록",
}


def evidence_rules(theme: Theme, day: dict, key: str) -> list[str]:
    """그날 증거 종류·배정 매체에 맞추는 지킬 점(단서·증거 발견 줄·수사 연결 문장)."""
    kind = str((day.get("evidence") or {}).get("kind") or "")
    medium = (plan_slot(theme, day["day"]) or {}).get("medium")
    use_medium = f"기록 매체 '{medium}' 낱말을 그대로 쓴다." if medium and kind == "RECORD" else ""
    if key == "clue":
        owner = (
            f"누구의 흔적인지 찾는 대상 낱말({'·'.join(target_words(theme))} 중 하나)을 꼭 넣는다."
            # #782 설계 v8: 탈것 사건 단서 날은 온 사람 낱말만(바퀴는 후보를 가름)
            if kind == "TRACE" and not (is_story(day.get("condition") or {}) and clue_person(theme))
            else f"대상 낱말({'·'.join(target_words(theme))} 중 하나)을 넣어 그 대상의 증거임을 "
            "밝힌다(장소 모습만 말하지 않음)."
            if story_type(theme).owner_all
            else ""
        )
        return [EVIDENCE_CLUE_RULE.get(kind, ""), use_medium, owner]
    found = f"{EVIDENCE_KO.get(kind, kind)}({kind}) 증거, 곧 {EVIDENCE_FOUND.get(kind, '증거')}"
    if key == "discovery":
        # #782 미션 방식: 부탁 날 증거는 문제 뒤 단서가 나오는 곳(줄거리 discovery 규칙과 같음)
        how = (
            f"돕는 사람({day.get('helper') or ''})이 본 것·가진 것으로"
            if mission_way(day) == ASK
            # #782 설계 v8: 수사 날도 돕는 사람이 가진 증거(줄거리 discovery 규칙과 같음)
            else f"돕는 사람({day.get('helper') or ''})이 가진 증거로"
        )
        return [f"그날 {found}를 {how} 한 줄만 쓴다.", use_medium]
    # #782 설계 v8: 부탁 날 연결 문장은 무엇을 알려 줄지 말하지 않음(EVIDENCE_EARLY와 같게)
    return (
        [f"그날 증거 발견 줄이 찾은 {found}를 가리켜 말한다."]
        if mission_way(day) == INVESTIGATE
        else []
    )


# 사건 단서 날(#782 테마 짜임) 다른 칸의 고쳐 쓰기 규칙: 그날 단서 결론 낱말·특징이 없으므로
STORY_DAY_HIDE = (
    "그날은 사건 단서 날이라 그날 단서 내용(사건이 어떻게 벌어졌는지)을 미리 말하지 않는다(단서는 "
    "문제 뒤에 보여 줌)."
)


def child_known_rule(theme: Theme) -> str:
    """시작 이야기·오늘 온 까닭 고쳐 쓰기의 '아이가 이미 아는 것' 규칙(#782 설계 v10, 코드 검사
    INTRO_HEARD·INTRO_FOUND와 같음). 해당 없는 종류는 빈 글."""
    t, name = story_type(theme), first_speaker(theme)
    if t.code == "SOUND":
        return (
            f"{name}은(는) 소리를 직접 듣지 않았고 소리에 깨지도 않았다: 이웃·가족에게 전해 들은 "
            "것으로 쓴다('전해 들었어'·'이야기를 들었어'는 됨, 코드 검사 INTRO_HEARD)."
        )
    if t.code == "ORIGIN" and theme_branch(theme) != "동물":
        return (
            f"{name}은(는) 그 물건을 줍거나 받아 들지 않았다: 다른 사람(관리실 직원·선생님)이 주워 "
            "맡겼고 아이는 이야기로만 안다(코드 검사 INTRO_FOUND)."
        )
    return ""


def fix_rules(theme: Theme, path: str) -> list[str]:
    """칸 종류별로 줄거리 프롬프트와 같은 지킬 점(검사를 다시 통과하도록)."""
    # 동물 주인공 가족은 머리 낱말까지(#634 ③, 코드 검사 CANDIDATE_NAME과 같은 낱말)
    words = (
        candidate_words(theme)
        if story_type(theme).hide_candidates
        else theme.get("candidates") or []
    )
    names = f"후보 이름({', '.join(words)})은 쓰지 않는다."
    head, _, key = path.partition(".")
    if key == "sceneNote":  # CLUE_EARLY sceneNote(#535): 단서 결론 낱말만 빼고 장면은 그대로
        cond = theme_day(theme, head).get("condition") or {}
        return [
            f"그날 단서 결론 낱말 {cond.get('allowed') or []}과 증거가 남은 자리의 "
            f"'{cond.get('feature') or ''}'를 쓰지 않는다(단서는 문제 뒤에 보여 줌)."
            if not is_story(cond)
            else STORY_DAY_HIDE,
            # #782 설계 v10: 돕는 사람을 바꾸는 사유(HELPER_SAME)면 그 사람으로(#782 설계 v11: 돕는
            # 사람 검토 review_helpers의 HELPER_FORCED·HELPER_FALLBACK은 뺌)
            # #782 설계 v13: 글 검토 HELPER_FIT(돕는 사람의 일이 장소와 동떨어짐)도 사람·일을 바꿈
            "누가 어디서 무엇을 하는지는 그대로 둔다(검사 사유가 돕는 사람이나 그 일을 바꾸라고 "
            "하면(HELPER_SAME·HELPER_FIT) 새 돕는 사람이 새 일을 하는 모습으로).",
            # #782 미션 방식 EVIDENCE_EARLY: 부탁 날 증거는 문제 뒤 단서로 나옴
            f"부탁 날이라 흔적·자국·증거를 쓰지 않고 돕는 사람"
            f"({theme_day(theme, head).get('helper') or ''})이 그 일을 하는 모습으로 쓴다."
            if mission_way(theme_day(theme, head)) != INVESTIGATE
            else "",
            names,
            "정답 이름은 쓰지 않는다.",
        ]
    if key == "missionMaterial":  # #782 미션 지문(줄거리 프롬프트 규칙과 같음, 미션 방식대로)
        cond = theme_day(theme, head).get("condition") or {}
        investigate = mission_way(theme_day(theme, head)) == INVESTIGATE
        return [
            "돕는 사람이 가진 증거의 내용(본 사람의 말, 기록에 적힌 글·수)을 그때 찾는 대상·사건에 "
            "관한 내용으로 쓰고, 단서의 그때와 같은 때의 내용만 쓴다(수사를 마친 뒤의 회고 금지)."
            + (
                " 그때 직접 보거나 듣거나 그때 적은 사람의 증언 하나로, 직접 본 것임이 드러나게 "
                "쓴다(#782 설계 v13)."
                if testimony_day(theme_day(theme, head))
                else ""
            )
            if investigate
            else "돕는 사람의 그 일(오늘 할 일)의 자료(안내문·쪽지·지은 시·후기·셀 수)를 쓴다. "
            "사건 증거인 척 지어내지 않고, 돕는 사람 자신의 기록(내 메모·일지·사진)으로 쓰지 "
            "않는다(그 기록은 미션 뒤 단서, #782 설계 v9).",
            "수가 있으면 그 학년이 배운 셈으로 풀리게 쓴다(초3은 분수를 더하거나 빼지 않음).",
            "그날 활동을 할 수 있는 분량은 그대로 둔다. 수가 있으면 문제를 푸는 데 필요한 조건을 "
            "빠짐없이 서로 어긋나지 않게 쓴다.",
            # #782 설계 v13: 수사 날 증언에는 그날 단서 내용이 들어감(단서는 따져서 확실해진
            # 그 내용)
            (
                f"증언에 그날 단서 내용(단서가 말하는 값 낱말 {clue_says(theme_day(theme, head))}, "
                f"단서와 같은 꼴, 단서: {theme_day(theme, head).get('clue') or ''})을 그대로 넣는다"
                "(단서는 따져서 확실해진 그 증언 내용, 단서도 함께 고쳐 쓰면 고친 단서와 같은 "
                "내용)."
                if not is_story(cond)
                else "증언에 그날 사건 단서 내용(사건이 어떻게 벌어졌는지, 단서: "
                f"{theme_day(theme, head).get('clue') or ''})을 넣는다(단서는 따져서 확실해진 그 "
                "증언 내용)."
            )
            if testimony_day(theme_day(theme, head))
            else f"그날 단서 결론 낱말 {cond.get('allowed') or []}과 특징 "
            f"'{cond.get('feature') or ''}'에 대한 말을 쓰지 않는다(단서는 문제 뒤에 보여 줌)."
            if not is_story(cond)
            else STORY_DAY_HIDE,
            names,
            "정답 이름과 지금 대상이 있는 곳은 쓰지 않는다.",
        ]
    if key == "helper":  # #782 미션 방식 HELPER_SAME: 요일마다 다른, 등장인물이 아닌 그날 사람
        others = [
            str(d.get("helper") or "")
            for d in theme.get("days") or []
            if d.get("day") != head and d.get("helper")
        ]
        people = [str(c.get("name") or "") for c in theme.get("characters") or []]
        work = frame_of(theme, head).get("work") or ""
        return [
            # #782 설계 v10: 국어 부탁 날은 배정 호칭 대신 그날 성취기준의 일을 늘 하는 사람
            f"그날 성취기준의 일{f'({work})' if work else ''}을 늘 하는 사람 호칭 하나(12자 "
            "이내). 그 사람의 일이 그날 "
            "장소·활동과 맞고 아이 답이 그 일에 쓰이게(helperUse) 정한다."
            if helper_use_day(theme, theme_day(theme, head))
            else f"그날 장소({theme_day(theme, head).get('place') or ''})에 어울리는 사람 호칭 "
            "하나(12자 이내).",
            f"다른 요일 돕는 사람({', '.join(others)})·등장인물({', '.join(people)})·찾는 대상이 "
            "아닌 새 사람으로 쓴다.",
            names,
        ]
    if key == "helperUse":  # #782 설계 v10: 국어 부탁 날 아이 답의 쓰임(줄거리 프롬프트와 같음)
        d = theme_day(theme, head)
        return [
            f"아이가 쓴 답이 돕는 사람({d.get('helper') or ''})의 일에 실제로 쓰이는 곳을 그 "
            "사람의 말 한 줄로(40자 이내, 예: '책 추천 카드에 붙일게'). 그날 할 일"
            f"({d.get('missionHook') or ''})과 같은 일을 가리킨다.",
            "쓰이는 곳 낱말(두 글자 이상)을 '~에·~에다·~으로·~로' 바로 앞에 쓴다(미션 문제 글이 이 "
            "낱말을 씀, 코드 검사 USE_MISSING).",
            names,
            "정답 이름은 쓰지 않는다.",
        ]
    if key == "dayStep":  # #782 테마 짜임: 오늘 온 까닭(줄거리 프롬프트 dayStep 규칙과 같음)
        cond = theme_day(theme, head).get("condition") or {}
        days = theme.get("days") or []
        names_order = [d.get("day") for d in days]
        before = [
            a
            for d in days[: names_order.index(head)]
            for a in (d.get("condition") or {}).get("allowed") or []
        ]
        today = cond.get("allowed") or []
        return [
            "월요일은 시작 이야기에서 이어(사건 직후 현장부터, '어제'라고 쓰지 않음 — 시작 "
            "이야기가 밤·전날 일이면 됨), 화~금은 오늘 장소·그곳 사람이 사건과 어떻게 닿는지에서 "
            "오늘 여기 온 까닭을 한 줄로 쓴다(예: '고양이가 빵집 앞을 지났을지 몰라 와 봤어').",
            # #782 설계 v7: 어제 일은 들은 것만, 부탁·소개·지시·건넴·오늘 할 일 금지, 자기 이름 금지
            "어제 일은 넣지 않아도 되고 넣으면 들은 것만 쓴다. 어제 돕는 사람이 "
            "부탁·소개·지시하거나 자료를 건넸다고 쓰지 않고 오늘 할 일(부탁)도 쓰지 않는다(코드 "
            "검사 DAY_STEP_MADE).",
            f"대화 첫 줄로 {first_speaker(theme)}이(가) 하는 말이라 '나'의 말로 쓰고 그 이름은 "
            "쓰지 않는다(코드 검사 SELF_NAME).",
            child_known_rule(theme),  # #782 설계 v10 5절
            f"앞 요일 단서 결과 낱말 {list(dict.fromkeys(before))}은 쓰지 않는다(어제 일은 들은 "
            "것만)."
            if before
            else "",
            f"오늘 단서 결론 낱말 {today}은 쓰지 않는다." if today else STORY_DAY_HIDE,
            names,
            "정답 이름은 쓰지 않는다.",
        ]
    if key in ("clue", "discovery", "missionHook"):
        day = theme_day(theme, head)
        cond = day.get("condition") or {}
        allowed = cond.get("allowed") or []
        if key == "clue" and is_story(cond):  # #782 테마 짜임: 사건 단서
            return [
                "사건 단서다: 그날 찾은 증거에서 사건이 어떻게 벌어졌는지(찾는 대상이 지나간 "
                "길·한 일·남긴 것) 새 사실을 한 줄로 쓴다(예: '부스러기가 창틀 쪽으로 이어져 "
                "있었어!'). 앞 요일 단서를 되풀이하지 않는다.",
                "후보 이름과 후보 특징 표의 값 낱말은 쓰지 않는다(코드 검사 STORY_VALUE). 남은 "
                "어떤 후보와도 어긋나지 않게 쓴다(상식으로 한 후보를 빼거나 가리키는 말 금지 — "
                "예: 생쥐가 후보에 남았는데 '높은 나무 위로 갔다').",
                *evidence_rules(theme, day, "clue"),
                way_clue_rule(theme, day),
                names,
            ]
        if key == "clue":
            values = (feature_table(theme)[0].get(cond.get("feature") or "") or {}).values()
            others = sorted({v for v in values if v not in allowed})
            excluded = cond.get("excluded") or []
            return [
                f"특징 '{cond.get('feature')}'이 무엇에 대한 것인지 밝히고, 빠지는 값 {excluded}를 "
                f"'…는 아니었어'처럼 부정으로 쓴다(허용 값 {allowed}를 늘어놓지 않음)."
                if excluded
                else f"특징 '{cond.get('feature')}'이 무엇에 대한 것인지 밝히고 값 낱말 "
                f"{allowed}를 그대로 쓴다('A나 B'로 늘어놓지 않음).",
                *evidence_rules(theme, day, "clue"),
                f"허용 밖 값 낱말 {[o for o in others if o not in excluded]}는 쓰지 않는다."
                if [o for o in others if o not in excluded]
                else "",
                "후보를 빼는 단서라 단정해서 쓴다('~수도 있다·~것 같다·~듯' 금지)."
                if cond.get("kind") == "RULE"
                else "",
                way_clue_rule(theme, day),
                "말한 사람 이름을 붙이지 않고, 새 사실을 더하지 않는다.",
                names,
                "어떤 시각(3시·정오 등)도 쓰지 않는다(그때가 정답, '그 일을 할 때'처럼)."
                if story_type(theme).hide_times
                else "",
                # #634 ④⑤ CLUE_OWNER: 탈것은 온 사람(탈것을 봤다고 쓰지 않음), 소리는 '소리' 낱말
                (
                    f"'{person}' 낱말을 넣어 그 소리의 증거임을 밝힌다."
                    + (
                        " 소리가 난 자리로 쓰고('내가 들었는데 소리가 ○○에서 났어') 듣는 사람이 "
                        "있던 곳으로 "
                        "쓰지 않는다."
                        if cond.get("feature") == "소리 난 곳"
                        else ""
                    )
                    if story_type(theme).clue_word
                    else f"온 사람('{person}')을 넣어 그 사람이 탄 탈것의 증거임을 밝히고, 탈것을 "
                    "봤다고 쓰지 않는다(들고 온 것을 봤거나 소리를 들은 것으로)."
                )
                if (person := clue_person(theme))
                else "",
            ]
        if key == "discovery":
            return [
                *evidence_rules(theme, day, "discovery"),
                f"단서 결론 낱말 {allowed}은 쓰지 않는다." if allowed else STORY_DAY_HIDE,
                names,
            ]
        return [
            # #782 테마 짜임: 줄거리 프롬프트 missionHook 규칙과 같음(미션 방식대로)
            "돕는 사람이 가진 증거를 같이 읽고 따져 보자는 말 한 줄(그 증거와 그날 활동을 함께 "
            "말함)."
            if mission_way(day) == INVESTIGATE
            else "돕는 사람의 부탁 한 줄. 그 일과 그날 활동을 함께 말하고, 무엇을 알려 줄지는 "
            "말하지 않는다(흔적·자국 낱말 금지, 코드 검사 EVIDENCE_EARLY). 지금 글이 가리키는 "
            "일이 있으면 그대로 둔다. 수학이면 구한 값을 그 사람이 어디에 쓰는지 함께 말하고, "
            "그 학년이 배운 셈만 시킨다(#782 설계 v9).",
            HOOK_ACT_RULE,
            *evidence_rules(theme, day, "missionHook"),
            "'<증거>를 풀려면 <배울 것>이 필요해'처럼 증거와 상관없는 활동이 증거를 풀어 준다고 "
            "쓰지 않는다.",
            # #782 미션 방식: 돕는 사람 자신의 생각을 묻지 않음(HOOK_SELF)
            "돕는 사람 자신의 생각·마음을 추측하게 하지 않는다('내 생각을 추론해 볼래?' 금지).",
            # 줄거리 프롬프트 missionHook 규칙과 같음. 칸 고쳐 쓰기에 빠져 있어 '분수 계산으로
            # 발자국 길이를 알아낸다'처럼 문제 결과가 단서가 되는 문장이 나왔음(글 검토
            # CLUE_LOGIC, 실측 2026-11-15 닫기 2차)
            f"그날 단서 특징('{cond.get('feature') or ''}')의 값이나 증거가 뜻하는 것을 그날 "
            "문제의 계산·답으로 알아낸다고 쓰지 않는다('~로 알아볼까?'·'~하면 알 수 있어' 금지).",
            names,
        ]
    if key in ("scene", "action"):
        t = story_type(theme)
        cut = ("OUTRO" if head.startswith("outroCuts") else "INTRO", int(head[-1]))
        return [
            f"이 컷의 역할을 지킨다: {cut_roles(theme, head[:-1])[int(head[-1]) - 1]}.",
            "scene은 컷 끝에 보이는 모습(누가 어디서) 한 문장, action은 동작 하나를 한 문장으로, "
            "지금 글 길이와 비슷하게 쓴다. 같은 말을 되풀이하지 않는다.",
            "뭉치는 제자리에서 작게 통통 튀기·고개 갸웃·몸 살짝 흔들기·표정 바꾸기만 한다. 손짓·"
            "건네기·안기·뛰기처럼 손이나 팔다리를 쓰는 동작은 사람이 한다.",
            "누구도 화면 쪽으로 다가오거나 화면 밖으로 나가지 않는다. 인물·장소는 그대로 둔다.",
            # #765 CUT_TARGET: 컷 그림에 나오지 않는 것은 이름도, 없다는 말도 쓰지 않음
            f"이 컷 그림에는 찾는 대상('{theme.get('target') or ''}')이 나오지 않는다: 대상 이름을 "
            "쓰지 않고 '보이지 않는다'처럼 없다는 말도 쓰지 않는다. 없어진 것은 빈손·빈자리처럼 "
            "보이는 것으로 쓴다."
            if cut in t.hidden_target_cuts
            else "",
            f"이 컷 그림에는 후보가 나오지 않는다: 정답을 포함해 후보 이름"
            f"({', '.join(candidate_words(theme))})을 쓰지 않는다."
            if cut in t.hidden_candidate_cuts
            else "종료 콘티라 정답 이름을 써도 된다."
            if cut[0] == "OUTRO"
            else "정답 이름·정답 장소를 쓰지 않는다.",
        ]
    if key == "caption":
        if head.startswith("outroCuts"):
            return ["영상 위에 띄우는 짧은 문구. 종료 콘티라 정답 이름을 써도 된다."]
        return ["영상 위에 띄우는 짧은 문구. 정답 이름·정답 장소를 쓰지 않는다."]
    if path == "incident":  # #634 ③ 내부 칸이 비었을 때
        return [
            f"이번 주 사건 물건·일 한 줄(찾는 것: {theme.get('target') or ''}). 엔딩 전에 보여도 "
            "되는 사실이고 그 주 문제의 소재가 된다(예: '떡 접시가 비어 있고 떡 부스러기가 "
            "흩어짐').",
            names,
        ]
    if path == "answerLook":
        return [
            f"정답 {theme.get('answer') or ''}의 겉모습 한 줄(종료 그림·영상에서 같은 "
            "모습으로 그림). 특징 표의 정답 값과 맞게 쓴다."
        ]
    if path == "outro":  # 마무리 장면만(다섯 단서 정리는 코드가 앞에 붙임, #535 7차)
        return [
            f"종료 이야기의 마무리 장면만 쓴다: {story_type(theme).outro_rule} "
            "요일 이름·빠진 후보 정리는 쓰지 않는다(코드가 앞에 붙임). 정답 이름은 써도 된다.",
            # #782 갈래 마무리 장면(줄거리 프롬프트와 같은 줄). 예전 저장본처럼 갈래가 없으면 빼기
            branch_outro(story_type(theme).code, theme_branch(theme)).strip("- \n"),
            # #634 ④⑤ OUTRO_ANSWER: 마무리 장면은 정답 그대로
            f"정답 '{theme.get('answer') or ''}' 그대로 쓰고 다른 후보는 쓰지 않는다."
            if story_type(theme).outro_check
            else "",
        ]
    t = story_type(theme)
    extra = []
    if path == "intro" and t.intro_notes:  # #634 ④ 마을 규칙은 코드가 끝에 붙임
        extra.append(f"끝의 규칙 문장('{t.intro_notes[0]}')은 코드가 붙이므로 쓰지 않는다.")
    if path == "intro" and (known := child_known_rule(theme)):  # #782 설계 v10 2.1
        extra.append(known)
    if t.hide_times:  # #634 ④ 시간 탐정: TIME_WORD
        extra.append("어떤 시각(3시·오전 9시·정오 등)도 쓰지 않는다('그 일을 할 때'·'아침에'처럼).")
    if t.facts is not None:  # #634 CANDIDATE_NAME: 엔딩 전 글
        return [
            f"{names} 후보를 가리킬 때는 '그 {t.facts.name}'처럼 쓴다.",
            "정답 이름은 종료 이야기(outro)에만 쓴다.",
            *extra,
        ]
    return ["정답 이름은 종료 이야기(outro)에만 쓴다.", *extra]


NO_HOOK_REASON = "없음(문제가 다루는 자료 이름이 들어가게 다듬기)"


def hook_fix_user(theme: Theme, days: dict[str, tuple[str, list[str]]]) -> str:
    """미션을 만든 뒤 수사 연결 문장을 그날 문제 소재 낱말이 들어가게 고쳐 쓰는 요청.

    days: {요일: (그날 미션 질문, STORY_LINK 사유. 경고가 없으면 빈 목록)}. 요일 노드가 미션이
    통과한 직후 그 요일 하나로 부른다(fix_hook). 미션은 다시 만들지 않음(#535 닫기).
    """
    words = (
        candidate_words(theme)
        if story_type(theme).hide_candidates
        else theme.get("candidates") or []
    )
    cands = ", ".join(words)
    lines = [
        f"테마: {theme.get('title')} / 찾는 대상: {theme.get('target')}",
        "",
        "고칠 칸(수사 연결 문장만, 대화 모델이 문제 앞 대화의 마지막 말로 풀어 씀):",
    ]
    for day, (question, reasons) in days.items():
        d = theme_day(theme, day)
        lines += [
            f"- path: {day}.missionHook",
            f"  지금 글({len(d.get('missionHook') or '')}자): {d.get('missionHook')}",
            f"  상한: 공백 포함 {text_max(day + '.missionHook')}자",
            f"  오늘 장소: {d.get('place')}",
            f"  미션 방식: {WAY_KO[mission_way(d)]}, 돕는 사람: {d.get('helper') or '없음'}",
            f"  오늘 단서가 나오는 증거(대화에 미리 말하지 않음): {d.get('discovery')}",
            f"  오늘 문제(그대로 둠): {question}",
            f"  검사 사유: {' / '.join(reasons) or NO_HOOK_REASON}",
            # #782 테마 짜임: 미션 방식대로 그 사람의 부탁·증거를 같이 보자는 말
            "  지킬 점: 오늘 문제가 실제로 다루는 일·자료를 사실대로 말한다(부탁 날은 돕는 사람의 "
            "부탁, 수사 날은 증거를 같이 읽고 따져 보자는 말). 오늘 "
            "문제에 나온 자료·일 이름을 하나 이상 그대로 쓴다(문제에 없는 다른 것으로 바꾸지 "
            "않음). "
            "공백 포함 32자 안팎.",
            *[f"  지킬 점: {r}" for r in fix_rules(theme, day + ".missionHook") if r],
            f"  지킬 점: 후보 이름({cands})·정답과 그날 단서 결론은 쓰지 않는다.",
            "  지킬 점: 오늘 문제의 답(고를 자료·방법, 계산 결과, 예시 답 내용)은 쓰지 "
            "않는다. 문제가 여러 자료·방법 가운데 고르게 하면 고를 것을 가리키지 않고 문제 전체가 "
            "다루는 소재 낱말만 쓴다.",
        ]
    return "\n".join(lines)


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
            f"  상한: 공백 포함 {text_max(path, theme)}자",
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
    # #782 설계 v13: 수사 날 지문 증언 속 그날 단서 내용은 후보 특징 금지 줄의 예외(지문은
    # 그대로 씀)
    TESTIMONY_KEEP = (
        " 다만 오늘 지문 증언 속 그날 단서 내용은 그대로 둔다(수사 날, #782 설계 v13)."
        if testimony_day(theme_day(theme, day))
        else ""
    )
    """미션 초안 프롬프트 뒤에 붙이는 테마 이야기 조각(생각 열기 개수·찾는 대상 포함, 정답은 주지
    않음).

    단서는 학생이 그날 미션을 마친 뒤 보여 주므로 그날 단서도 앞 요일 단서 목록도 넣지 않고(학생이
    아직 못 얻었을 수 있음), 그날 찾은 증거와 증거에서 오늘 할 일을 준다(사용자 결정 2026-11-11).
    """
    d = next(x for x in theme["days"] if x["day"] == day)
    names = ", ".join(c["name"] for c in theme["characters"])
    helper, way = str(d.get("helper") or "").strip(), mission_way(d)
    use, words = day_use(theme, day)  # #782 설계 v10 국어 부탁 날 아이 답의 쓰임
    animal = story_type(theme).animal
    hide = story_type(theme).hide_candidates
    avoid_names = (
        [*candidate_words(theme), *secret_values(theme)] if hide else theme.get("candidates") or []
    )
    lines = [
        "",
        "테마 이야기 조각(이 미션은 주간 테마의 한 장면이다):",
        f"- 테마: {theme['title']} / {theme['world']}",
        f"- 등장인물: 뭉치(솜뭉치 모양의 주인공 캐릭터, 사건을 해결하러 온 해결사), {names}",
        f"- 오늘({DAY_KO[day]}요일) 장소: {d['place']}",
        f"- 오늘 장면: {d['sceneNote']}",
        f"- 오늘 돕는 사람: {helper}" if helper else "",
        # #782 설계 v12: 9차 new3 문제가 '가게 주인이 그때 본 일을 설명하고'인데 그 말이 없음
        f"- 오늘 찾은 증거(문제 앞 대화에서 보여 줌, 문제에는 지문만 보여 주고 '○○가 본 일을 "
        f"설명하고'처럼 지문에 없는 증언을 준다고 쓰지 않음 — 코드 검사 MISSION_TESTIMONY): "
        f"{d['discovery']}"
        if way == INVESTIGATE
        else "",
        f"- 오늘 할 일(돕는 사람의 부탁·증거를 같이 보자는 말): {d['missionHook']}",
        # #782: 줄거리 단계가 정한 그날 증거 내용(내부 칸, 예전 저장본에는 없음)
        f"- 오늘 문제의 지문(줄거리가 정한 그날 일의 자료): {d['missionMaterial']}"
        if d.get("missionMaterial")
        else "",
        # #782 실측 40건: 수학 지문의 수가 그대로 최종 답이 돼 LEAK ANSWER_KEY가 되풀이됨
        f"- 지문에 나온 수(최종 답이 되면 안 됨, 이 수로 계산해 새 값을 구함): "
        f"{', '.join(material_numbers(d.get('missionMaterial')))}"
        if material_numbers(d.get("missionMaterial"))
        else "",
        "테마 규칙:",
        "- 오늘 할 일은 문제 앞 대화가 이미 말하므로 부탁하는 말을 question에 되풀이하지 "
        "않는다. 문제 글에 준 자료로 성취기준의 행동을 학생이 직접 하게 한다.",
        # #782 테마 짜임(사용자 판단 2026-11-19 "예시 답이 너무 어려워 초5가 풀 만한 게 아님")
        f"- 제목·문제·안내·생각 열기 질문·예시 답은 초{grade} 아이가 읽고 쓸 만한 쉬운 말로 쓴다"
        "(어려운 한자어·'자료'처럼 어른스러운 낱말은 풀어 쓰거나 증거 이름을 그대로). 서술·논술 "
        f"예시 답은 {EXAMPLE_SENTENCES[grade]}문장 안으로 짧게 쓰되 질문이 묻는 것은 모두 담는다"
        "(코드 검사 EXAMPLE_LONG). 그래서 질문이 묻는 항목은 "
        f"{EXAMPLE_SENTENCES[grade]}개 이하로 묶는다(논술은 주장·까닭 둘·반대 의견에 답하기를 "
        "한 문장씩, #782 설계 v8).",
        # #782 실측 40건: 수학 지문의 수 하나를 고르는 문제로 만들어 LEAK ANSWER_KEY로 3건 실패
        "- '오늘 문제의 지문'이 있으면 그 글을 question 안에 그대로 넣고(낱말을 바꾸지 않음, 뜻을 "
        "해치지 않는 조사·문장부호만) 그 지문으로 그날 활동을 하게 한다. 지문에 없는 사건 사실을 "
        "더하지 않는다. 지문에 수가 있으면 그 수는 계산 재료로 쓰고, 최종 답은 그 수로 계산해 새로 "
        "나오는 값(합·차·몇 배 등)이 되게 한다. 지문의 수 가운데 하나를 고르는 문제로 만들지 않는다"
        "(정답 수가 문제 글에 보이면 유출 검사 LEAK에 걸림)."
        if d.get("missionMaterial")
        else "",
        "- 문제는 이 장소와 장면에서 뭉치와 등장인물이 겪는 일로 쓰고, 이 글만 읽고 풀 수 있게 "
        "한다. 관찰·비교할 내용"
        "(사진·그림 속 모습, 수, 생김새)은 question 글에 직접 쓴다. 그림에만 있는 정보로 풀게 "
        "하지 않는다.",
        "- 사진·녹음·그림·영상·지도·활동지를 보거나 듣게 하려면 그 내용을 question 글에 적는다. "
        "내용을 적지 않은 자료를 살피라고 하지 않는다.",
        # 실측 2026-11-16 8차 미션 검토 MATERIAL: 문제 소재를 오늘 증거에서 가져오면서 증거의
        # 모습은 단서라 못 적어 "소개할 자국의 모습이 문제에 없다"가 되풀이됨(두 규칙의 충돌)
        "- 오늘 찾은 증거(흔적·기록·목격)를 문제 소재로 쓸 때 그 증거의 모습·내용을 소개·설명·"
        "묘사하게 하지 않는다(모습은 문제를 마친 뒤 보여 주는 단서라 question에 적을 수 없음). "
        "대신 그 증거를 둘러싼 다른 자료(인물이 한 말, 기록 글의 다른 부분)를 question에 직접 "
        "적고 그것으로 성취기준 행동을 하게 한다."
        # #782 미션 방식: 부탁 날은 증거를 문제 전에 주지 않아 이 규칙이 필요 없음
        if way == INVESTIGATE and not testimony_day(d)
        # #782 설계 v13: 지문이 그때 직접 본 사람의 증언 하나(그날 단서 내용이 들어 있음). v10의
        # 두 말 견주기는 예시 답이 길어져(8차 6 → 19) 뺌
        else "- 오늘 지문은 그때 직접 보거나 듣거나 그때 적은 사람의 증언이다. 문제는 그 증언이 "
        "믿을 만한지(사실·의견 구별이면 본 사실과 짐작)와 그 까닭(직접 봤는지·그때 적었는지 등)을 "
        "따지게 한다. 예시 답은 증언 속 직접 본 사실을 믿을 만하다고 결론 낸다(짐작·전해 들은 "
        "부분은 덜 믿을 만하다고 구별해도 됨). 직접 본 사실을 믿기 어렵다거나 알 수 없다고 결론 "
        "내지 않는다(단서는 따져서 확실해진 그 사실이라 어긋남, 미션 검토 EXAMPLE_COMPLETE). 예시 "
        "답이 그 증언 내용을 되풀이해도 되지만 그것이 어느 후보·정답을 가리키는지는 쓰지 않는다. "
        "증언에 없는 사건 사실은 더하지 않는다."
        if testimony_day(d)
        else "",
        "- " + TEXT_ONLY,
        # #782 설계 v3: 국어 부탁 날은 아이 답이 돕는 사람의 일에 쓰이는 곳(USE_MISSING)
        # #782 설계 v10: 쓰임은 줄거리 helperUse(예전 저장본은 dayFrames 쓰임, day_use)
        f"- 문제 글에 아이 답의 쓰임을 밝힌다: 돕는 사람이 '{use}'라고 했으므로 그 뜻을 "
        f"question에 넣는다(낱말 {'·'.join(words)} 중 하나, 예: '네 글은 "
        f"{words[0]}에 실려', 코드 검사 USE_MISSING)."
        if words and way == ASK
        else "",
        # 8차 a: 초3 미션이 비율을 써 GRADE_MATH로 미션을 몇 번 다시 만들다 실패(hand3) — 코드 검사
        # 표(MATH_AHEAD)를 미션 지시문에도 그대로
        f"- 초{grade}에서 아직 배우지 않은 수학 개념은 문제·예시 답·확인 방법에 쓰지 않는다: "
        f"{'·'.join(name for name, _, learned in MATH_AHEAD if grade < learned)}(코드 검사 "
        "GRADE_MATH)."
        if any("수" in c for c in frame_of(theme, day).get("codes") or [])
        and any(grade < learned for _, _, learned in MATH_AHEAD)
        else "",
        # #782 설계 v9: 수학 부탁 날은 구한 값의 쓰임(6차 억지 13일 중 6일)
        "- 문제 글에 구한 값을 돕는 사람이 어디에 쓰는지 밝힌다(missionHook이 말한 쓰임, 예: '네가 "
        "구한 길이대로 리본을 잘라 상자에 묶을 거야')."
        if way == ASK and any("수" in c for c in frame_of(theme, day).get("codes") or [])
        else "",
        # #782 설계 v3: 그래프 성취기준은 글로 나타내기·해석하기(목요일 수학 실패 6건 중 3건)
        "- 그래프 성취기준이다. 그래프를 그리게 하지 않고 글로 한다: ① 표나 글로 준 자료의 "
        "눈금 한 칸을 몇으로 할지와 그 까닭 ② 각 막대(띠)가 몇 칸이 되는지 ③ 그래프로 알 "
        "수 "
        "있는 점 한 가지(가장 많은 것·적은 것과 그 차이 등)를 쓰게 한다(나타내기와 해석하기를 "
        "모두, "
        "미션 검토 STANDARD_FIT)."
        if set(frame_of(theme, day).get("codes") or []) & GRAPH_STANDARDS
        else "",
        "- 성취기준의 행동을 학생이 답 안에서 직접 하게 "
        "한다. '어떻게 쓸지·만들지·정리할지' 방법이나 "
        "계획을 묻지 않고, 글을 완성해 쓰기·분류한 결과 "
        "쓰기·정리한 내용 쓰기처럼 결과물을 쓰게 한다.",
        # 실측 2026-11-15 닫기 3c 글 검토 STANDARD_FIT 4번: 직접 어림·자기 점검·매체 윤리·비교
        # 방법 설명이 빠지거나 보고할 결과·발표할 내용 자료가 없음
        "- 성취기준 문장의 핵심 행동(직접 어림하기, 자기 글 점검하기, 매체 윤리 생각하기, 비교 "
        "방법 설명하기 등)을 질문이 요구하는 것에 넣고, 이야기 소재에 맞추느라 빼지 않는다. 그 "
        "행동에 쓸 자료(보고할 절차와 결과, 발표할 내용, 어림할 대상)는 question에 주되 학생이 할 "
        "몫(어림값·점검 결과)은 미리 주지 않는다.",
        # 실측 2026-11-15 닫기 3c 글 검토 ANSWER_HINT: 장면·대화의 '녹음 나누기 전 허락 구하기'가
        # 그대로 예시 답의 핵심 방법이 됨
        "- 오늘 장면에 이미 나온 행동·방법은 문제의 답(예시 답의 핵심)으로 삼지 않는다(학생이 문제 "
        "전에 장면과 대화로 봄).",
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
        "설명이 아님). " + EXAMPLE_RULES + " 대화·면담 대화를 쓰게 하면 "
        "예시 답에 인사부터 끝까지 두 사람의 말을 모두 완성해 쓴다. 다 쓴 뒤 질문이 요구한 것"
        "(쓰라는 것·조건·개수)을 하나씩 짚어 예시 답에 모두 들어 있는지 확인하고 빠진 것을 채운다.",
        # 실측 2026-11-15 닫기 2차: 면담 성취기준 문제가 면담할 말 준비만 시켜 글 검토
        # STANDARD_FIT 3번(다시 만든 문제는 면담 기록을 넣어 통과)
        "- 면담·인터뷰를 다루는 성취기준이면 question 안에 상대(등장인물)의 대답이 담긴 짧은 면담 "
        "기록을 넣고, 학생이 그 기록을 바탕으로 이어 묻기·정리하기 같은 면담 행동을 답 안에서 "
        "하게 한다(물을 말 준비만 시키지 않음). 대답에는 사건에 관한 새 사실을 넣지 않는다.",
        "- 질문이 어떤 글을 비교·점검·고쳐 쓰게 하면(예: 처음 쓴 글과 고친 글) 그 글 자체를 "
        "question 안에 짧게 넣는다. "
        "학생이 질문 글만 읽고 답할 수 있어야 한다.",
        "- 읽을 글·자료가 필요하면 question 안에 넣는다. guide에는 풀이 안내만 쓴다. 읽을 글에 "
        "나오는 낱말·문장은 "
        "forbiddenTerms에 넣지 않는다(학생이 그 글을 읽고 답함). forbiddenTerms에 수는 넣지 "
        "않는다(정답 수는 정답 키로 "
        "따로 검사함).",
        "- 큰 질문의 사건에 관한 새 사실(흔적·목격·기록 등)을 지어내지 않는다.",
        # #782 설계 v13: 15차 치명 snd6b 수요일 '어젯밤 민박집 방에서 소리가 들렸지만'
        "- 사건이 일어난 때는 '그날 밤·그때'로 쓴다. '어젯밤·어제 저녁·그저께'처럼 오늘 기준 지난 "
        "때로 쓰지 않는다(사건은 월요일 전 일, 코드 검사 INCIDENT_TIME).",
        # #782 설계 v10(2.3): 7차 auto4b 금 '별빛 캠핑을 마친 네 마음'(시작은 '별 보기 모임 직전')
        f"- 시작 이야기의 앞으로 열릴 행사({'·'.join(events)})는 아직 열리지 않았다. 문제·예시 "
        "답에서 이미 열리거나 끝난 것처럼('~에서 본'·'~을 마친') 쓰지 않는다(코드 검사 "
        "EVENT_LATER)."
        if (events := future_events(theme))
        else "",
        # 마지막 확인 3차 글 검토 SAFETY: 아이가 강아지 간식을 강아지와 나눠 먹음
        "- 사람이 동물 먹이(사료·동물 간식)를 먹거나 동물에게 사람 음식을 먹이는 장면은 쓰지 "
        "않는다.",
        # 실측 2026-11-11: 단서는 회색 벽 앞 사진인데 미션이 사진 속 벽을 파란색으로 지어냄(글 검토
        # CLUE_LOGIC). 특징 값 낱말을 모두 막으면 성취기준 개념(도형 이름 등)을 못 써서 특징만 알림
        f"- 오늘 단서가 다루는 특징: '{(d.get('condition') or {}).get('feature') or ''}'. 사건 "
        "현장(오늘 장소·장소 후보·찾는 대상·찾은 증거)의 이 특징이 어떤지는 문제에 정해 쓰지 "
        "않는다(학생이 문제 뒤에 볼 단서와 어긋날 수 있음). 이 특징을 다른 자료·예로 다루는 것은 "
        "된다."
        # #782 설계 v13: 수사 날 지문 증언에는 이미 단서 내용이 있음
        + (
            " 지문의 증언에 이미 있는 내용은 그대로 둔다(지문 밖에서 새로 정하지 않음)."
            if testimony_day(d)
            else ""
        )
        if not is_story(d.get("condition") or {})
        # #782 테마 짜임: 사건 단서 날은 특징이 없고 사건이 어떻게 벌어졌는지가 단서
        else "- 오늘 단서는 사건 단서다(사건이 어떻게 벌어졌는지). 문제에서 사건이 어떻게 "
        "벌어졌는지를 새로 정해 쓰지 않는다(학생이 문제 뒤에 볼 단서와 어긋날 수 있음).",
        "- 풀이 문제의 최종 답은 계산해서 새로 구하는 "
        "값이다. 문제에 주어진 수 가운데 하나를 고르는 "
        "비교 문제로 만들지 않는다(정답 수가 문제 글에 보이면 유출 검사에 걸림).",
        (
            # #782 설계 v3: 선물·길·출처 찾기 물건은 관리실에 맡겨 둠
            f"- 맡겨 둔 대상: {theme.get('target') or ''}. 관리실에 맡겨 두어 문제에 이름은 나와도 "
            "되지만 등장인물이 들고 있거나 살펴보지 않는다. 그 대상의 단서 특징 값(색·무게·소리 "
            "등)은 문제에 정해 쓰지 않는다."
            if kept_target(theme)
            else f"- 손에 든 대상: {theme.get('target') or ''}. 처음부터 등장인물이 가지고 있어 "
            "문제에 곁에 있는 것으로 나와도 된다. 그 대상의 단서 특징 값(색·맛·무게·소리 등)은 "
            "문제에 정해 쓰지 않는다."
            if story_type(theme).target_in_hand
            # #634 ④⑤ 시간 탐정·소리 탐정: 그 일·그 소리는 알려진 사실, 모르는 것은 때·소리를 낸 것
            else f"- 밝힐 것: {theme.get('target') or ''}. {story_type(theme).target_note}. "
            "문제·안내·생각 열기 질문·예시 답에도 그대로 지킨다."
            if story_type(theme).target_note
            else f"- 찾는 대상: {theme.get('target') or ''}. 아직 찾지 못했으므로 문제에서 지금 "
            "보거나 만지거나 곁에 있는 것처럼 쓰지 않는다. 사진·영상·기록에 찍힌 지나간 때의 "
            "모습은 써도 된다(지금 있는 곳은 쓰지 않음)."
        ),
        f"- 쓰지 말 낱말(이번 주 {story_type(theme).candidate_kind} 후보 이름"
        f"{', 머리 낱말·정답의 표 값 포함' if hide else ''}): "
        f"{', '.join(avoid_names) or '없음'}. "
        "문제·안내·생각 열기 질문·예시 답에 쓰지 않는다.",
        "- 위 증거 발견 줄·수사 연결 문장의 낱말은 "
        "forbiddenTerms에 넣지 않는다(학생이 대화로 보는 줄).",
        "- 문제에 나오는 사람은 위 테마 등장인물만 쓴다(새 이름을 만들지 않는다).",
        "- 문제 첫머리를 매번 '장소에서 누가 …'로 시작하지 "
        "않는다. 대화·자료·물음 등으로 다양하게 연다.",
        f"- 생각 열기 질문(hints)은 정확히 {HINTS[grade]}개. question 글에 나온 장소·물건·자료를 "
        "가리켜 생각을 열게 쓰되 정답·풀이는 주지 않는다. question 글에 없는 그림 속 모습·안내판"
        "을 떠올리게 하지 않는다(미션 그림은 question과 생각 열기 질문으로 그림).",
    ]
    lines += [
        # 실측 2026-11-11(초4): 화요일 미션이 사건과 무관한 그림책 소개, 목요일은 수사 연결 문장
        # '받침대 무게'인데 문제는 '모래 무게'(#535). 소재 일치는 미션 검토 STORY_LINK가 본다
        # #782 A안(사용자 결정 2026-11-18): 문제의 주 자료는 그날 찾은 증거. 전에는 '오늘 장소의
        # 물건·
        # 등장인물이 만든 자료도 소재'라 연습 글·안내 글·그림책 장면이 통과했다(#634 실측 미션 485개
        # 중 증거를 자료로 쓴 것 24개)
        # #782 테마 짜임(사용자 결정 2026-11-20 "부탁을 들어주면 알려 줌"): 부탁 날 미션은 돕는
        # 사람의 일, 수사 날은 그 사람이 가진 증거를 읽고 따지는 일
        (
            f"- 오늘 미션 방식: {WAY_KO[way]}. 문제는 오늘 돕는 "
            f"사람({helper or '그 장소 사람'})의 "
            "일로 쓴다: '오늘 할 일'의 그 일을 학생이 대신 해 주게 하고(예: '떡집 사장님이 떡 "
            "12개를 "
            "상자 3개에 똑같이 나누려고 해. 한 상자는 전체의 몇 분의 몇일까?'), '오늘 문제의 "
            "지문'을 "
            "question 안에 그대로 넣는다. 문제가 학생 자신의 생각·주장·경험을 쓰게 하면 그 답이 "
            "돕는 사람에게 어떻게 쓰이는지 question에 밝힌다(예: '네 경험은 안내판 끝에 붙을 "
            "거야'). 사건 증거인 척 지어내지 않는다(그 사람의 일 자체가 문제 "
            "소재, 미션 검토 STORY_LINK)."
            if way != INVESTIGATE
            else "- 오늘 미션 방식: 수사. 문제의 주 자료는 오늘 돕는 사람이 가진 증거(본 "
            "사람의 "
            "말·적은 기록)이고 '오늘 문제의 지문'을 question 안에 그대로 넣어 그 증거로 그날 생각 "
            "유형·성취기준 활동을 하게 한다(미션 검토 STORY_LINK). 이때도 사건 현장의 오늘 단서 "
            "특징 값은 정하지 않는다. 돕는 사람 자신의 생각·마음을 추측하게 하지 않고 증거 속 "
            "사람의 말·기록을 따지게 한다."
        ),
        "- 질문이 요구하는 학생 자신의 경험·생각(돌아보기의 경험 잇기, 성취기준이 요구한 자기 "
        "경험)은 줄이거나 선택으로 두지 말고 그대로 묻는다.",
        "- 어느 후보가 답인지는 쓰거나 묻지 않는다. 문제를 사건 "
        "풀기(누구·어디·무엇 맞히기)로 만들지 않는다.",
        # #634 ③ 남은 위험(설계 17.8.5): 미션·대화가 후보 동물의 특징을 말하면 정해진 단서보다 먼저
        # 근거가 샘. 문제 소재는 사건 물건·일(incident)에서
        *(
            [
                f"- 이번 주 사건: {theme.get('incident') or ''}. 문제 소재는 이 사건 "
                "물건·일과 오늘 장소·오늘 찾은 증거에서 가져온다. 동물 이야기·동물 설명 "
                "글(동물의 생김새·습성·먹이·발자국 모양)은 쓰지 않는다(이번 주 단서보다 먼저 "
                "답의 근거가 됨)." + TESTIMONY_KEEP
            ]
            if animal
            else [
                f"- 이번 주 후보({story_type(theme).candidate_kind}) 이야기·설명 글(그 "
                f"{story_type(theme).candidate_kind}의 색·맛·무게·소리 같은 특징)은 문제에 쓰지 "
                "않는다(이번 주 단서보다 먼저 답의 근거가 됨). 문제 소재는 "
                f"{'손에 든 대상·' if story_type(theme).target_in_hand else ''}오늘 "
                "장소·오늘 찾은 증거에서 가져온다." + TESTIMONY_KEEP
            ]
            if hide
            else []
        ),
        "- 이번 주 단서는 학생이 문제를 마친 뒤 화면이 따로 보여 준다. 증거가 무엇을 뜻하는지(단서 "
        "결론)를 문제·안내·생각 열기 질문·예시 답에 쓰지 않고, 문제의 답이 단서가 되게 만들지 "
        "않는다."
        # #782 설계 v13: 수사 날 단서는 따져서 확실해진 증언 내용(예시 답이 믿을 만하다고 하는
        # 그 사실)
        + (
            " 다만 오늘은 수사 날이라 단서가 지문 증언을 따져 확실해진 그 내용이다(예시 답이 그 "
            "증언을 믿을 만하다고 하는 것은 설계, 그 내용이 어느 후보를 가리키는지는 쓰지 않음)."
            if testimony_day(d)
            else ""
        ),
    ]
    if DAY_TYPE[day] == "EVALUATE":
        lines += [
            "- 따져 보기는 자기 주장·근거와 함께 다른 관점(반대 의견·예외)을 생각해 답하는 부분을 "
            "질문에 넣고 예시 답에도 쓴다. 그 부분을 필수로 볼지는 관리자가 미션 요소에서 정한다"
            "(요소 기본값은 미션 초안 규칙 그대로).",
        ]
    if day == "FRI":
        lines += [
            # 실측 2026-11-15 닫기 3c 미션 검토 STANDARD_FIT: '비슷한 경험이 떠오르면 덧붙여도
            # 좋아'처럼 자기 경험을 선택으로 둠
            "- 돌아보기에서 자기 경험과 잇기는 꼭 쓰게 한다. '떠오르면 덧붙여도 좋아'·'경험이 "
            "있다면'처럼 선택으로 쓰지 않는다.",
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
    # #782 설계 v3(사용자 결정 2026-11-21): 첫 줄(오늘 온 까닭)은 코드 문장(fill_day_steps)
    "- 첫 줄(① 오늘 온 까닭)은 코드가 첫 등장인물의 말로 넣는다. 너는 그다음 줄(②)부터 쓰고 첫 "
    "줄을 "
    "되풀이하지 않는다. 주어진 '미션 방식'대로 이 순서로 이어지게 한다(#782 테마 짜임).\n"
    "  - 첫날(월요일)은 시작 이야기에 없는 '어제'를 지어내지 않는다(코드 검사 DAY1_TIME).\n"
    "  - 부탁: ① 오늘 온 까닭(인물의 말로, 오늘 여기 온 까닭) → ② 돕는 사람이 자기 일로 "
    # #782 설계 v10: '막막해'가 대화 163개 중 44개(7차). v11: '구체적으로'를 빼고 짧게(8차 40자
    # 넘는 줄 20 → 46)
    "곤란해함(한 줄 40자 안, '막막해'만 쓰지 않음) → ③ 돕는 사람이 '오늘 할 일'을 "
    "부탁하며(부탁은 '오늘 문제'가 시키는 것을 짧게 다 "
    "담고 문제와 다른 일을 부탁하지 않음) 주어진 '돕는 사람의 약속'의 뜻대로 오늘 부탁한 일을 "
    "도와주면(조건은 오늘 일로 자기 말로) 그때 알게 된 것(본 것·들은 소리·맛본 것·맡은 냄새, "
    "기록 날은 자기 기록)을 알려 주겠다고 함(정해진 문장을 그대로 쓰지 않고, 주어진 감각과 다른 "
    "감각으로 쓰지 않음. 약속 말에는 '그때'와 알려 줄 것을 꼭 넣는다: 본 날 '그때 본 걸', 들은 "
    "날 '그때 들은 소리를', 기록 날 '내 일지를 보여 줄게'처럼 자기 기록(예: '편지를 같이 써 주면, "
    "그때 본 걸 알려 줄게'). 무엇(재료·색·모양·자리)인지는 말하지 않고 '오늘·아까 본 것', "
    "'안내문에서 본 것'처럼 다른 때·곳을 붙이지 않음 — 그때 본 단서와 어긋남, #782 설계 v12, "
    "코드 검사 ASK_PROMISE) → 마지막 줄 뭉치가 같이 도와 보자고 함. "
    "부탁 줄과 약속 줄은 나눠 쓴다(한 줄 40자 안, #782 설계 v8). "
    "사건과 상관없는 것(일하는 요령·고마운 것)을 알려 주겠다고 하지 않고(코드 검사 ASK_PROMISE), "
    "본 것이 무엇인지(단서 내용)는 말하지 않는다.\n"
    "  - 부탁 날은 오늘 증거·흔적·자국 이야기를 꺼내지 않는다(그날 증거는 문제를 마친 "
    "뒤 단서로 나옴, 어제 일은 오늘 온 까닭에서 들은 것만 말함).\n"
    "  - 수사: ① 오늘 온 까닭 → ② 돕는 사람이 '오늘 찾은 증거'를 보여 주거나 이야기함(그 "
    "증거 그대로, 다른 증거를 지어내지 않음) → ③ '오늘 할 일'처럼 그 증거를 같이 읽고 따져 "
    "보자고 함 → 마지막 줄 뭉치가 함께 살펴보자고 함. 증거가 무엇을 뜻하는지는 말하지 않는다. "
    "돕는 사람이 자기 생각·마음을 추측해 보라고 하지 않는다(따질 것은 증거 속 사람의 말·기록).\n"
    "  - 앞 줄과 말이 자연스럽게 주고받아지게 쓴다(앞 줄에 답하거나 이어 받음, 갑자기 다른 "
    "이야기를 꺼내지 않음). 마지막 줄은 늘 뭉치다.\n"
    "- 화자(speaker)는 '뭉치', 주어진 등장인물 이름, 오늘 돕는 사람(주어진 호칭 그대로)만. "
    "찾고 있는 대상(사라진 동물·물건, 일을 한 동물)은 말하지 않고 대화에 나타나지도 않는다(사용자 "
    "글이 '손에 든 대상'이라고 하면 나와도 "
    "된다). 쓰지 말 낱말의 후보 이름은 쓰지 않는다.\n"
    "- 단서는 학생이 오늘 문제를 마친 뒤 화면이 보여 준다. 증거가 무엇을 뜻하는지(오늘 단서 "
    "결론)와 앞 요일 단서가 무엇이었는지 말하지 않는다(문제는 순서 없이 풀 수 있어 아직 못 얻은 "
    "학생이 있음). 어제 일은 들은 것만 말하고 어제 사람이 하지 않은 부탁·소개를 지어내지 않는다. "
    "글로 할 수 없는 활동(그래프 그리기·만들기·재기·걷기·발표)을 시키지 않는다(코드 검사 "
    "ACT_NAME). 주어진 이름 말고 다른 "
    "장소·사람 이름을 새로 꺼내지 않는다.\n"
    "- 줄 수는 주어진 범위를 지킨다. 한 줄에 한 가지만, 25자 안팎(공백 포함 40자를 넘으면 안 됨).\n"
    "- 장면 메모를 그대로 옮기지 말고, 인물이 그 자리에서 실제로 할 법한 짧은 말로 쓴다. "
    "'자료'처럼 어른스러운 낱말 대신 증거 이름(일지·사진·발자국 등)을 그대로 쓴다.\n"
    "- text에는 말만 쓰고 앞에 '이름:'을 붙이지 않는다.\n"
    "- 오늘 문제의 값·풀이 방법·답(만들 물건 같은 답이 될 생각 포함), 예시 답 내용, 금지어는 쓰지 "
    "않는다.\n"
    '- 말하는 사람은 자기 이름을 3인칭으로 부르지 않는다("수아: 수아는…" 금지). 학년에 맞는 말투.\n'
)


def avoid_words(theme: Theme, day: str) -> list[str]:
    """문제 전 글(대화 LLM 줄·살펴보기)이 피할 낱말: 그날 "
    "단서 허용 값과 장소 후보 이름(점검 C11·C13)."""
    d = next(x for x in theme["days"] if x["day"] == day)
    # #782 설계 v13: 검사(CLUE_EARLY·PREV_CLUE)는 부정형 단서면 빠지는 값을 봄(clue_says) —
    # 허용 값만 주면 수사 날 문제 글 증언 속 빠지는 값('갈색은 아니었어')을 대화가 따라 써서 걸림
    allowed = [*((d.get("condition") or {}).get("allowed") or []), *clue_says(d)]
    # 동물 주인공 가족은 후보 머리 낱말까지(#634 ③ CANDIDATE_NAME과 같은 낱말)
    hide = story_type(theme).hide_candidates
    names = (
        [*candidate_words(theme), *secret_values(theme)] if hide else theme.get("candidates") or []
    )
    # 앞 요일 단서 결과도 피함(#782 테마 짜임 PREV_CLUE, 문제는 순서 없이 풀 수 있음)
    names_before = [x.get("day") for x in theme["days"]]
    before = [
        a
        for x in theme["days"][: names_before.index(day)]
        for a in [*((x.get("condition") or {}).get("allowed") or []), *clue_says(x)]
    ]
    return list(dict.fromkeys([*allowed, *before, *names]))


def way_clue_rule(theme: Theme, day: dict) -> str:
    """단서 칸 고쳐 쓰기의 미션 방식 규칙(줄거리 프롬프트 clue 규칙과 같음, #782)."""
    if mission_way(day) == ASK:
        helper = day.get("helper") or "그 장소 사람"
        # #782 설계 v6: 맡겨 둔 대상 자체의 흔적은 맡겨지기 전에 본 것(KEPT_TRACE, v7 '맡겨지기')
        kept = (
            " 관리실에 맡겨 둔 대상 자체의 흔적은 '맡겨지기 전에 내가 보니 ~'처럼 맡겨지기 전에 본 "
            "것으로 쓰고, 자기가 맡아 두었거나 맡겼다고 쓰지 않는다(코드 검사 "
            "KEPT_TRACE·KEPT_PLACE)."
            if kept_target(theme)
            else ""
        )
        return (
            f"부탁 날이라 돕는 사람({helper})이 자기가 본 것·가진 것을 "
            "직접 알려 주는 말로 쓴다(예: '그때 공 바구니 곁에서 인형을 봤어!', 기록이면 '내 "
            "사진에 "
            "~가 찍혀 있어!', 흔적이면 '내가 창고 앞에서 본 발자국은 ~'). 전해 들은 말('~였대·"
            "~났대')로 쓰지 않는다(코드 검사 CLUE_SOURCE). 기록은 돕는 사람 자신의 '내 {매체}', "
            "흔적의 "
            "소리·냄새·맛은 '내가 흔들어 보니·맡아 보니·맛보니'(본 것이 아님). 이름·'고마워!' 같은 "
            "앞말은 붙이지 "
            "않는다." + kept
        )
    if testimony_day(day):  # #782 설계 v13: 지문 증언 속 내용
        return (
            "수사 날이라 지문 증언을 따져 확실해진 그 내용으로 쓴다(증언에 없는 내용을 더하지 "
            f"않음, 지문: {day.get('missionMaterial') or ''})."
        )
    return "수사 날이라 그 증거를 따져 확실해진 사실로 쓴다."


def ask_promise(theme: Theme, d: dict) -> str:
    """부탁 날 돕는 사람의 약속 한 줄(증거 종류대로, 무엇을 봤는지는 말하지 않음).

    #782 설계 v10: 대화 요청에는 뜻만 주고(promise_meaning) 이 문장은 마지막 시도에도 ASK_PROMISE만
    남을 때 대화 노드가 약속 줄로 바꿔 넣는 코드 대신 문장. 감각은 promise_sense.
    #782 설계 v11: 대신하는 날이 여럿일 수 있어(v12부터 마지막 시도에만) — 감각
    마다 짧은 꼴 셋(PROMISE_FORMS)을 그 주 같은 감각 부탁 날 안의 순서로 돌려 써 대신한 날끼리 같은
    문장이 덜 나오게 함. 장소 이름은 넣지 않음(잃어버린 물건·시간 탐정은 장소가 후보 이름일 수
    있음)."""
    sense, medium = promise_sense(theme, d)
    forms = PROMISE_FORMS[sense]
    if sense == "RECORD":
        medium = medium or "기록"
        josa = "을" if (ord(medium[-1]) - 0xAC00) % 28 else "를"  # 받침 있으면 '을'
        # #782 설계 v8: 녹음은 들려줌
        verb = "들려줄게" if medium == "녹음" else "보여 줄게"
        forms = tuple(f.format(medium=medium, josa=josa, verb=verb) for f in forms)
    return forms[promise_turn(theme, d, sense) % len(forms)]


# #782 설계 v11: 코드 대신 약속 문장(감각마다 짧은 꼴 셋, 40자 안, ask_promise_missing·
# ask_promise_mismatch를 통과). 첫 꼴은 v10 문장 그대로
# #782 설계 v8: 들은·맛본·맡은 날은 그렇게 안 것(전에는 늘 '본 걸'이라 소리 날과 어긋남)
# #782 설계 v9: '그때 들은 걸'은 남에게 전해 들은 말로 읽혀 '내가 들은 소리'로
PROMISE_FORMS: dict[str, tuple[str, ...]] = {
    "SEEN": (
        "도와주면 그때 본 걸 알려 줄게",
        "다 끝나면 그때 내가 본 걸 말해 줄게",
        "도와주면 내가 본 것을 들려줄게",
    ),
    "HEARD": (
        "도와주면 그때 내가 들은 소리를 알려 줄게",
        "다 끝나면 내가 들은 소리를 말해 줄게",
        "도와주면 내가 들은 소리를 들려줄게",
    ),
    "TASTED": (
        "도와주면 그때 내가 맛본 걸 알려 줄게",
        "다 끝나면 내가 맛본 걸 말해 줄게",
        "도와주면 내가 맛본 것을 들려줄게",
    ),
    "SMELLED": (
        "도와주면 그때 내가 맡은 냄새를 알려 줄게",
        "다 끝나면 내가 맡은 냄새를 말해 줄게",
        "도와주면 내가 맡은 냄새를 들려줄게",
    ),
    "RECORD": (
        "도와주면 내 {medium}{josa} {verb}",
        "다 끝나면 내 {medium}{josa} {verb}",
        "도와주면 내 {medium}도 {verb}",
    ),
}


def promise_turn(theme: Theme, d: dict, sense: str) -> int:
    """그 주 부탁 날 중 약속 감각이 같은 날 안에서 이 요일의 순서(#782 설계 v11, 이 요일은 늘 셈).
    요일 순서로만 돌리면 월·목처럼 세 칸 떨어진 날이 같은 문장이 됨. 테마에 없는 요일이면 0."""
    day = d.get("day")
    days = [d if x.get("day") == day else x for x in theme.get("days") or []]
    same = [
        x.get("day")
        for x in days
        if (x is d or mission_way(x) == ASK) and promise_sense(theme, x)[0] == sense
    ]
    return same.index(day) if day in same else 0


def dialogue_user(theme: Theme, day: str, draft: Draft, grade: int, feedback: list[str]) -> str:
    """그날 단서는 넣지 않는다(학생이 미션을 마친 뒤 보여 줌). 오늘 온 까닭·오늘 찾은 증거·증거에서
    오늘 할 일은 대화를 쓰는 재료로만 준다(#782 테마 짜임: 전에는 끝 두 줄로 그대로 넣었음)."""
    d = next(x for x in theme["days"] if x["day"] == day)
    lo, hi = DIALOGUE_LINES[grade]
    count = f"{lo}줄" if lo == hi else f"{lo}~{hi}줄"
    # 예전 저장본(부분 다시 생성)은 오늘 온 까닭이 없어 그 자리에서 코드 문장(#782 설계 v4 B4, 대화
    # 노드가 붙이는 첫 줄과 같음)
    step = first_line_text(theme, day)  # #782 설계 v7: 대화 노드가 붙이는 첫 줄과 같음
    helper, way = str(d.get("helper") or "").strip(), mission_way(d)
    lines = [
        f"학년: 초{grade}",
        f"학년에 맞는 말투: {grade_style(grade)}",
        f"줄 수: {count}(첫 줄은 코드가 넣으므로 너는 그 뒤 {lo - 1}~{hi - 1}줄)",
        # #782 설계 v3: 첫 줄은 코드 문장, 모델은 그다음부터
        f"첫 줄(코드가 넣음, 되풀이하지 않음): {first_speaker(theme)}: {step}",
        f"등장인물: 뭉치, {', '.join(c['name'] for c in theme['characters'])}",
        f"오늘 돕는 사람(화자로 써도 됨): {helper}" if helper else "",
        f"미션 방식: {WAY_KO[way]}({way})",
        f"오늘({DAY_KO[day]}요일) 장소: {d['place']}",
        f"오늘 장면: {d['sceneNote']}",
        # #782: 월요일은 어제 한 일이 없음(이름표가 늘 '어제'라 첫날 대화가 '어제 빈손을
        # 알아챘다'로 시작 이야기와 어긋남, 저장된 테마 230개 중 9개)
        f"시작 이야기(첫날이라 여기서 이어짐, 어제 한 일 없음): "
        f"{theme.get('introStory') or theme.get('intro') or ''}"
        if day == "MON"
        else "",
        f"오늘 온 까닭({'시작 이야기의 사건에서 이어짐' if day == 'MON' else '오늘 여기 온 까닭'}, "
        f"① 재료): {step}",
        # 수사 날만 증거를 문제 전에 보여 줌(부탁 날 증거는 문제 뒤 단서로 나옴)
        f"오늘 찾은 증거(② 재료, 이 증거 그대로): {d['discovery']}" if way == INVESTIGATE else "",
        f"오늘 할 일(③ 재료, 부탁·증거를 같이 보자는 말): {d['missionHook']}",
        # #782 미션 방식: 부탁 날 보답이 엉뚱했음(실측 '인사말 만들 때 살펴볼 점'), 증거 종류대로
        # 정해 줌
        # #782 설계 v10: 문장을 주면 작은 생성 4개 중 3개가 같은 약속이라(7차 같은 문장 53번) 뜻만
        # 줌(감각은 promise_sense)
        # #782 설계 v12: '오늘 일과 엮어'가 약속 내용을 오늘과 엮게 해 9차 약속 164줄 중 '오늘'
        # 42·출처 22(글 검토 실패 50 중 27) → 오늘 일은 조건에만
        f"돕는 사람의 약속(③): 오늘 부탁한 일을 도와주면(조건은 오늘 일로 자기 말로) 그때 "
        f"{promise_meaning(theme, d)} 알려 주겠다는 뜻으로 한 줄. 약속 말에 '그때'와 알려 줄 것을 "
        "꼭 넣고(기록 날은 '내 ○○를 보여 줄게'처럼 자기 기록, 코드 검사 ASK_PROMISE), 무엇인지는 "
        "말하지 않으며 '오늘·아까·○○에서'를 붙이지 않음(예시 문장을 그대로 쓰지 않음)"
        if way == ASK
        else "",
        (
            # #782 설계 v3: 선물·길·출처 찾기 물건은 관리실에 맡겨 둠
            "맡겨 둔 대상(관리실에 맡겨 둠, 이름은 대화에 나와도 되지만 들고 있지 않음, 단서 특징 "
            "값은 "
            f"말하지 않음): {theme.get('target') or ''}"
            if kept_target(theme)
            else "손에 든 대상(대화에 나와도 됨, 단서 특징 값은 말하지 않음): "
            f"{theme.get('target') or ''}"
            if story_type(theme).target_in_hand
            else f"밝힐 것({story_type(theme).target_note}): {theme.get('target') or ''}"
            if story_type(theme).target_note
            else f"찾는 대상(대화에서 말하지 않고 나타나지 않음): {theme.get('target') or ''}"
        ),
        f"오늘 문제(대화 뒤에 나옴, 값·풀이·답을 대화에 쓰지 않음): {draft.question}",
        # #782 설계 v10 5절: 첫 등장인물의 대화 줄도(코드 검사 INTRO_HEARD·INTRO_FOUND)
        f"아이가 이미 아는 것: {known}" if (known := child_known_rule(theme)) else "",
        f"금지어: {', '.join(draft.forbidden_terms) or '없음'}",
        "쓰지 말 낱말(오늘·앞 요일 단서 결론, 후보 이름): "
        + (", ".join(avoid_words(theme, day)) or "없음"),
    ]
    if feedback:
        lines += [
            "",
            "이전 대화가 검사를 통과하지 못했다. 고칠 점:",
            *[f"- {x}" for x in dict.fromkeys(feedback)],
        ]
    return "\n".join(lines)


# 글·그림·영상 검토 SAFETY에 같은 글(#634: 동물 장난꾸러기·경찰관 역할이 안전 검토에 걸리지 않게,
# 설계 17.8.5)
SAFETY_STORY = (
    "동물의 습성·장난은 범죄가 아니고, 사람이 동물을 제자리에서 부드럽게 안아 올리는 것은 "
    "폭력·위험이 아니다. 경찰관·소방관 차림은 해결사 역할일 뿐이다(체포·수갑·벌주기가 나오면 "
    "결함). 밤에 들린 궁금한 소리 이야기(소리 탐정)는 무섭지 않은 궁금증이다(귀신·괴물·유령이 "
    "나오면 결함). 사람이 동물 먹이를 먹거나 동물에게 사람 음식을 먹이면 결함."
)

REVIEW_SYSTEM = (
    "너는 초등 교육 콘텐츠 검토자다. 주간 테마 초안(이야기 틀·단서·문제 5개·대화 5개)을 아래 여섯 "
    "항목으로 검토한다.\n"
    "항목마다 verdict를 PASS(문제 없음)·WARN(애매해서 사람이 볼 것)·FAIL(분명한 결함, 고쳐야 함) "
    "중 하나로, 문제가 있는 "
    "요일(days)과 근거 한두 문장(reason)을 쓴다. promiseDays는 CLUE_LOGIC에서만 쓰고(다른 항목은 "
    "빈 목록), 그 요일의 결함이 부탁 날 돕는 사람의 약속 줄뿐이고 단서는 맞을 때 그 요일을 넣는다"
    "(그 요일 대화만 다시 만듦, #782 설계 v12). 단서·이야기가 틀린 요일은 넣지 않는다.\n"
    "분명한 결함만 FAIL로 한다. 더 좋게 고칠 수 있다는 이유만으로 FAIL로 하지 않는다. 여섯 항목을 "
    "모두 한 번씩 쓴다.\n"
    "판정 눈높이: 이 이야기는 그 학년 아이가 읽는 추리다. 그 학년 아이가 읽고 상식으로 납득하면 "
    "통과다. 이야기에 나오지 "
    "않은 가능성(나중에 옮겨졌을 수도, 다른 소리도 났을 수도, 창문으로 들어갔을 수도 등)을 "
    "상상해서 FAIL로 하지 않는다. "
    "그런 의문은 WARN으로 남긴다(사람 검토에서 판단). FAIL은 글에 실제로 있는 결함에만 준다: 단서 "
    "문장과 조건(특징·허용 "
    "값)이 다름, 이야기 속 사실끼리 모순, 찾는 대상이 종료 이야기 전에 나타나거나 말함"
    "(단, 잃어버린 것 찾기의 시작 영상 "
    "1컷에서 주인이 사라지기 전의 대상을 지닌 모습은 허용), 아직 찾지 "
    "못한 대상 몸·겉의 "
    "자국이나 상태를 직접 본 것처럼 씀(이야기 속 사실끼리 모순), "
    '찾지 못한 것("없었다·못 봤다")만으로 뺌('
    "빠지는 값을 '본 ○○는 X는 아니었어'로 말하는 부정형 단서는 설계라 결함이 아님 — 허용 값을 "
    "직접 말하지 않아도 됨, #782 설계 v8), "
    "장소 설명·일반 상식·"
    "지시를 증거처럼 씀, 목요일 전에 정답이 정해짐. "
    # #634 ② 설계 17.8.13: 손에 든 것 종류는 '못 찾은 대상' 전제를 쓰지 않음
    "단, 손에 든 것 종류(storyType ORIGIN·GIFT·SECRET_INGREDIENT·ROUTE)는 대상이 처음부터 손에 "
    "있어 "
    "대상이 나오는 것과 대상 겉에 묻은 것·대상 자체(무게·소리·맛 등)를 증거로 쓰는 것이 "
    "설계다(결함 "
    "아님). 이 종류의 흔적(TRACE)에는 돕는 사람이 대상을 직접 들어 보거나 흔들어 보거나 맛본 "
    "관찰도 "
    "들어간다(흔적이 남지 않았다는 이유로 결함이 아님). 대상을 준비한(산·만든·보낸) 때의 "
    "목격·기록과 받은 뒤 살핀 흔적은 같은 대상의 증거라 서로 다른 때를 섞은 것이 아니다. 선물 "
    "상자는 "
    "엔딩 전에 상자를 열거나 안의 "
    "선물을 말하면 결함. "
    # #634 ④ 설계 17.8.17
    "시간 탐정(storyType WHEN)은 그 일(예: 화단에 물을 준 일)이 처음부터 알려진 사실이고 모르는 "
    "것은 때뿐이라 그 일이 나오는 것은 결함이 아니다. 단서는 그 일을 하던 그때 들리거나 보인 "
    "것(종소리·빵집·가로등)의 목격·기록이고, 시작 이야기 끝의 마을 규칙(코드가 붙임)으로 후보 "
    "시각을 가른다(흔적 단서가 없는 것도 설계). 엔딩 전 글에 시각이 나오면 결함"
    # #782 설계 v10(2.4)
    "(단서에 시각이 적혔다는 말도 결함). 그 일을 한 사람은 등장인물이 아니고 끝 이야기에서 처음 "
    "나온다 — 등장인물이 그 일을 한 사람이면 결함(처음부터 물어보면 끝남). 탈것 찾기"
    "(storyType VEHICLE)는 온 사람이 처음부터 나오고 모르는 것은 타고 온 탈것뿐이다(엔딩 전에 "
    "탈것이 장면에 나오면 결함). "
    # #782 설계 v10(2.1): 탈것은 코드로 가르기 어려워 지시문·글 검토만
    "아이는 온 사람이 도착하는 모습과 들고 온 것을 보지 못했다(이미 와서 짐을 정리해 둠) — "
    "아이가 도착 장면·들고 온 것·올 때 난 소리를 직접 보거나 들었다고 쓰면 결함(단서를 이미 앎). "
    "소리를 들은 사람의 증언은 목격(SIGHTING)이다. 소리 탐정"
    "(storyType SOUND)은 그 소리가 처음부터 알려진 사실이고 모르는 것은 소리를 낸 것뿐이며, "
    "흔적 단서가 없고 여러 밤의 증거여도 같은 소리면 같은 그때로 본다(설계, 결함 아님). 결말에서 "
    "동물을 만지거나 붙잡으면 결함. "
    # #782 설계 v10(2.1): 아이가 이미 아는 것(코드 검사 INTRO_HEARD·INTRO_FOUND와 같은 말)
    "소리 탐정에서 아이(첫 등장인물)는 소리를 직접 듣지 않고 이웃·가족에게 전해 들은 것이 "
    "설계다 — 시작 이야기·오늘 온 까닭·대화에서 아이가 소리를 직접 듣거나 소리에 깨면 결함(소리 "
    "특징을 이미 알아 단서가 필요 없어짐). 출처 찾기(ORIGIN) 물건은 다른 사람(관리실 직원·"
    "선생님)이 주워 맡겼고 아이는 이야기로만 안다 — 아이가 그 물건을 직접 줍거나 손에 쥐고 "
    "살펴보면 결함. "
    "시작 이야기에서 앞으로 열릴 행사(토요일 대회·모임 직전 등)를 끝 이야기 전 단서·지문·문제가 "
    "이미 열린 것처럼 쓰면 결함(코드 검사 EVENT_LATER).\n"
    "CLUE_LOGIC: 정답 논리(어느 후보가 언제 빠지고 정답만 남는지)는 특징 표(features)와 단서 "
    "조건(condition)으로 코드가 "
    "이미 확인했다. condition.kind가 STORY인 날(사건 단서, #782)은 사건이 어떻게 벌어졌는지 새 "
    "사실을 주는 날이라 특징·값을 말하지 않는 것이 맞다. 그 날은 사건 단서가 그날 남은 어떤 "
    "후보와도 어긋나지 않는지(상식으로 한 후보를 빼거나 가리키면 결함 — 예: 생쥐가 남았는데 "
    "'높은 나무 위로 갔다'), 앞 요일 단서나 시작 이야기에서 아이가 이미 본 모습을 되풀이하지 "
    "않는지, 그날 증거·장면과 맞는지 본다. 수사 날 기록 단서가 지문(그 기록)에 없는 말을 "
    "기록에 적혀 있다고 하면 결함(#782 설계 v9). "
    # #782 설계 v13: 수사 날 지문은 그때 직접 본 사람의 증언 하나, 단서는 따져서 확실해진 그 내용
    # #782 설계 v13: 15차 치명 snd6b(미션 코드 검사 INCIDENT_TIME과 같은 말)
    "문제가 사건 때를 '어젯밤·그저께'처럼 그날 기준 지난 때로 쓰면 결함(사건은 월요일 전 일). "
    "수사 날(missionWay INVESTIGATE) 단서 내용이 지문(missionMaterial) 증언에 없으면 결함(단서는 "
    "따져서 확실해진 그 증언 내용), 그날 문제 예시 답이 증언 속 본 사실을 믿기 어렵다거나 알 수 "
    "없다고 결론 내는데 단서가 확실해졌다고 하면 결함(#782 설계 v13). "
    "부탁 날 대화에서 돕는 사람이 알려 주겠다고 "
    "한 것(본 것·들은 소리·자기 기록)과 그날 단서의 감각·출처가 다르면 결함(예: 들은 소리를 "
    "알려 준다더니 본 달빛, #782 설계 v10). 약속에 단서와 다른 때·출처를 붙여도 결함(예: '오늘 "
    "본 것', '안내문에서 본 것'인데 단서는 그때 본 것) — 이때 단서가 맞으면 그 요일은 "
    "promiseDays(#782 설계 v12). 대화가 없는 요일(대화 생성이 끝내 실패해 코드가 경고로 "
    "남김)은 약속을 볼 수 없다는 이유로 결함으로 보지 않는다(10차 글 검토 실패 42번 중 10번이 "
    "'대화가 비어 있음'). "
    # #782 설계 v12: 9차 치명 결함(hand5b·snd5·auto5b·new4·hand4·way6b)
    "출처 찾기 물건 단서에서 돕는 사람이 자기가 그 물건을 줍거나 날랐다고 하면 결함(주운 사람은 "
    "시작 이야기의 그 사람뿐, 돕는 사람은 놓여 있을 때·누가 들고 지날 때 곁에서 봄). 소리 탐정 "
    "오늘 온 까닭이 시작 이야기와 다른 사람에게 들었다고 하면 결함. 사건 단서(STORY)가 다른 요일 "
    "특징(이름·값)을 미리 가리키면 결함(예: 금요일 특징이 '출입문과 거리'인데 수요일 사건 단서가 "
    "'출입문 쪽으로'). 오늘 온 까닭이 앞 요일 기록에 없는 것을 그 기록에 나왔다고 하면 결함. "
    "선물 상자가 배달돼 왔는데 등장인물이 상자를 들고 왔다고 하면 결함. "
    "비밀 재료 찾기에서 시작 이야기의 행사(잔치)를 다른 이름(대회)으로 부르면 다른 음식이 "
    "되어 결함. 오늘 온 까닭이 어제 없던 일을 '어제 ~'로 대면 결함. "
    "소리 특징 단서를 '본'으로 쓰면 약속(들은 소리)과 "
    "어긋나 결함. 자기 기록(내 일지·영상)을 "
    "'~래'처럼 남의 말로 전하면 결함. "
    '그 밖에 너는 다음을 본다. 각 단서가 찾는 대상 자체의 흔적·목격·기록으로 "대상이 그 '
    "특징을 가진 곳·사람·때에 "
    '있었다"를 보여 주는지(장소 특징 설명·일반 상식·지시만 말하면 결함). 큰 질문이 지나간 일을 '
    "묻는지. 각 단서의 "
    "evidence(종류·때)가 단서 문장과 맞고, 때가 큰 질문이 묻는 그때를 가리키는지(서로 다른 때의 "
    "증거를 섞지 않는지). 각 "
    "단서 문장이 그 조건(특징·allowed 값)을 그대로 말하고 표에 없는 새 사실을 더하지 않는지. 표의 "
    "값이 그 장소·물건에 "
    "실제로 그럴 법한지(condition에 excluded가 있으면 단서는 그 빠지는 값을 '~는 아니었어'로 "
    "말하는 것이 설계 — 본 것·들은 것이 밝혀져 있으면 결함 아님). RULE 단서가 찾지 못한 것만으로 "
    "빼지 않고 그 값 때문에 답이 될 수 없음이 "
    "그 학년 눈높이에서 "
    "분명한지. HINT 단서가 목요일 전에 정답을 정해 버리지 않는지. 찾는 대상이 종료 이야기 전에 "
    "나타나거나 말하지 않는지(잃어버린 것 찾기 시작 영상 1컷의 사라지기 "
    "전 모습과, 사진·영상·기록에 찍힌 그때(지나간 "
    "때)의 대상 모습은 허용. 지금 있는 곳이 드러나면 결함). "
    "단서가 그날 장면의 이야기 속 사실인지(문제 활동의 결과가 아닌지). "
    # #634 ③(설계 17.8.5): 후보가 동물이면 표 값은 코드의 동물 사실표, 단서는 관찰
    "후보가 동물(storyType PRANK·FOOTPRINT)이면 특징 표의 값은 코드가 정한 동물 사실표 값(초등 "
    "상식 수준으로 단순화한 값, 예: 고양이는 걸을 때 발톱을 숨겨 발바닥 자국만)이라 맞다고 보고 "
    "다시 따지지 않는다. 단서가 그 값의 관찰(발자국·부분 목격·부분 기록)로 쓰였는지 본다('고양이는 "
    "밤에 다닌다' 같은 상식 문장을 단서로 쓰면 결함). 목격·기록은 부분만 보인 것이 설계라 동물 "
    "전체를 보지 못했다는 이유로 결함이 아니다. "
    # #634 ④: 마을 규칙표·탈것 사실표도 코드가 정한 값
    "후보가 시각(WHEN)·탈것(VEHICLE)·소리를 낸 것(SOUND)이면 특징 표 값은 코드가 정한 마을 "
    "규칙표·탈것 사실표·소리 사실표 값"
    "(예: 버스·기차·여객선은 정류장·역·나루에서 내려 도착한 곳에 바퀴 자국이 없음)이라 맞다고 보고 "
    "다시 따지지 않는다.\n"
    "ANSWER_HINT: 종료 이야기(outro)·종료 콘티(outroCuts) "
    "말고 학생이 보는 글(intro·장면·증거 발견 줄·수사 연결 "
    "문장·문제·안내·생각 열기 질문·예시 "
    "답·대화)이 정답을 직접 "
    "쓰거나 목요일 전에 정답을 확정하지 않는지. 월~수의 빈 rulesOut 단서가 정답 하나만 가리키지 "
    "않고 남은 다른 후보에도 "
    "맞는지. 단서는 학생이 그날 미션을 마친 뒤 보여 준다. 부탁 날(missionWay ASK)은 증거 발견 "
    "줄이 비어 있고 그날 증거는 미션을 마친 뒤 돕는 사람이 알려 주는 것이라, 단서와 같은 내용은 "
    "결함이 아니다. 다만 부탁 날 지문(missionMaterial)이 돕는 사람 자신의 기록(그날 증거)이라 "
    "문제 전에 단서 내용이 보이면 결함(#782 설계 v9). "
    "수사 날(missionWay INVESTIGATE) 사건 단서는 그날 지문·증거 발견 줄의 증언을 "
    "따져 확실해진 사실이라 그 내용이 지문·증거 발견 줄에 있어도 결함이 아니다(#782 설계 v8). "
    "수사 날 특징 단서도 같다: 지문은 그때 직접 본 사람의 증언이고 그날 단서 내용(특징 값 포함)이 "
    "들어 있는 것이 설계라 결함이 아니다(예시 답이 그 증언을 믿을 만하다고 하는 것도 설계, #782 "
    "설계 v13). "
    "증거 발견 줄(discovery)·수사 연결 "
    "문장(missionHook)·대화·미션(수사 날 문제 글 속 증언은 빼고)이 그날 단서 결론이나 정답을 미리 "
    "말하지 않는지. 수사 연결 문장이 "
    "그날 배울 개념·방법 이름(예: 분수 곱셈, 넓이 "
    "구하기)을 말하는 것은 설계상 허용이다(단서 결론·정답을 "
    "말할 때만 결함). 그 개념 낱말이 단서 값 낱말과 같아도 장소·때와 묶어 결론으로 말하지 않으면 "
    "허용. 장면·대화가 그날 "
    "문제의 답(만들 물건·계산 "
    "결과 등)을 미리 알려 "
    "주지 않는지.\n"
    "GRADE_VOCAB: 그 학년이 읽고 풀 수 있는 낱말·분량인지, 그 학년에 배우지 않은 개념이 없는지. "
    "특징 표(features)의 이름·값도 학생이 단서 근거로 보므로 함께 본다.\n"
    "STANDARD_FIT: 각 문제가 주어진 성취기준의 행동을 학생이 직접 하게 하고 생각 유형과 맞는지. "
    "학생 혼자 글로 답하는 "
    "미션이므로 협력처럼 혼자 할 수 없는 부분은 보지 않고 핵심 "
    "행동(설명·구분·설계·계산·점검 등)을 본다. "
    # #782 설계 v12: 9차 new3 '가게 주인이 그때 본 일을 설명하고'인데 문제에 그 말이 없음
    "수사 날 문제가 누가 본 일을 설명해 준다고 해 놓고 그 말을 보여 주지 않으면 결함(학생이 "
    "따질 글이 없음). " + TEXT_ONLY + " 정답 키·예시 답의 계산 값이 맞는지(풀이는 finalAnswer). "
    "예시 답이 질문을 빠짐없이 답하는지는 "
    "미션 검토가 이미 봤으므로 보지 않는다. 따져 보기의 "
    "다른 관점은 질문에 들어 있으면 되고 선택처럼 "
    "쓰였다는 이유로 결함이 아니다(필수 여부는 관리자가 정함).\n"
    # #782 설계 v13: 측정 판정(억지 연결)과 같은 말. 10~13차 억지 36건 중 26건이 돕는 사람의 일이
    # 그 장소와 동떨어짐인데 생성 과정 안에서는 보지 않았음(돕는 사람 검토 노드는 v11에서 뺌)
    "HELPER_FIT: 부탁 날(missionWay ASK)마다 본다. 돕는 사람(helper)이 그 장소(place)에서 할 법한 "
    "일을 부탁하고, 학생이 쓰는 답이 그 일에 실제로 쓰이는지(helperUse·대화·문제 글). 돕는 사람의 "
    "일이 그 장소·사건과 동떨어지면(예: 골목 청소원이 관리실 안내문 간추리기를 부탁, 산책길 "
    "안내원이 읽기 안내 카드를 부탁, 화단에서 책쉼터 안내문을 부탁) FAIL, 학생 답이 그 일에 어떻게 "
    "쓰이는지 드러나지 않으면 FAIL. 그 요일을 days에 쓴다. 수사 날·학생 자신의 경험을 쓰게 하는 "
    "부분·문장 길이·말투 같은 작은 다듬기 거리는 판정에서 뺀다. 그 일이 사건 증거가 아닌 것은 "
    "결함이 아니다(부탁 날 미션은 돕는 사람의 일).\n"
    "SAFETY: 폭력·범죄·위험·무서운 내용, 차별, 실존 인물·상표, 개인정보가 없는지. "
    + SAFETY_STORY
    + "\n"
)

# #782 설계 v13 가(사용자 결정 2026-11-23 "응 가로 해"): 14차 억지 11일 중 글 검토 HELPER_FIT이 건
# 날은 2일(다섯 요일·여섯 항목을 한 번에 봄). 측정 판정(judge_flow)과 같은 말로 부탁 날만 따로 판정
HELPER_JUDGE_SYSTEM = (
    "너는 초등학생 추리 학습 서비스의 콘텐츠 검토자다. 주간 테마의 부탁 날들을 요일마다 "
    "학생이 보는 순서대로 준다(오늘 온 까닭 → 문제 전 대화 → 문제 → 문제를 마친 뒤 받는 단서). "
    "요일마다 그날 미션(문제)이 이야기에 자연스럽게 들어오는지 엄격하게 판정하고 근거를 한 "
    "문장으로 쓴다. 요일마다 돕는 사람(helper)과 장소(place)를 함께 준다. 받은 요일을 모두 한 번씩 "
    "쓴다.\n"
    "- NATURAL: 돕는 사람이 그 장소에서 할 법한 일을 부탁하고, 학생이 쓰는 답이 그 일에 실제로 "
    "쓰이며, 단서는 그 사람이 본 것·가진 기록을 알려 주는 말이다.\n"
    "- FORCED: 위와 어긋난다(돕는 사람의 일이 그 장소·사건과 동떨어짐, 학생 답이 그 일에 쓰이지 "
    "않음, 단서가 그날 일·사람과 따로 놂, 문제를 풀면 증거가 풀린다는 식의 억지 연결).\n"
    "학생 자신의 경험을 쓰게 하는 부분, 문장 길이·말투 같은 작은 다듬기 거리는 판정에서 뺀다."
)


def helper_judge_user(
    theme: Theme, drafts: dict[str, Draft], dialogues: dict[str, list[dict]], days: list[str]
) -> str:
    """돕는 사람 판정 입력: 측정 판정(judge_flow)과 같은 칸을 부탁 날마다."""
    return json.dumps(
        {
            "case": f"{theme.get('title') or ''} / {theme.get('bigQuestion') or ''}",
            "days": [
                {
                    "day": day,
                    "place": theme_day(theme, day).get("place") or "",
                    "way": "부탁",
                    "helper": theme_day(theme, day).get("helper") or "",
                    "dayStep": theme_day(theme, day).get("dayStep") or "",
                    "dialogue": [f"{x['speaker']}: {x['text']}" for x in dialogues.get(day) or []],
                    "question": drafts[day].question if day in drafts else "",
                    "clue": theme_day(theme, day).get("clue") or "",
                }
                for day in days
            ],
        },
        ensure_ascii=False,
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
                "dayStep": d.get("dayStep") or "",  # #782 테마 짜임 오늘 온 까닭(내부 칸)
                "helper": d.get("helper") or "",
                # #782 설계 v13: HELPER_FIT(아이 답이 돕는 사람의 일에 쓰이는지)
                "helperUse": d.get("helperUse") or "",
                "missionWay": mission_way(d),
                # #782 미션 방식: 부탁 날 증거 발견 줄은 문제 전에 보이지 않는 내부
                # 메모(그날 단서가 나오는 곳)라 글 검토에 주지 않음(ANSWER_HINT 오탐 8번)
                "discovery": d["discovery"] if mission_way(d) == INVESTIGATE else "",
                "missionHook": d["missionHook"],
                "missionMaterial": d.get("missionMaterial") or "",  # #782 미션 지문(내부 칸)
                "mission": {k: draft.get(k) for k in MISSION_FIELDS},
                "dialogue": dialogues.get(d["day"], []),  # 끝내 실패해 빠진 대화는 빈 줄로 검토
            }
        )
    summary = {
        k: theme[k]
        for k in ("title", "world", "intro", "outro", "bigQuestion", "candidates", "answer")
    }
    t = story_type(theme)
    summary["storyType"] = f"{t.code}({t.label}, 후보는 {t.candidate_kind})"
    if t.animal:  # 사건 물건·일(미션 소재)
        summary["incident"] = theme.get("incident") or ""
    if t.needs_answer_look:  # 정답 모습(종료 그림 기준, ③·⑤)
        summary["answerLook"] = theme.get("answerLook") or ""
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
    "너는 초등 교육 콘텐츠 검토자다. 미션(문제) 하나를 아래 네 항목으로 검토한다.\n"
    "항목마다 verdict를 PASS(문제 없음)·WARN(애매해서 사람이 볼 것)·FAIL(분명한 결함, 고쳐야 함) "
    "중 하나로 쓰고 근거 한두 "
    "문장(reason)을 쓴다. 네 항목을 모두 한 번씩 쓴다. 전체 verdict는 항목 중 가장 나쁜 것.\n"
    "분명한 결함만 FAIL로 한다. 더 좋게 고칠 수 있다는 이유만으로 FAIL로 하지 않는다.\n"
    "EXAMPLE_COMPLETE: 예시 답(서술·논술은 exampleAnswer, 고르기·순서·분류·풀이는 answerKey. "
    "풀이(SOLUTION_STEPS)는 미션 초안 형식상 exampleAnswer가 "
    "없어도 되고 answerKey.finalAnswer가 맞는지 "
    "본다)이 질문이 묻는 것을 "
    "하나도 빠짐없이 답하는지. 질문이 둘 이상을 물으면(예: 처음 생각·바뀐 생각·까닭) 모두 들어 "
    "있어야 한다. 계산이면 값이 "
    "맞는지. maxSentences가 있으면 그 문장 수 안에서 질문이 묻는 것을 한 문장씩이라도 다 담으면 "
    "통과다(자세히 쓰지 않았다는 이유로 FAIL하지 않음, #782 설계 v8). "
    # #782 설계 v13: 검토는 그날 단서를 모르므로 지문 안에서 판정(13차 치명 snd3: 예시 답은 판단을
    # 미루는데 단서는 "분명해졌어")
    "story.missionWay가 수사(INVESTIGATE)이고 지문(missionMaterial)이 그때 직접 보거나 적은 "
    "사람의 증언이면, 예시 답이 증언 속 직접 본 사실을 믿기 어렵다거나 알 수 없다고 결론 내면 "
    "결함(짐작·전해 들은 부분을 덜 믿을 만하다고 구별하는 것은 됨, #782 설계 v13).\n"
    "STANDARD_FIT: 질문이 주어진 성취기준의 핵심 행동을 학생이 직접 하게 하고 생각 유형과 맞는지. "
    "학생 혼자 글로 답하는 "
    "미션이므로 협력처럼 혼자 할 수 없는 부분은 보지 않는다. "
    + TEXT_ONLY
    + " 따져 보기의 다른 관점은 "
    "질문에 들어 있으면 되고 선택처럼 쓰였다는 이유로 결함이 아니다(필수 여부는 관리자가 정함).\n"
    "MATERIAL: 답하는 데 필요한 것(읽을 글·비교할 글·수·관찰할 모습)이 질문 글 안에 다 있는지. "
    "그림에만 있는 정보나 주어지지 "
    "않은 글(예: '처음 쓴 글'을 비교하라는데 그 글이 없음)에 기대면 결함. 사진·녹음·그림·영상·"
    "지도·활동지를 보거나 듣게 하는데 그 내용이 질문 글에 없으면 결함. target이 주어지면, "
    "문제가 그 대상을 지금 보거나 "
    "곁에 있는 것처럼 쓰면 결함(아직 찾지 못한 대상, target에 '손에 든 대상'이라고 적혀 있으면 "
    "곁에 있어도 됨). "
    "사진·영상·기록에 찍힌 지나간 때의 대상 모습은 "
    "허용(지금 있는 곳이 드러나면 결함).\n"
    # 측정 2026-11-13(#535): 저장된 미션 50개를 사람이 판정한 것과 비교해 코드 검사(수사 연결
    # 문장 앞 낱말이 질문에 있는지)는 맞힘 5/10·찾음 5/11, 이 항목은 9/11·9/11이라 검토 항목으로
    # 둠(기준안, ai.md 17.6)
    # #782 A안: 주 자료가 그날 찾은 증거인지로 바꿈(전에는 장면 소품·등장인물이 만든 자료도 통과,
    # #634 실측 미션 485개 중 증거를 자료로 쓴 것 24개). FAIL이어도 경고만(사용자 결정 2026-11-15)
    # #782 테마 짜임(사용자 결정 2026-11-20): 미션 방식대로 봄. 부탁 날은 돕는 사람의 일, 수사
    # 날은 그 사람이 가진 증거가 주 자료
    "STORY_LINK: story가 주어지면 missionWay대로 본다. 부탁 날은 문제가 돕는 "
    "사람(helper)의 그 일(missionHook)을 학생이 대신 해 주는 문제인지(그 사람의 일이 사건 증거가 "
    "아니어도 됨, 다른 일로 바꾸거나 일과 상관없는 그림책·연습 글을 다루면 FAIL). 수사 날은 문제의 "
    "주 자료(학생이 읽고 다루는 글·자료)가 돕는 사람이 가진 증거(discovery, missionHook이 가리킨 "
    "것)인지(사건과 무관한 글을 주 자료로 삼으면 FAIL, 증거가 아닌 장면의 물건·상황만 다루면 "
    "WARN). "
    "story에 missionMaterial이 있으면 문제가 그 글을 지문으로 쓰는지도 본다(쓰지 않고 다른 글을 "
    "지문으로 삼으면 FAIL). 수학 부탁 날 문제가 구한 값을 그 사람이 어디에 쓰는지 밝히지 않으면 "
    "WARN(#782 설계 v9). 질문이 학생 자신의 경험·생각을 쓰게 하는 부분은 판정에서 뺀다. story가 "
    "없으면 PASS.\n"
    # #782 설계 v8: 지문 탓이면 미션을 다시 만들어도 못 고침(3·4·5차 미션 검토 51번 중 35번)
    "story.missionMaterial(오늘 지문)은 줄거리가 정한 글이라 미션이 바꿀 수 없다. MATERIAL·"
    "STANDARD_FIT 결함이 그 지문 글 안에 있으면(지문의 수·조건이 서로 맞지 않음, 지문이 글로 할 "
    "수 없는 활동을 시킴 등) reason을 '[지문] '으로 시작한다. 미션이 지문을 바꾸거나 지문 밖에서 "
    "생긴 결함이면 붙이지 않는다.\n"
)


def story_brief(theme: Theme, day: str) -> dict[str, str]:
    """미션 검토 STORY_LINK에 주는 그날 이야기(정답·단서는 넣지 않음)."""
    d = next(x for x in theme["days"] if x["day"] == day)
    brief = {
        "place": d.get("place") or "",
        "target": theme.get("target") or "",
        "discovery": d.get("discovery") or "",
        "missionHook": d.get("missionHook") or "",
        # #782 테마 짜임: 미션 방식과 돕는 사람(STORY_LINK가 방식대로 봄)
        "missionWay": f"{WAY_KO[mission_way(d)]}({mission_way(d)})",
        "helper": d.get("helper") or "",
    }
    if d.get("missionMaterial"):  # #782 줄거리가 정한 그날 미션 지문(예전 저장본에는 없음)
        brief["missionMaterial"] = d["missionMaterial"]
    if story_type(theme).animal:  # #634 ③: 미션 소재가 되는 사건 물건·일
        brief["incident"] = theme.get("incident") or ""
    return brief


def mission_review_user(
    request: MissionDraftRequest,
    draft: Draft,
    grade: int,
    target: str | None,
    knowledge: list[str] | None = None,
    story: dict[str, str] | None = None,
    in_hand: bool = False,
) -> str:
    """미션 하나만 본다(테마 정답·단서 논리는 넣지 않음). story는 STORY_LINK용 그날 장소·증거 발견
    줄·수사 연결 문장. in_hand: 대상이 처음부터 손에 있는 종류(#634 ②)."""
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
        note = "처음부터 손에 든 대상" if in_hand else "이야기에서 아직 찾지 못한 대상"
        body["target"] = f"{target}({note})"
    if story:
        body["story"] = story
    if request.input_type in EXAMPLE_LONG_TYPES:  # #782 설계 v8: 예시 답 문장 수 상한
        body["maxSentences"] = EXAMPLE_SENTENCES[grade]
    return json.dumps(body, ensure_ascii=False)


EXAMPLE_FIX_SYSTEM = (
    "너는 초등 미션의 예시 답만 고쳐 쓰는 출제자다. 질문·생각 열기 질문은 바꾸지 않는다.\n"
    "- 예시 답은 질문이 묻는 것을 하나도 빠짐없이, 질문에 나온 순서대로 답한다. 질문이 여러 "
    "가지를 물으면(예: 처음 생각·바뀐 생각·까닭, 쓰는 법·처리 방법) 각각 분명히 답한다.\n"
    "- 사건(흔적·목격·기록)에 관한 새 사실은 지어내지 않는다. 질문이 요구한 자기 경험·새 생각은 "
    "쓴다. 질문이 쓰라고 한 재료·조건은 모두 쓴다.\n"
    "- 안내(guide)·생각 열기 질문 문장을 그대로 옮기지 않는다(예시 답 유출 검사에 걸림).\n"
    "- 그 학년 학생이 쓸 만한 쉬운 말과 길이로 쓴다(어려운 한자어·어른스러운 낱말은 풀어 씀). "
    "maxSentences가 있으면 그 문장 수 안으로 쓰되 질문이 묻는 것은 모두 담는다(코드 검사 "
    "EXAMPLE_LONG).\n"
    "- 풀이 문제(inputType SOLUTION_STEPS)면 exampleAnswer에 구할 것·방법·계산·확인을 차례로 쓰고 "
    "finalAnswer에 최종 답을 단위 없이 값만 쓴다(단위는 "
    "exampleAnswer에). 풀이가 아니면 finalAnswer는 "
    "null.\n"
    "- 검토 사유를 모두 고친다. reviewReasons에 앞서 고쳐 쓴 뒤에도 나온 사유가 함께 있으면 그것도 "
    "모두 고친다.\n"
    "- 예시 답은 계획·방법 설명이 아니라 질문이 요구한 결과물 자체다. "
    + EXAMPLE_RULES
    + " "
    + TEXT_ONLY
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
    if request.input_type in EXAMPLE_LONG_TYPES:  # #782 테마 짜임: 서술·논술 예시 답 문장 수 상한
        body["maxSentences"] = EXAMPLE_SENTENCES[grade]
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
    "brown feet, no arms (only the tiny hands). Mungchi wears the theme outfit: {outfit}. "
    "Keep Mungchi exactly like the "
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
        "Hats and items worn around the neck are part of the outfit. "
        "No letters, numbers, badges or emblems on the outfit. "
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
    t = story_type(theme)
    if not t.target_visual:  # #634 ④ 시간 탐정: 대상이 '때'라 그릴 것이 없음
        return ""
    if (
        t.target_covered
    ):  # #765 비밀 재료: 엔딩 전 음식은 덮개·도시락 안(콘티 틀 '덮인 음식'과 같게)
        return _covered_target(theme)
    return f"Do not draw {theme.get('target') or 'the missing target'} anywhere in this picture."


def _covered_target(theme: Theme) -> str:
    """비밀 재료 음식(엔딩 전): 덮인 그릇·닫힌 도시락은 보여도 되고 음식 자체·색은 안 보임(#765)."""
    return (
        f"{theme.get('target') or 'The food'} stays covered: only a covered dish or a closed "
        "lunchbox may appear. Never show the food itself or its color."
    )


# 사실표 종류의 후보 이름(영어 지시문용)
FACT_EN = {
    "동물": "animals",
    "선물": "gift items",
    "재료": "ingredients",
    "탈것": "vehicles",
    "소리": "animals or objects",
}


def _no_candidates(theme: Theme) -> str:
    """사실표 종류(동물·선물·재료): 정답 공개 전 그림에 후보가 보이면 답이 보임(#634)."""
    t = story_type(theme)
    if t.facts is None:
        return ""
    if t.facts.image_hide:  # 표가 정함(#634 ④ 시간 탐정: 그림에 시계가 보이면 답이 보임)
        return t.facts.image_hide
    cands = ", ".join(theme.get("candidates") or [])
    return f"Do not draw any of these {FACT_EN.get(t.facts.name, 'candidates')}: {cands}."


def target_in_hand(theme: Theme) -> bool:
    """대상이 처음부터 손에 있는 종류(#634 ②, 미션 검토 target 설명에 씀)."""
    return story_type(theme).target_in_hand


def mission_target(theme: Theme) -> str | None:
    """미션 검토에 줄 대상. 시간 탐정은 대상이 '때'라 '지금 곁에 있으면 결함' 판정에 맞지 않아 주지
    않는다(#634 ④, 시각은 코드 검사 CANDIDATE_NAME·프롬프트가 막음)."""
    if not story_type(theme).target_visual:
        return None
    return theme.get("target")


def mission_shows_target(theme: Theme) -> bool:
    """요일 미션 그림에 대상이 나와도 되는지(그림 검토 targetAllowed).

    대상이 늘 보이는 손에 든 것 종류(출처·선물 상자·길)는 그림 지시가 '손에 들어도 됨'이라 검토도
    같게 하고, 시간 탐정은 그릴 대상이 없어 참(#634 — 전에는 늘 거짓이라 손에 든 대상을 그리면 그림
    검토 ANSWER_HINT와 어긋났음)."""
    t = story_type(theme)
    return (t.target_in_hand and t.target_cuts == ALL_CUTS) or not t.target_visual


def target_lines(theme: Theme, scene: str, index: int) -> list[str]:
    """시작·종료 컷 그림의 대상·후보 규칙(종류별 target_cuts·answer_cuts, #634)."""
    t = story_type(theme)
    shows = cut_shows_target(theme, scene, index)
    if t.animal:  # 대상 = 정답 동물
        if shows:
            return [f"{_answer_animal(theme)} Draw it the same in every picture. No other animals."]
        return [_no_target(theme), _no_candidates(theme)]
    lines = []
    if not t.target_visual:  # #634 ④ 시간 탐정: 대상 지시 없음(시계 금지는 아래 후보 줄)
        pass
    elif shows and t.target_in_hand and not cut_has_characters(scene, index):
        # 뭉치 혼자 출동하는 컷: 대상을 들 사람이 없어 뭉치가 들게 그려짐(그림·영상 실측 선물 상자
        # 시작 3컷, 영상 검토 CONTINUITY "뭉치가 사건 대상을 들고 있음"). 이 컷에는 대상을 그리지
        # 않음
        lines.append(
            f"Do not draw {theme.get('target') or 'the target'} in this picture; Mungchi holds "
            "nothing."
        )
    elif shows and t.code == "GIFT" and (scene, index) not in t.answer_cuts:
        lines.append(
            f"{theme.get('target') or 'The gift box'}: a plain square gift box with a ribbon, the "
            "same in every picture, closed (do not show what is inside), with no tag, card or "
            "label."
        )
    elif shows:
        lines.append(f"{theme.get('target') or 'The missing target'} may appear as the scene says.")
    else:
        lines.append(_no_target(theme))
    if t.facts is not None:
        if (scene, index) not in t.answer_cuts:
            lines.append(_no_candidates(theme))
        elif t.facts.drawable and t.needs_answer_look:  # #634 ⑤ 정답 모습 고정
            lines.append(f"{_answer_look(theme)} Draw it the same in every picture.")
        elif t.facts.drawable:
            lines.append(f"The answer, {theme.get('answer') or ''}, may appear as the scene says.")
    return lines


def _answer_look(theme: Theme) -> str:
    """정답 모습(answerLook)이 필수인 종류의 정답(소리 탐정의 동물·물건, #634 ⑤)."""
    answer, look = theme.get("answer") or "", theme.get("answerLook") or ""
    return f"The answer, {answer}, looks like this (Korean): {look}."


def _answer_animal(theme: Theme) -> str:
    """동물 주인공 가족의 정답 동물 모습(종료 2~4컷 그림·영상이 같은 모습으로, #634 answerLook)."""
    answer, look = theme.get("answer") or "", theme.get("answerLook") or ""
    return f"The animal {answer} looks like this (Korean): {look}."


# 그날 증거 종류별로 그림·살펴보기에서 보여 줄 것(찾는 대상 자체는 증거가 아님, 점검 C2·C3)
EVIDENCE_EN = {
    "TRACE": "the place or object where the trace was left",
    "RECORD": "the photo or record object",
    "SIGHTING": "the person who saw it",
}


def evidence_kind(day: dict) -> str:
    return str((day.get("evidence") or {}).get("kind") or "")


def cut_reveals_answer(scene: str) -> bool:
    """정답 장소를 보여 줘도 되는 컷: 종료 콘티(정답 공개 뒤)."""
    return scene == "OUTRO"


def mission_image_prompt(theme: Theme, day: str, draft: Draft, feedback: list[str]) -> str:
    """요일 미션 그림: 스타일·뭉치·인물·그날 장면 + 그날 증거(수사 날) 또는 돕는 사람(부탁·함께
    발견 날) + 미션 질문·생각 열기 질문.
    """
    d = next(x for x in theme["days"] if x["day"] == day)
    hints = " / ".join(h for h in draft.hints if h.strip())
    t = story_type(theme)
    # #782 설계 v3: 관리실에 맡겨 둔 대상은 요일 그림에서 손에 들지 않음
    shown = t.target_in_hand and t.target_cuts == ALL_CUTS and not kept_target(theme)
    about = (
        f"{theme.get('target') or ''} may appear in the characters' hands."
        if shown
        else f"{theme.get('target') or 'The missing target'} itself is not the evidence; do not "
        "draw it."
        if t.target_visual
        else ""
    )
    lines = [
        IMAGE_STYLE,
        MUNGCHI_LOOK.format(outfit=theme["outfit"]),
        _characters(theme),
        f"Scene (Korean): 장소 {d['place']}. {d['sceneNote']}",
        # #782 테마 짜임: 부탁 날은 문제 전 장면에 그날 돕는 사람과 그 일을 그리고 단서가
        # 나오는 증거는 그리지 않음(문제를 마친 뒤 단서로 나옴), 수사 날만 증거를 보이게
        f"Today's evidence (Korean): {d['discovery']}. Draw "
        f"{EVIDENCE_EN.get(evidence_kind(d), 'the evidence')} clearly visible. {about}".strip()
        if d.get("discovery") and mission_way(d) == INVESTIGATE
        else (
            f"Today's helper (Korean): {d.get('helper') or ''}, busy with their own task in this "
            "scene. Do not draw any clue or trace about the case."
            if d.get("helper")
            else ""
        ),
        "Today's question for the student (Korean). Every object or place the question and the "
        f"thinking prompts point to must be visible in the picture: {draft.question}",
        f"Thinking prompts (Korean): {hints}" if hints else "",
        # 손에 든 것(#634 ②)은 대상이 늘 보이는 종류만 그림(선물 상자는 닫힌 채, 비밀 재료 음식은
        # 물든 색이 답이라 그리지 않음)
        (
            "The gift box stays closed (do not show what is inside) and has no tag, card or label."
            if shown and t.code == "GIFT"
            else ""
        )
        if shown
        else _no_target(theme),
        _no_candidates(theme),
        IMAGE_RULES,
        *_fixes(feedback),
    ]
    return "\n".join(x for x in lines if x)


def cut_shows_target(theme: Theme, scene: str, index: int) -> bool:
    """찾는 대상(③은 정답 동물)이 나와도 되는 컷(#634 종류별 families.target_cuts).

    잃어버린 것: 시작 1컷(주인이 지닌 모습)·종료 3·4컷, 보물 쪽지: 종료 3·4컷,
    동물 주인공: 종료 2~4컷.
    """
    return (scene, index) in story_type(theme).target_cuts


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
    lines += [x for x in target_lines(theme, scene, index) if x]
    lines += [IMAGE_RULES, *_fixes(feedback)]
    return "\n".join(lines)


# #765 비밀 재료: 엔딩 전 음식은 덮개·도시락 안으로 나오는 틀(그림·영상 지시 _covered_target과 같게)
COVERED_REVIEW = (
    "storyType이 비밀 재료(SECRET_INGREDIENT)면 targetAllowed false인 그림에서 덮개를 덮은 "
    "접시·닫힌 도시락만 보이는 것은 찾는 대상이 보이는 것이 아니다(음식 자체나 그 색이 보이면 "
    "결함)."
)

IMAGE_REVIEW_SYSTEM = (
    "너는 초등학생 학습 서비스의 그림 검토자다. 첫 그림이 검토할 그림이고, 두 번째 그림은 "
    "주인공 뭉치의 기준 모습(테마 옷)이다. 주어진 항목(items)마다 verdict를 PASS(문제 없음)·"
    "WARN(애매해서 사람이 볼 것)·FAIL(분명한 결함, 다시 그려야 함) 중 하나로 쓰고 근거 한 "
    "문장(reason)을 쓴다. 주어진 항목을 모두 한 번씩 쓴다. 분명한 결함만 FAIL로 한다.\n"
    "그림에는 글자·숫자를 그리지 않는다(그림 규칙). "
    "그래서 모든 항목에서 물건·장소·인물이 보이는지만 "
    "보고, 적힌 내용·정확한 개수·그림 속 사진이나 종이 "
    "안의 내용, 생각·말·시선처럼 그림으로 보일 수 "
    "없는 것은 판단하지 않는다(그 내용은 문제 글이 준다).\n"
    "storyType이 동물 주인공(PRANK·FOOTPRINT)이면 candidates는 후보 동물이고 정답(answer)은 그중 "
    "한 동물이다. 시간 탐정(WHEN)이면 candidates는 후보 시각이라 정답 공개가 허용되지 않은 그림에 "
    "시계가 보이면 ANSWER_HINT 결함이고 target(그 일을 한 때)은 그릴 것이 없다. 탈것 찾기(VEHICLE)"
    "면 candidates는 후보 탈것이라 정답 공개가 허용되지 않은 그림에 그 탈것이 보이면 결함. 소리 "
    "탐정(SOUND)이면 candidates는 후보 동물·물건이라 정답 공개가 허용되지 않은 그림에 그 가운데 "
    "어느 것이라도 보이면 결함이고 target(밤에 들린 소리)은 그릴 것이 없다.\n"
    "MUNGCHI: 뭉치가 나와야 하는 그림이면 기준 모습과 같은지(크림색 몽글몽글한 몸, 몸 아래쪽 "
    "가운데 얼굴, 흰자 없는 점 눈, 분홍 볼, 작은 손, "
    "갈색 짧은 발, 테마 옷). 손에 든 물건·자세·표정은 "
    "장면에 따라 달라도 된다. 뭉치가 나오지 않아야 하는 그림이면 나오지 않는지.\n"
    "ANSWER_HINT: 찾는 대상이 나오면 안 되는 "
    "그림(targetAllowed false)에 찾는 대상이 보이는지(후보가 동물이면 후보 동물 가운데 어느 "
    "것이라도 보이면 결함). 정답 "
    "공개가 허용되지 않은 그림(answerAllowed "
    "false)에 생각 풍선·화살표처럼 정답(대상이 있는 곳·정답 동물)을 "
    "가리키는 표시가 있는지(장소가 비슷해 보인다는 이유만으로는 결함이 아님). "
    + COVERED_REVIEW
    + "\n"
    "TEXT: 글자·숫자 같은 글이 보이는지(간판·책·표지에 쓴 글 포함).\n"
    "SAFETY: 무섭거나 위험한 모습, 폭력, 실존 인물·상표가 있는지. " + SAFETY_STORY + "\n"
    "SCENE_FIT: 주어진 장면의 장소·인물·하는 일이 그림에 보이는지. 장면 글에 없는 등장인물이 함께 "
    "있는 것은 결함이 아니다. "
    # #765: 대상이 나오면 안 되는 그림은 일부러 대상을 그리지 않음(ANSWER_HINT와 반대로 걸리지 않게)
    "찾는 대상이 나오면 안 되는 그림(targetAllowed false)에서 찾는 대상이나 후보가 보이지 않는 "
    "것은 장면 글에 나와도 결함이 아니다(그 그림에는 일부러 그리지 않음).\n"
    "MISSION_FIT(items에 있을 때만): 미션 질문과 생각 열기 질문이 가리키는 물건·장소와 그날 증거"
    "(evidenceKind가 TRACE면 흔적이 남은 자리·물건, "
    "RECORD면 사진·기록 물건, SIGHTING이면 그것을 본 "
    "사람)가 그림에 보이는지. 찾는 대상 자체는 증거가 아니라 그리지 않는다. "
    # #782 테마 짜임: 부탁 날은 증거를 문제 전에 그리지 않고 돕는 사람을 그림
    "evidenceKind가 비어 있고 helper가 있으면 증거 대신 그 돕는 사람이 그림에 보이는지 본다"
    "(그날 증거는 문제를 마친 뒤 나오므로 보이지 않아도 결함이 아니다).\n"
)


def _story_keys(theme: Theme) -> dict:
    """그림·영상 검토가 정답·후보를 알게(#634: 'answerPlace' → 'answer', 종류·후보 목록)."""
    t = story_type(theme)
    keys: dict = {
        "storyType": f"{t.code}({t.label})",
        "target": theme.get("target") or "",
        "candidates": theme.get("candidates") or [],
        "answer": theme.get("answer") or "",
    }
    if t.needs_answer_look:
        keys["answerLook"] = theme.get("answerLook") or ""
    return keys


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
    evidence: str | None = None,
    helper: str | None = None,
    answer_allowed: bool = False,
) -> str:
    body: dict = {
        "items": list(ids),
        "scene": scene_text,
        "mungchi": "나와야 함" if has_mungchi else "나오지 않아야 함",
        "characters": theme["characters"],
        **_story_keys(theme),
        "targetAllowed": shows_target,
        "answerAllowed": answer_allowed,
    }
    if question is not None:
        body |= {
            "missionQuestion": question,
            "hints": hints or [],
            "discovery": discovery or "",
            "evidenceKind": evidence or "",
            "helper": helper or "",
        }
    return json.dumps(body, ensure_ascii=False)


# 사용자 결정 2026-11-15(생성 쪽도 B안): 첫 그림에 든 차림 소품은 그대로 들어도 되고 새 물건을
# 집거나 건네는 것만 막음(검토 CONTINUITY와 같은 기준, "들지 말라"면 첫 그림의 돋보기가 사라짐)
VIDEO_NEGATIVE = (
    "big eyes, eye whites, changing eye shape, body morphing, extra limbs, long arms, wings, "
    "stretched limbs, Mungchi raising hands, Mungchi grabbing or handing over objects, "
    "outfit change, "
    "character leaving the frame, character disappearing, character walking toward the camera, "
    "characters merging, extreme zoom, cropped faces, freeze frame, 3D render, text, "
    "flashing lights, scary, sudden cuts"
)


def video_prompt(theme: Theme, scene: str, index: int, cut: dict, feedback: list[str]) -> str:
    """컷 동작 + 고정 문구(첫 그림만 고정해 그 그림에서 시작). 뭉치·찾는 대상 규칙은 그림과 같은
    컷 판정(cut_has_mungchi·cut_has_characters·cut_shows_target)을 따른다."""
    target = theme.get("target") or "the missing target"
    if cut_has_mungchi(scene, index):
        mouth = mood_mouth(cut)
        mungchi = [
            "Keep Mungchi's round fluffy shape and small dot eyes unchanged (no eye whites).",
            "Mungchi has only tiny hands at the lower front: no arms, wings or stretched limbs.",
            "Mungchi only bounces gently in place, tilts its head or changes its mouth: it never "
            "waves, raises its hands or points, and never picks up, lifts, hugs, hands over or "
            f"receives anything, especially {target}. An outfit item Mungchi already holds in the "
            "first frame (such as a magnifying glass) stays in its hand as it is. Any hand "
            "gestures are done by the people.",
            "Mungchi's outfit, hat and items around the neck stay exactly as in the first frame.",
            f"Mungchi's expression: {mouth}." if mouth else "",
        ]
    else:
        mungchi = ["Mungchi does not appear in this clip."]
    if not cut_has_characters(scene, index):
        mungchi.append("Only Mungchi is in this clip (no other characters).")
    t = story_type(theme)
    shows = cut_shows_target(theme, scene, index)
    if not t.target_visual:  # #634 ④⑤ 대상(때·소리)은 그릴 것이 없음(후보 감추기는 아래)
        about_target = ""
        if t.facts is not None and t.facts.drawable and (scene, index) in t.answer_cuts:
            about_target = f"{_answer_look(theme)} Keep it looking the same."
            if t.facts.group(str(theme.get("answer") or "")) == "동물":
                about_target += " Nobody touches, lifts or holds the animal; everyone watches it."
    elif t.animal and shows:
        # #634 ③: 정답 동물은 같은 모습, 사람이 제자리에서 부드럽게 안아 올리는 것은 됨
        # (뭉치는 안 됨)
        about_target = (
            f"{_answer_animal(theme)} Keep it looking the same. A person may gently lift it in "
            "place; it does not run away."
        )
    elif scene == "INTRO" and shows and not t.target_in_hand:  # 잃어버린 것 시작 1컷
        about_target = f"{target} may be held or used, but do not show where it is put or hidden."
    elif shows and t.target_in_hand and not cut_has_characters(scene, index):
        about_target = (
            f"Do not show {target}; Mungchi holds nothing."  # 뭉치 혼자 출동 컷(그림과 같게)
        )
    elif shows:
        about_target = (
            "The gift box stays closed, with no tag, card or label."
            if t.code == "GIFT" and (scene, index) not in t.answer_cuts
            else ""
        )
    elif t.target_covered:  # #765 비밀 재료 엔딩 전 컷: 덮인 채로(그림 지시와 같게)
        about_target = _covered_target(theme)
    else:
        about_target = f"Do not show {target}."
    if t.facts is not None and not t.animal and (scene, index) not in t.answer_cuts:
        about_target += " " + _no_candidates(theme).replace("Do not draw", "Do not show")
        about_target = about_target.strip()
    elif t.animal and not shows:
        about_target += " " + _no_candidates(theme).replace("Do not draw", "Do not show")
    lines = [
        f"Action (Korean): {cut['action']}",
        "Keep the 2D cartoon style of the first frame with thick even outlines.",
        *mungchi,
        "Everyone in the first frame stays fully inside the frame until the end: nobody walks "
        "out, disappears, appears or merges with another person.",
        "Small, gentle movements in place, continuous until the end with no pauses. Nobody moves "
        "toward or away from the camera: everyone keeps the same size as in the first frame.",
        "Only a slow, slight camera move; never zoom in so close that someone is cut off. No text.",
        about_target,
        *_fixes(feedback),
    ]
    return "\n".join(x for x in lines if x)


VIDEO_REVIEW_SYSTEM = (
    "너는 초등학생 학습 서비스의 영상 검토자다. 첫 "
    "그림은 컷의 첫 장면(기준)이고, 나머지는 영상에서 "
    "1초마다 뽑은 장면이다. 다섯 항목마다 verdict를 PASS·WARN·FAIL 중 하나로 쓰고 근거 한 문장"
    "(reason)을 쓴다. 다섯 항목을 모두 한 번씩 쓴다. 분명한 결함만 FAIL로 한다.\n"
    "CONTINUITY: 기준 장면의 인물(뭉치 포함)이 끝까지 모두 화면 안에 보이는지(화면 밖으로 나가거나 "
    "사라지거나 둘이 겹쳐 하나가 되거나 얼굴이 크게 "
    "잘리지 않는지), 뭉치의 옷·모자·목에 건 것이 기준 "
    "장면과 같은지, 뭉치에게 팔·날개가 새로 생기지 않는지. "
    # 실측 2026-11-11(초4 종료 3컷): 뭉치가 주인과 함께 로봇을 잡는 영상이 통과함(#535).
    # 사용자 결정 2026-11-15(B안): 결함은 사건 대상 잡기와 팔·날개 생김만, 차림 소품 쥠은 결함 아님
    # (그림 검토 MUNGCHI는 손에 든 물건을 허용해 첫 그림이 통과하는데 영상만 실패하지 않게)
    "뭉치가 사건 대상(target, 찾는 대상 등 이야기 속 물건)을 잡거나 들거나 안거나 건네거나 "
    "받는지(사람과 함께 잡아도 결함). 뭉치가 차림 소품(목에 걸거나 손에 든 돋보기·모자처럼 기준 "
    "장면의 테마 차림)을 쥐거나 지니고 있는 것은 결함이 아니다. 사람이 동물을 제자리에서 "
    "부드럽게 안아 올리는 것은 결함이 아니다(#634 동물 주인공 결말).\n"
    "MORPH: 인물·뭉치의 몸·얼굴·눈 모양이 장면 사이에 녹아내리듯 바뀌거나 팔다리가 늘어나는지, "
    "2D 그림체가 3D로 바뀌는지, 뭉치가 나오지 않아야 하는 컷(mungchi 나오지 않아야 함)에 뭉치가 "
    "나타나는지. 사람이 손에 든 물건·자세와 표정, 뭉치가 쥔 차림 소품은 동작에 따라 달라도 된다"
    "(뭉치가 사건 대상을 잡는 것·팔이나 날개가 생기는 것은 CONTINUITY에서 본다).\n"
    "ANSWER_HINT: 찾는 대상이 나오면 안 되는 컷(targetAllowed false)에 대상이 보이는지(후보가 "
    "동물이면 후보 동물 가운데 어느 것이라도 보이면 결함), 정답 "
    "공개가 허용되지 않은 컷(answerAllowed false)에서 정답(대상이 있는 곳·정답 동물)을 가리켜 "
    "보여 주는지"
    "(장소가 비슷해 보인다는 이유만으로는 결함이 아님). " + COVERED_REVIEW + "\n"
    "TEXT: 글자·숫자가 보이는지.\n"
    "SAFETY: 무섭거나 위험한 모습, 번쩍이는 빛, 폭력이 있는지. " + SAFETY_STORY + "\n"
)


def video_review_user(
    theme: Theme,
    cut: dict,
    shows_target: bool,
    has_mungchi: bool = True,
    answer_allowed: bool = False,
) -> str:
    return json.dumps(
        {
            "scene": cut["scene"],
            "action": cut["action"],
            "mungchi": "나와야 함" if has_mungchi else "나오지 않아야 함",
            **_story_keys(theme),
            "targetAllowed": shows_target,
            "answerAllowed": answer_allowed,
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
    "- spots: dayInfo가 있는 요일 장면만, 문제 전에 학생이 그림에서 눌러 볼 것 2~3개. 정확히 "
    "하나는 그날 증거(evidence true): evidenceKind가 "
    "TRACE면 흔적이 남은 자리·물건, RECORD면 사진·기록 "
    "물건, SIGHTING이면 그것을 본 사람. evidenceKind가 비어 있고 helper가 있으면(부탁·함께 "
    "발견 날, 증거는 문제 뒤에 나옴) 그 돕는 사람(#782). 찾는 대상 "
    "자체는 증거가 아니다. 나머지는 미션 질문·생각 열기 "
    "질문에 나온 물건(evidence false). 그림에 실제로 보이는 것만 고르고 x·y는 그 중심. 서로 떨어진 "
    "서로 다른 물건·사람만 고르고, 한 물건 안의 부분(화면 속 길·자막처럼)은 따로 고르지 않는다. "
    "label은 이름(10자 이내), line은 눌렀을 때 뭉치가 하는 짧은 말(30자 이내). line은 그 "
    "물건에서 학생이 볼 부분·모습이나 확인할 점을 가리킨다(증거는 그 증거에서 살펴볼 곳, 다른 "
    "물건은 미션 질문이 그 물건으로 하게 하는 일). '찾았어!'·'살펴볼까?'처럼 물건 이름만 바꾸면 "
    "어느 물건에나 쓸 말은 쓰지 않는다(#782). "
    "label·line에 avoidWords(단서 결론 낱말·후보 "
    "이름·미션 금지어)와 미션의 값·풀이·답을 쓰지 않는다. dayInfo가 없으면(시작·종료) 빈 목록.\n"
)


def motion_user(
    theme: Theme,
    scene: str,
    scene_text: str,
    speakers: list[str],
    day_info: dict | None = None,
) -> str:
    """day_info: 요일 장면의 살펴보기 재료 {discovery, evidenceKind, helper, missionQuestion, hints}
    (단서는 넣지 않음, 부탁 날은 discovery·evidenceKind가 비고 helper만).
    """
    body: dict = {
        "scene": scene,
        "sceneText": scene_text,
        "styleNote": theme.get("styleNote") or "",
        "speakers": speakers,
    }
    if day_info:
        body["dayInfo"] = day_info
    return json.dumps(body, ensure_ascii=False)
