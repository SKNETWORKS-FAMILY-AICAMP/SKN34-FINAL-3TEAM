"""ai-service 실제 프롬프트로 가상 입력 요청 본문을 만든다(학생 실제 글 없음)."""
import copy, json, sys
from pathlib import Path
root = Path(sys.argv[1]); sys.path.insert(0, str(root))
from app.llm.providers import strict_schema
from app.report_narrative import prompts as np_
from app.report_narrative.models import NarrativeRequest
from app.report_explanation import prompts as ep
from app.report_explanation.models import ExplanationDetail
from tests.report_narrative.test_service import BODY

body = copy.deepcopy(BODY)
body["thinkingTypes"] = [
    {"type": "ANALYZE", "state": "OK", "missions": [{"attemptId": "t-7", "title": "쉬는 시간"}]},
    {"type": "EVALUATE", "state": "OK", "missions": [{"attemptId": "t-8", "title": "급식 남기기"}]},
    {"type": "CREATE", "state": "NO_RECORD"},
    {"type": "SOLVE", "state": "OK", "missions": [{"attemptId": "t-9", "title": "교실 화분 물 주기"}]},
    {"type": "REFLECT", "state": "NO_RECORD"},
]
req = NarrativeRequest.model_validate(body)

TEXT = ("우리 반은 교실 화분 물 주기를 번갈아 하기로 했다. 처음에는 아무도 순서를 정하지 않아서 "
        "어떤 날은 물을 두 번 주고 어떤 날은 아무도 주지 않았다. 그래서 잎이 노랗게 변한 화분도 있었다. "
        "나는 칠판 옆에 당번표를 붙이자고 했다. 당번표가 있으면 누가 언제 물을 줄지 한눈에 볼 수 있기 때문이다. "
        "또 물을 준 사람은 이름 옆에 동그라미를 그리면 같은 날 두 번 주는 일도 막을 수 있다. "
        "친구들은 처음에 귀찮다고 했지만 일주일 동안 해 보니 화분 잎이 다시 초록색이 되었다. "
        "나는 작은 약속이라도 눈에 보이게 정해 두면 모두가 지키기 쉬워진다고 생각한다. "
        "다음에는 주말에 물을 어떻게 줄지도 친구들과 이야기해 보고 싶다.")
TOPIC = "우리 반에서 생긴 작은 문제를 하나 고르고, 어떻게 해결하면 좋을지 까닭을 들어 써 보세요."

def chat(system, user, output, max_tokens, model):
    schema = strict_schema(output)
    return {"model": model, "messages": [
        {"role": "system", "content": system + "\n아래 스키마를 따르는 JSON 객체 하나만 출력하세요."
         " 설명이나 코드 블록은 쓰지 마세요.\n" + json.dumps(schema, ensure_ascii=False)},
        {"role": "user", "content": user}],
        "max_tokens": max_tokens, "temperature": 0, "stream": False,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": output.__name__, "schema": schema, "strict": True}}}

out = {
  "narrative": chat(np_.SYSTEM, np_.build_user(req), np_.GeneratedNarrative, 2048, "MODEL"),
  "explanation": chat(ep.SYSTEM, ep.build_user(5, TOPIC, TEXT), ExplanationDetail, 4096, "MODEL"),
  "explanation_text": TEXT,
  "versions": {"narrative": np_.PROMPT_VERSION, "explanation": ep.PROMPT_VERSION},
}
Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print({k: len(json.dumps(v, ensure_ascii=False)) for k, v in out.items()})
