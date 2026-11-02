"""M1 풀이 점검 모델: 모델 구조(학습·평가 공용) + 오프라인 평가용 불러오기(evaluate.py).

입력: 문제 + 모범 정답 + 학생 풀이 (mathtext.model_input 형식)
출력: 정답 여부, 필수 과정 실수 여부, 계산 정확도 클래스와 각 확률. 실수 '위치'는 내지 않는다.

models/ 에 m1.pt · meta.json · config.json · 토크나이저가 있고 torch·transformers가 설치돼 있을 때만
available()이 True. 서비스 추론은 scoring-service 담당(#88)이라
로컬 MVP 앱 연결(1건 예측 predict)은 옮기지 않음(#263).
"""

import json
from functools import lru_cache
from pathlib import Path

from common import MODEL_DIR
from mathtext import model_input


def build_model(encoder, n_calc):
    """인코더 하나 + 출력 3개. train.py와 평가(_load)가 같은 구조를 쓴다."""
    from torch import nn

    class M1(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc = encoder
            h = encoder.config.hidden_size
            self.drop = nn.Dropout(0.1)
            self.head_correct = nn.Linear(h, 2)
            self.head_req = nn.Linear(h, 2)
            self.head_calc = nn.Linear(h, n_calc)

        def forward(self, input_ids, attention_mask, token_type_ids=None):
            kw = {"input_ids": input_ids, "attention_mask": attention_mask}
            # klue/roberta-base는 문장 구분 임베딩이 1종류뿐(type_vocab_size=1)인데 토크나이저는
            # 두 번째 문장에 1을 붙인다 → 그대로 넣으면 IndexError. 지원하는 모델에만 넣는다.
            if token_type_ids is not None and getattr(self.enc.config, "type_vocab_size", 1) > 1:
                kw["token_type_ids"] = token_type_ids
            x = self.drop(self.enc(**kw).last_hidden_state[:, 0])
            return self.head_correct(x), self.head_req(x), self.head_calc(x)

    return M1()


def available(model_dir=None):
    d = Path(model_dir or MODEL_DIR)
    if not all((d / f).exists() for f in ("m1.pt", "meta.json", "config.json")):
        return False
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


def meta(model_dir=None):
    return json.loads((Path(model_dir or MODEL_DIR) / "meta.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=2)
def _load(model_dir=None):
    import torch
    from transformers import AutoConfig, AutoModel, AutoTokenizer

    d = Path(model_dir or MODEL_DIR)
    info = meta(d)
    tok = AutoTokenizer.from_pretrained(d)
    enc = AutoModel.from_config(AutoConfig.from_pretrained(d))  # 인터넷 없이 저장된 설정으로
    model = build_model(enc, len(info["calc_classes"]))
    model.load_state_dict(torch.load(d / "m1.pt", map_location="cpu"))
    model.eval()
    return tok, model, info


def predict_many(items, model_dir=None, batch_size=32):
    """items: [(question, reference_answer, solution), ...]
    또는 [(input_a, input_b), ...] (이미 변환된 경우)."""
    import torch

    tok, model, info = _load(model_dir)
    pairs = [model_input(*it) if len(it) == 3 else tuple(it) for it in items]
    out = []
    for i in range(0, len(pairs), batch_size):
        a, b = zip(*pairs[i : i + batch_size], strict=False)
        enc = tok(
            list(a),
            list(b),
            truncation="longest_first",
            max_length=info["max_len"],
            padding=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            lc, lr_, lk = model(
                **{
                    k: v
                    for k, v in enc.items()
                    if k in ("input_ids", "attention_mask", "token_type_ids")
                }
            )
        pc, pr, pk = (torch.softmax(x, -1) for x in (lc, lr_, lk))
        for j in range(len(a)):
            k = int(pk[j].argmax())
            out.append(
                {
                    "is_correct": bool(pc[j, 1] >= pc[j, 0]),
                    "p_correct": float(pc[j].max()),
                    "has_required_error": bool(pr[j, 1] >= pr[j, 0]),
                    "p_required": float(pr[j].max()),
                    "calc_accuracy": info["calc_classes"][k],
                    "p_calc": float(pk[j, k]),
                    "version": info.get("version", "m1"),
                }
            )
    return out
