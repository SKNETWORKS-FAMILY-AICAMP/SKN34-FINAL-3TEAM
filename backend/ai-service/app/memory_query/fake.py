"""개발용 가짜 질의 변환 (MEMORY_QUERY_PROVIDER=fake, api-spec 4.2.7).

외부 호출 없이 정해진 규칙으로 변환한다(같은 요청 = 같은 응답). learning(#682)이 실제 LLM 없이
하이브리드 검색을 개발하는 데 쓴다. 사용량을 남기지 않는다.
- keywords: 질문을 공백으로 나눠 앞에서부터 중복을 뺀 5개(각 20자로 자름)
- period: 언제나 null
- search_text: 원문 질문(앞뒤 공백만 뺌)
"""

from app.memory_query.models import KEYWORD_MAX_CHARS, KEYWORDS_MAX, MemoryQueryRequest
from app.memory_query.prompts import GeneratedMemoryQuery

FAKE_MODEL = "fake-memory-query-v1"


def fake_generated(request: MemoryQueryRequest) -> GeneratedMemoryQuery:
    keywords: list[str] = []
    for word in request.query.split():
        keyword = word[:KEYWORD_MAX_CHARS]
        if keyword not in keywords:
            keywords.append(keyword)
        if len(keywords) == KEYWORDS_MAX:
            break
    return GeneratedMemoryQuery(keywords=keywords, period=None, search_text=request.query.strip())
