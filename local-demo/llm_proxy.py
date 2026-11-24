"""Local-only SageMaker facade for the RunPod queue used by the Gemma review."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ENDPOINT = re.fullmatch(
    r"https://api[.]runpod[.]ai/v2/([A-Za-z0-9_-]+)(?:/(?:run|runsync))?/?",
    os.environ["LOCAL_LLM_QUEUE_URL"],
)
if ENDPOINT is None:
    raise RuntimeError("Invalid local RunPod queue configuration")
BASE = f"https://api.runpod.ai/v2/{ENDPOINT[1]}"
KEY = os.environ["LOCAL_LLM_API_KEY"]
MODEL = os.environ.get("LOCAL_LLM_MODEL", "explain")
WAIT_SECONDS = 110


def queue_request(path, payload, deadline):
    request = urllib.request.Request(
        BASE + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
    )
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    with urllib.request.urlopen(request, timeout=min(10, remaining)) as response:
        return json.load(response)


def invoke(body):
    deadline = time.monotonic() + WAIT_SECONDS
    body.update(model=MODEL, stream=False)
    # Submit once. Read-only polling can recover a transient transport or rate-limit error.
    receipt = queue_request(
        "/run",
        {
            "input": {"openai_route": "/v1/chat/completions", "openai_input": body},
            "policy": {"executionTimeout": WAIT_SECONDS * 1000, "ttl": WAIT_SECONDS * 2000},
        },
        deadline,
    )
    job_id = receipt.get("id", "")
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise ValueError("Invalid RunPod receipt")
    while time.monotonic() < deadline:
        time.sleep(min(1, max(0, deadline - time.monotonic())))
        try:
            result = queue_request("/status/" + job_id, None, deadline)
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise
            continue
        except (TimeoutError, urllib.error.URLError):
            continue

        status = result.get("status")
        if status == "COMPLETED":
            output = result.get("output")
            if isinstance(output, list) and len(output) == 1:
                output = output[0]
            if not isinstance(output, dict) or not output.get("choices"):
                raise ValueError("Invalid RunPod completion")
            return output
        if status not in ("IN_QUEUE", "IN_PROGRESS"):
            raise ValueError("RunPod job did not complete")
    raise TimeoutError


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        self._send(200, {"status": "ok"})

    def do_POST(self):
        if not (self.path.startswith("/endpoints/") and self.path.endswith("/invocations")):
            self._send(404, {"message": "not found"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self._send(200, invoke(body))
        except urllib.error.HTTPError as error:
            self._send(424, {"OriginalStatusCode": error.code, "Message": "upstream error"})
        except TimeoutError:
            self._send(424, {"OriginalStatusCode": 504, "Message": "upstream deadline exceeded"})
        except (ValueError, TypeError, urllib.error.URLError):
            self._send(424, {"OriginalStatusCode": 502, "Message": "upstream unavailable"})

    def log_message(self, fmt, *args):
        print(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
