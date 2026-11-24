"""#884 민감정보 점검: 값은 출력하지 않고 패턴 이름·건수만 출력한다.

사용: python -I scan.py <workdir>
workdir: canaries.json, llm-requests.jsonl, service-logs.txt, payment-test-out.txt, e2e.env
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

w = Path(sys.argv[1])
can = json.loads((w / "canaries.json").read_text(encoding="utf-8"))
env = {}
for line in (w / "e2e.env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
secret_keys = [k for k in env if re.search(r"PASSWORD|TOKEN|SECRET|KEY", k) and k != "PAYMENT_FREE_PRODUCT_ID"]
secrets = {k: env[k] for k in secret_keys if len(env[k]) >= 8}

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
GENERIC = {
    "toss_key_prefix(test_sk_|test_gsk_|test_ck_|live_sk|live_gsk)": re.compile(r"\b(test_sk_|test_gsk_|live_sk_|live_gsk_)\w+"),
    "openai_key(sk-...)": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "jwt(eyJ...)": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    "payment_field(billingKey|customerKey|paymentKey|cardNumber)": re.compile(r"(billingKey|customerKey|paymentKey|cardNumber|card_number)\s*[=:\"]", re.I),
    "card_number_16digits": re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
    "password_assign(password=|\"password\":)": re.compile(r"password\s*[=:]\s*\"?[^\s\",*]{3,}", re.I),
    "pin_value(e2e PIN)": re.compile(r"\b" + re.escape(can["pin"]) + r"\b"),
}


def literal_hits(text, values):
    return sum(text.count(v) for v in values if v)


def scan_text(name, text):
    r = {"source": name, "lines": text.count("\n")}
    r["e2e_env_secret_values"] = {k: text.count(v) for k, v in secrets.items() if text.count(v)}
    r["e2e_env_secret_values_total"] = sum(r["e2e_env_secret_values"].values())
    for label, rx in GENERIC.items():
        r[label] = len(rx.findall(text))
    r["student_answer_text"] = literal_hits(text, can["answer_texts"])
    r["student_nickname"] = literal_hits(text, can["nicknames"])
    r["guardian_login_or_display_name"] = literal_hits(text, can["guardian_names"])
    r["student_id"] = literal_hits(text, can["student_ids"])
    r["attempt_id"] = literal_hits(text, can["attempt_ids"])
    r["answer_id"] = literal_hits(text, can["answer_ids"])
    return r


out = {"secret_value_keys_checked": sorted(secrets), "canary_counts": {k: len(v) for k, v in can.items() if isinstance(v, list)}}

# SEC-03: 외부 LLM 요청 본문
reqs = [json.loads(l) for l in (w / "llm-requests.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
by_schema = Counter((r["path"].split("/")[1] if r["path"].startswith("/endpoints") else "chat", r["schema"] or "stream(analysis answer)") for r in reqs)
id_keys = re.compile(r"\"(studentId|attemptId|answerId|childId|student_id|attempt_id|answer_id|nickname|studentName|name|displayName)\"\s*:")
llm = {"requests": len(reqs), "by_route_schema": {f"{a}:{b}": n for (a, b), n in sorted(by_schema.items())}}
per = []
for r in reqs:
    text = "\n".join(m.get("content", "") if isinstance(m.get("content"), str) else json.dumps(m.get("content"), ensure_ascii=False) for m in r["body"].get("messages", []))
    uuids = set(UUID.findall(text))
    per.append({
        "schema": r["schema"],
        "message_roles": [m.get("role") for m in r["body"].get("messages", [])],
        "top_level_keys": sorted(r["body"].keys()),
        "id_like_keys_in_messages": len(id_keys.findall(text)),
        "student_id": literal_hits(text, can["student_ids"]),
        "attempt_id": literal_hits(text, can["attempt_ids"]),
        "answer_id": literal_hits(text, can["answer_ids"]),
        "student_nickname": literal_hits(text, can["nicknames"]),
        "guardian_login_or_display_name": literal_hits(text, can["guardian_names"]),
        "uuid_total": len(uuids),
        "uuid_rubric_element": len(uuids & set(can["rubric_element_ids"])),
        "uuid_other": len(uuids - set(can["rubric_element_ids"])),
        "contains_student_answer_text": literal_hits(text, can["answer_texts"]) > 0,
    })
llm["requests_detail"] = per
llm["totals"] = {k: sum(p[k] for p in per) for k in ["id_like_keys_in_messages", "student_id", "attempt_id", "answer_id", "student_nickname", "guardian_login_or_display_name", "uuid_rubric_element", "uuid_other"]}
out["sec03_llm_requests"] = llm

out["sec05_service_logs"] = scan_text("docker compose logs (서비스만)", (w / "service-logs.txt").read_text(encoding="utf-8", errors="replace"))
pay = (w / "payment-test-out.txt").read_text(encoding="utf-8", errors="replace")
out["sec06_payment_test_output"] = scan_text("core payment 패키지 테스트 system-out", pay)
# 테스트 대역이 쓰는 합성 PG 키 값(paymentKey "synthetic-…", 시크릿 "test_sk_…"·"test_gsk_…")
out["sec06_payment_test_output"]["pg_fake_key_literals(synthetic-|test_sk_|test_gsk_)"] = sum(pay.count(v) for v in ["synthetic-", "test_sk_", "test_gsk_"])
(w / "scan-result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
