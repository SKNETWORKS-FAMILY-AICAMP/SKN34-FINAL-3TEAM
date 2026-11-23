"""낱말 물어보기 흐름 (#599): 표제어·사전·뜻 고르기·유출 검사·대체 응답·사용량. 사전은 가짜 HTTP."""

import asyncio
import json
import logging

import httpx
import openai
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import ApiError
from app.llm.base import LlmError
from app.prompt_versions.registry import ActiveVersions
from app.word_help.dictionary import Dictionary
from app.word_help.models import WordHelpRequest, WordHelpResponse
from app.word_help.prompts import GeneratedHeadword, GeneratedWordHelp
from app.word_help.service import WordHelpService
from app.word_help.web_search import WordWebSearch
from tests.fakes import FakeLlm

SECRET = "test-dict-key-should-not-leak"
STD = {
    "분수": [
        ("분수^", "서로 작별함."),
        ("분수", "정수 <I>a</I>를 0이 아닌 정수 b로 나눈 몫을 a/b로 표시한 것."),
        ("분수", "압력으로 좁은 구멍을 통하여 물을 위로 세차게 내뿜는 설비."),
    ],
    "증발": [("증발", "어떤 물질이 액체 상태에서 기체 상태로 변함. 또는 그런 현상.")],
    "질리다": [("질리다", "놀라거나 두려워서 기가 막히다.")],
}
ONYONG = {
    "증발": [
        ("증발", "액체로부터 기체로 상이 변하는 것.", "4"),
        ("증발", "액체가 기체로 되는 현상.", "1"),
    ],
    "기화": [("기화", "액체가 기체로 변하는 현상.", "4")],
    "감지기": [
        ("감지기", "표시 없음.", ""),
        ("감지기", "비상업만 허용.", "2"),
        ("감지기", "변경할 수 없음.", "3"),
    ],
}
MISSION = "피자 한 판을 똑같이 4조각으로 나누어 1조각을 먹었어요. 먹은 양을 분수로 나타내 보세요."


class Calls:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.fail = False


def transport(calls: Calls) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.urls.append(str(request.url))
        if calls.fail:
            return httpx.Response(500)
        q = request.url.params
        if request.url.host == "std.test":
            items = [
                {"word": w, "sup_no": "1", "pos": "명사", "sense": {"definition": d}}
                for w, d in STD.get(q["q"], [])
            ]
            return httpx.Response(
                200, text=json.dumps({"channel": {"item": items}}) if items else ""
            )
        rows = [
            {
                "word": w,
                "definition": d,
                "category_sub": "물리학",
                "kr_gvrn_lcns_ty": lic,
                "glossary": "시험 용어집",
                "source": "시험 기관",
            }
            for w, d, lic in ONYONG.get(q["apiSearchWord"], [])
        ]
        return httpx.Response(200, json={"channel": {"return_object": [{"resultlist": rows}]}})

    return httpx.MockTransport(handle)


def make(
    llm: FakeLlm,
    calls: Calls | None = None,
    web_search: WordWebSearch | None = None,
    **settings: object,
) -> WordHelpService:
    calls = calls or Calls()
    dictionary = Dictionary(
        "https://std.test/api/search.do",
        SECRET,
        "https://on.test/api/search.do",
        SECRET,
        transport=transport(calls),
    )
    settings_obj = Settings(**settings)  # type: ignore[arg-type]
    return WordHelpService(llm, dictionary, settings_obj, ActiveVersions(), web_search)


def body(
    question: str = "분수가 뭐야?", leak: dict | None = None, mission: str = MISSION
) -> WordHelpRequest:
    data: dict = {"question": question, "missionText": mission, "grade": 3, "subject": "수학"}
    if leak is not None:
        data["leak"] = leak
    return WordHelpRequest.model_validate(data)


def run(service: WordHelpService, request: WordHelpRequest) -> WordHelpResponse:
    return asyncio.run(service.help(request))


EXPLAIN = GeneratedWordHelp(
    kind="WORD",
    sense=1,
    easy="분수는 똑같이 나눈 것 중 몇 조각인지 나타낸 수야.",
    example="귤 3조각 중 1조각은 3분의 1이야.",
)


def test_헤드워드를_LLM이_고르고_맞는_뜻을_쉬운_말로_답하며_원문과_출처를_준다():
    llm = FakeLlm(GeneratedHeadword(headword="분수"), EXPLAIN)
    out = run(make(llm), body())
    assert out.state == "EXPLAINED" and out.headword == "분수"
    assert out.text == EXPLAIN.easy and out.example == EXPLAIN.example
    assert [(s.source, s.definition) for s in out.senses] == [
        ("표준국어대사전", "정수 a를 0이 아닌 정수 b로 나눈 몫을 a/b로 표시한 것.")
    ]
    assert out.versions.prompt == "word-help@1" and out.versions.model == "fake-model"
    assert [u.call_type for u in llm.usages] == ["WORD_HELP", "WORD_HELP"]
    user = llm.requests[1].user
    assert "0. (표준국어대사전·명사) 서로 작별함." in user and "<I>" not in user  # HTML 조각 제거
    assert "학년: 초3" in user and MISSION in user


