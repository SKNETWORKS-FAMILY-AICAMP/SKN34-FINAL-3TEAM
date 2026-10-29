"""#52-permitted AI fixture only. Does not invent a core nickname endpoint."""

from fastapi import FastAPI, HTTPException, Request

app = FastAPI()
mode = "valid"
calls = []


@app.post("/test/mode/{value}")
async def change_mode(value: str):
    global mode
    if value not in {"valid", "mismatch", "unavailable"}:
        raise HTTPException(400)
    mode = value
    calls.clear()
    return {"mode": mode}


@app.get("/test/calls")
async def captured():
    return calls


@app.post("/internal/report-narratives")
async def narrative(request: Request):
    if request.headers.get("X-Internal-Token") != "report56-test-only":
        raise HTTPException(401)
    if request.headers.get("X-User-Role") != "SYSTEM":
        raise HTTPException(403)
    calls.append({"body": await request.json(), "scope": request.headers.get("X-Student-Scope")})
    if mode == "unavailable":
        raise HTTPException(503, "synthetic outage")
    return {
        "narrative": {
            "text": "답변 제출 시도 999건입니다."
            if mode == "mismatch"
            else "답변 제출 시도 1건입니다.",
            "source": "LLM",
            "modelExplanation": None,
        },
        "eveningQuestion": "어떤 생각이 기억에 남니?",
        "citedQuotes": [],
        "versions": {"prompt": "synthetic-report@1", "model": "synthetic-model@1"},
    }