def test_한_낱말이고_사전에_있으면_표제어_LLM을_부르지_않는다():
    calls = Calls()
    llm = FakeLlm(EXPLAIN)
    out = run(make(llm, calls), body("분수"))
    assert out.state == "EXPLAINED" and len(llm.requests) == 1
    assert [httpx.URL(url).host for url in calls.urls] == ["std.test"]


def test_낱말_질문이_아니면_범위_밖():
    out = run(make(FakeLlm(GeneratedHeadword(headword=""))), body("이 문제 답 그냥 알려 줘"))
    assert out.state == "OUT_OF_SCOPE" and out.senses == [] and out.headword is None
    out = run(
        make(FakeLlm(GeneratedWordHelp(kind="OUT_OF_SCOPE", sense=-1, easy="", example=""))),
        body("분수"),
    )
    assert out.state == "OUT_OF_SCOPE"


def test_맞는_뜻이_없거나_사전에_없으면_찾지_못함():
    out = run(
        make(FakeLlm(GeneratedWordHelp(kind="WORD", sense=-1, easy="", example=""))), body("질리다")
    )
    assert out.state == "NOT_FOUND" and out.headword == "질리다" and out.senses == []
    out = run(make(FakeLlm(GeneratedHeadword(headword="없는말"))), body("없는말이 뭐야"))
    assert out.state == "NOT_FOUND" and out.headword == "없는말"


def test_마무리_전_정답_키와_겹치는_낱말은_사전도_LLM도_없이_미룬다():
    calls = Calls()
    llm = FakeLlm()
    out = run(make(llm, calls), body("증발이 뭐야?", leak={"answerKey": ["증발"]}))
    assert out.state == "DEFERRED" and llm.requests == [] and calls.urls == []
    assert out.versions.model is None and "다 풀고" in out.text


def test_설명이나_사전_원문에_정답_키가_나오면_미룬다():
    llm = FakeLlm(
        GeneratedWordHelp(
            kind="WORD", sense=0, easy="증발은 물이 기체로 바뀌는 거야.", example="물이 증발했어."
        )
    )
    out = run(make(llm), body("증발", leak={"answerKey": ["수증기"], "forbiddenTerms": ["기체"]}))
    assert out.state == "DEFERRED" and out.senses == []


def test_마무리_뒤에는_유출_검사를_하지_않는다():
    llm = FakeLlm(
        GeneratedWordHelp(
            kind="WORD", sense=0, easy="증발은 물이 기체로 바뀌는 거야.", example="물이 증발했어."
        )
    )
    assert run(make(llm), body("증발")).state == "EXPLAINED"


def test_표준국어대사전에서_맞는_뜻이_없으면_허용된_온용어를_사용한다():
    calls = Calls()
    llm = FakeLlm(
        GeneratedWordHelp(kind="WORD", sense=-1, easy="", example=""),
        GeneratedWordHelp(kind="WORD", sense=0, easy="증발은 물이 날아가는 거야.", example=""),
    )
    out = run(make(llm, calls), body("증발"))
    user = llm.requests[1].user
    assert [httpx.URL(url).host for url in calls.urls] == ["std.test", "on.test"]
    assert "상이 변하는 것" not in user and "액체가 기체로 되는 현상." in user
    assert out.state == "EXPLAINED" and out.senses[0].source == "온용어"
    assert out.senses[0].attribution == "시험 용어집 / 시험 기관"


@pytest.mark.parametrize("word", ["기화", "감지기"])
def test_제한되거나_조건이_불명확한_온용어는_원문과_모델_후보에서_제외한다(word: str):
    llm = FakeLlm(GeneratedHeadword(headword=word))
    out = run(make(llm), body(word))
    assert out.state == "NOT_FOUND" and out.senses == []
    assert len(llm.requests) == 1


@pytest.mark.parametrize("allowed", [True, False])
def test_대체_검색은_공식_상세_페이지에서_허용된_뜻만_사용한다(allowed: bool):
    entry = "https://kli.korean.go.kr/term/trgtWord/indexTrgtWord.do?trgtWordNo="
    openai_requests = []
    visited = []

    def search(request: httpx.Request) -> httpx.Response:
        openai_requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "output": [
                    {
                        "id": "ws_test",
                        "type": "web_search_call",
                        "status": "completed",
                        "action": {
                            "type": "search",
                            "sources": [
                                {"type": "url", "url": url}
                                for url in (
                                    entry + "1",
                                    entry + "2",
                                    entry + "3",
                                    entry.replace("kli.korean.go.kr", "external.test") + "4",
                                )
                            ],
                        },
                    }
                ],
            },
        )

    def page(request: httpx.Request) -> httpx.Response:
        ident = request.url.params["trgtWordNo"]
        visited.append(ident)
        title = "응결" if ident == "3" else "기화"
        accepted = allowed and ident == "2"
        rights = (
            "저작자표시-동일조건변경허락 2.0 대한민국"
            if accepted
            else "이 용어 정보는 공공누리 4유형 조건에 따라 이용할 수 있습니다."
        )
        definition = "허용된 뜻풀이" if accepted else "제한된 뜻풀이"
        return httpx.Response(
            200,
            text=f'<h2 class="trgtWord">{title}</h2>'
            '<div class="cont_src_dl"><dl><dt>출처</dt><dd>우리말샘 / 국립국어원</dd></dl></div>'
            f'<div class="kogl_type"><span>{rights}</span></div>'
            f'<p class="mean">{definition}<br>《우리말샘》</p>',
        )

    async def scenario() -> WordHelpResponse:
        async with (
            httpx.AsyncClient(transport=httpx.MockTransport(search)) as openai_http,
            httpx.AsyncClient(transport=httpx.MockTransport(page)) as source_http,
            openai.AsyncOpenAI(api_key="test", http_client=openai_http) as client,
        ):
            service = make(llm, web_search=WordWebSearch(client, source_http))
            return await service.help(body("기화"))

    llm = FakeLlm(
        GeneratedHeadword(headword="기화"),
        GeneratedWordHelp(kind="WORD", sense=0, easy="액체가 기체로 바뀌는 거야.", example=""),
    )
    out = asyncio.run(scenario())
    assert sorted(visited) == ["1", "2", "3"]
    assert len(openai_requests) == 1 and openai_requests[0]["input"] == "기화"
    assert openai_requests[0]["store"] is False
    assert openai_requests[0]["tools"][0]["filters"]["allowed_domains"] == ["kli.korean.go.kr"]
    if allowed:
        assert out.state == "EXPLAINED"
        assert out.senses[0].definition == "허용된 뜻풀이"
        assert out.senses[0].source_url == entry + "2"
        assert out.senses[0].license == "https://creativecommons.org/licenses/by-sa/2.0/kr/"
        assert "제한된 뜻풀이" not in llm.requests[-1].user
    else:
        assert out.state == "NOT_FOUND" and out.senses == []
        assert len(llm.requests) == 1


def test_설명_LLM이_실패하면_사전_원문만_돌려준다():
    llm = FakeLlm(LlmError("LLM_TIMEOUT", retryable=True))
    out = run(make(llm), body("분수"))
    assert out.state == "DICTIONARY_ONLY" and len(out.senses) == 3
    assert all(s.source == "표준국어대사전" for s in out.senses)


def test_설명_번호가_범위_밖이면_사전_원문만():
    out = run(
        make(FakeLlm(GeneratedWordHelp(kind="WORD", sense=9, easy="x", example=""))), body("분수")
    )
    assert out.state == "DICTIONARY_ONLY"


def test_표제어_LLM이_실패하면_조사를_뗀_글자로_사전을_찾아_본다():
    llm = FakeLlm(LlmError("LLM_TIMEOUT", retryable=True), EXPLAIN)
    out = run(make(llm), body("분수가 뭐야?"))
    assert out.state == "EXPLAINED" and out.headword == "분수"
    with pytest.raises(ApiError) as caught:
        run(make(FakeLlm(LlmError("LLM_TIMEOUT", retryable=True))), body("솟아올랐어요가 뭐야"))
    assert caught.value.status == 503 and caught.value.code == "AI_UNAVAILABLE"


def test_사전_장애는_503이고_키를_로그에_남기지_않는다(caplog: pytest.LogCaptureFixture):
    calls = Calls()
    calls.fail = True
    with caplog.at_level(logging.DEBUG), pytest.raises(ApiError) as caught:
        run(make(FakeLlm(), calls), body("분수"))
    assert caught.value.status == 503 and caught.value.code == "DICTIONARY_UNAVAILABLE"
    assert caught.value.extra["retryable"] is True
    assert SECRET not in caplog.text and "분수" not in caplog.text


def test_사전이_미설정이면_503():
    service = WordHelpService(FakeLlm(), Dictionary("", "", "", ""), Settings(), ActiveVersions())  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        run(service, body("분수"))
    assert caught.value.code == "DICTIONARY_UNAVAILABLE"


def test_사전_결과는_표제어_단위로_캐시한다():
    calls = Calls()
    service = make(FakeLlm(EXPLAIN, EXPLAIN), calls)
    run(service, body("분수"))
    first = len(calls.urls)
    run(service, body("분수"))
    assert len(calls.urls) == first


def test_가짜_구현은_LLM없이_첫_뜻으로_답한다():
    llm = FakeLlm()
    out = run(make(llm, word_help_provider="fake"), body("분수가 뭐야?"))
    assert (
        out.state == "EXPLAINED"
        and out.text == "분수는 서로 작별함라는 뜻이야."
        and llm.requests == []
    )
    assert out.versions.model == "fake-word-help-v1"


def test_요청_칸_검사():
    for bad in ({"question": " "}, {"question": "가" * 101}, {"grade": 7}, {"studentName": "x"}):
        data = {"question": "분수", "missionText": MISSION, "grade": 3, "subject": "수학", **bad}
        with pytest.raises(ValidationError):
            WordHelpRequest.model_validate(data)
