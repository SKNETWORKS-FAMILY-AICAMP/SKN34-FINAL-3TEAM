"""Run real core/learning JARs with disposable PostgreSQL and an AI HTTP double.

Requires JDK 21 and Docker. No compose services, real credentials or external LLMs
are used. The learning JAR/source may explicitly refer to an unmerged PR; report
that ref separately rather than claiming the implementation has been merged.
For a Linux runner without Docker CLI, --db-host accepts a caller-owned disposable
sidecar and needs psycopg in that test runtime. The caller must remove the sidecar.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.cookiejar
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(check, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.1)
    raise TimeoutError("Verification readiness deadline exceeded")


def verify(args):
    root = Path(__file__).resolve().parents[1]
    core_jar, learning_jar = args.core_jar.resolve(), args.learning_jar.resolve()
    learning_source = args.learning_source.resolve()
    require(core_jar.is_file() and learning_jar.is_file(), "Both executable JARs are required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    container = "issue39-feedback-db-" + uuid.uuid4().hex[:8]
    core_db, learning_db = "issue39_core_feedback", "issue39_learning_feedback"
    internal = "issue39-disposable-internal-token"
    processes, logs, cases = [], [], []
    server = None
    created = False
    external_db = args.db_host
    if external_db:
        require(external_db.startswith("issue39-feedback-db-"), "External host must be a dedicated issue39 container")
        import psycopg  # Test-runtime dependency only, for an isolated Linux runner without Docker CLI.

    def docker(*command, sql=None):
        result = subprocess.run(["docker", *command], input=sql, text=True, encoding="utf-8",
                                capture_output=True)
        if result.returncode:
            raise RuntimeError(f"Verification docker {command[0]} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def db(database, sql):
        require(database in (core_db, learning_db), "Refusing a shared database")
        if external_db:
            with psycopg.connect(host=external_db, port=5432, dbname=database, user="issue39",
                                 password="issue39-disposable-password", autocommit=True) as connection:
                cursor = connection.execute(sql)
                if cursor.description:
                    return "\n".join(json.dumps(row[0], ensure_ascii=False) if isinstance(row[0], (dict, list))
                                     else str(row[0]) for row in cursor.fetchall())
                return ""
        return docker("exec", "-i", container, "psql", "-X", "-At", "-v", "ON_ERROR_STOP=1",
                      "-U", "issue39", "-d", database, sql=sql)

    def start_app(jar, port, database, extra):
        log = (args.output.parent / (database + ".log")).open("w", encoding="utf-8")
        logs.append(log)
        env = os.environ.copy()
        env.update(DB_URL=f"jdbc:postgresql://{external_db or '127.0.0.1'}:{db_port}/{database}",
                   DB_USERNAME="issue39", DB_PASSWORD="issue39-disposable-password",
                   INTERNAL_TOKEN=internal, RABBITMQ_USERNAME="unused", RABBITMQ_PASSWORD="unused",
                   AUTH_JWT_SECRET=base64.b64encode(b"issue39-only-disposable-jwt-secret-32bytes").decode(),
                   AUTH_WEB_ORIGIN=core_url, AUTH_COOKIE_SECURE="false", AI_URL=ai_url,
                   LEARNING_URL=learning_url)
        process = subprocess.Popen([args.java, "-XX:ActiveProcessorCount=2", "-Xmx512m", "-jar", str(jar),
                                    f"--server.port={port}", "--server.address=127.0.0.1",
                                    "--spring.rabbitmq.listener.simple.auto-startup=false",
                                    "--management.health.rabbit.enabled=false",
                                    "--management.endpoint.health.group.readiness.include=readinessState,db", *extra],
                                   env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        processes.append(process)

        def ready():
            require(process.poll() is None, f"{database} JVM exited; inspect its verification log")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/actuator/health/liveness", timeout=2) as response:
                    return response.status == 200
            except (OSError, urllib.error.URLError):
                return False

        wait_for(ready, 60)

    class AiState:
        mode = "success"
        counts = {}
        errors = []
        entered = threading.Event()
        release = threading.Event()
        student = None

        def reset(self, mode):
            self.mode, self.counts, self.errors = mode, {}, []
            self.entered.clear()
            self.release.clear()

    ai = AiState()

    class AiHandler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            ai.counts[self.path] = ai.counts.get(self.path, 0) + 1
            if self.headers.get("X-Internal-Token") != internal or self.headers.get("X-Student-Scope") != ai.student:
                ai.errors.append("Internal token/student scope was not propagated")
            if ai.student and ai.student in json.dumps(payload):
                ai.errors.append("Student identifier leaked into AI request body")
            status = 200
            if self.path == "/internal/judgments":
                mode = ai.mode
                ai.entered.set()
                if mode == "block":
                    require(ai.release.wait(25), "AI test latch was not released")
                if mode in ("fail", "permanent"):
                    status = 503
                    result = {"code": "AI_UNAVAILABLE", "retryable": mode == "fail"}
                else:
                    held = mode == "held"
                    result = {"result": "HELD" if held else "PARTIAL", "trial": True,
                              "heldReason": "TOO_SHORT" if held else None,
                              "elements": [] if held else [
                                  {"elementId": element["elementId"], "quote": payload["answerText"],
                                   "verified": True, "satisfied": True} for element in payload["rubric"]["elements"]],
                              "versions": {"model": "test-only-ai", "prompt": "verify-judge@1"}}
            elif self.path == "/internal/followups":
                result = {"type": "TELL_MORE", "question": "왜 그렇게 생각했는지 더 말해 볼까?",
                          "source": "LLM", "leakCheck": {"passed": True},
                          "versions": {"model": "test-only-ai", "prompt": "verify-followup@1"}}
            else:
                status, result = 404, {"code": "NOT_FOUND"}
            body = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/problem+json" if status != 200 else "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        if not external_db:
            docker("run", "--rm", "-d", "--name", container, "-p", "127.0.0.1::5432",
                   "-e", "POSTGRES_DB=" + core_db, "-e", "POSTGRES_USER=issue39",
                   "-e", "POSTGRES_PASSWORD=issue39-disposable-password", "postgres:17.11-alpine")
            created = True
            # The image's temporary init server accepts Unix sockets before its final restart, but not TCP.
            wait_for(lambda: subprocess.run(["docker", "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "issue39", "-d", core_db],
                                            capture_output=True).returncode == 0)
        db(core_db, "CREATE DATABASE " + learning_db)
        db_port = 5432 if external_db else int(docker("port", container, "5432/tcp").split(":")[-1])
        for database, base in ((core_db, root), (learning_db, learning_source)):
            require(db(database, "SELECT current_database()") == database, "Unexpected database")
            service = "core-service" if database == core_db else "learning-service"
            migrations = base / "backend" / service / "src/main/resources/db/migration"
            files = sorted(migrations.glob("V*__*.sql"), key=lambda path: int(re.match(r"V(\d+)__", path.name)[1]))
            require(bool(files), "No migrations found")
            for migration in files:
                try:
                    db(database, "BEGIN;\n" + migration.read_text(encoding="utf-8") + "\nCOMMIT;")
                except RuntimeError as error:
                    raise RuntimeError(f"{database}/{migration.name}: {error}") from error

        core_port, learning_port, ai_port = free_port(), free_port(), free_port()
        core_url, learning_url, ai_url = (f"http://127.0.0.1:{p}" for p in (core_port, learning_port, ai_port))
        server = ThreadingHTTPServer(("127.0.0.1", ai_port), AiHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        start_app(learning_jar, learning_port, learning_db, [])
        start_app(core_jar, core_port, core_db, [])

        cookies = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
        access = None

        def request(path, body=None, expected=200, method=None, headers=None, raw=False):
            supplied = {"Origin": core_url, "X-Requested-With": "XMLHttpRequest", **(headers or {})}
            if access:
                supplied["Authorization"] = "Bearer " + access
            if body is not None:
                supplied["Content-Type"] = "application/json"
            data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
            req = urllib.request.Request(core_url + path, data=data, headers=supplied, method=method)
            try:
                response = opener.open(req, timeout=45)
            except urllib.error.HTTPError as error:
                response = error
            require(response.status == expected, f"{path}: expected {expected}, received {response.status}")
            return response if raw else json.loads(response.read())

        user, session = str(uuid.uuid4()), str(uuid.uuid4())
        refresh = uuid.uuid4().hex
        hashed = base64.urlsafe_b64encode(hashlib.sha256(refresh.encode()).digest()).decode().rstrip("=")
        db(core_db, f"""INSERT INTO user_account(id,role,login_id,status,is_demo,created_at,updated_at)
            VALUES('{user}','PARENT','{user}@example.invalid','ACTIVE',true,now(),now());
            INSERT INTO auth_session(id,user_id,role,version,expires_at,created_at)
            VALUES('{session}','{user}','PARENT',1,now()+interval '1 day',now());
            INSERT INTO refresh_token(id,user_id,session_id,token_hash,expires_at,created_at)
            VALUES('{uuid.uuid4()}','{user}','{session}','{hashed}',now()+interval '1 day',now());""")
        for kind in ("TERMS", "PRIVACY", "GUARDIAN"):
            doc = uuid.uuid4()
            db(core_db, f"""INSERT INTO consent_document(id,kind,version,title,content,required,effective_from,created_at)
                VALUES('{doc}','{kind}','{doc}','합성 안내','검증 문서',true,
                (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date,now());""")
        access = request("/api/v1/auth/refresh", {}, headers={"Cookie": "sagomungchi_refresh=" + refresh})["accessToken"]
        documents = request("/api/v1/consent-documents")["items"]
        choices = lambda guardian: [{"documentId": d["documentId"], "version": d["version"], "agreed": True}
                                    for d in documents if (d["kind"] == "GUARDIAN") == guardian]
        request("/api/v1/me/consents", {"consents": choices(False)})
        child = request("/api/v1/children", {"nickname": "검증 학생", "grade": 3, "birthYear": 2017,
                                            "consents": choices(True)}, expected=201)["id"]
        access = request("/api/v1/auth/student-sessions", {"childId": child})["accessToken"]
        ai.student = child
        cases.append({"case": "actual_consent_child_registration_student_session", "passed": True})

        def new_answer():
            mission, version, rubric, element = [str(uuid.uuid4()) for _ in range(4)]
            db(learning_db, f"""INSERT INTO mission(id,code,status,demo_only,sort_order,created_by,created_at,updated_at)
                VALUES('{mission}','VERIFY-{mission}','PUBLISHED',false,1,'{user}',now(),now());
                INSERT INTO mission_version(id,mission_id,version,title,subject,grade_min,grade_max,thinking_type,input_type,question,created_by,created_at)
                VALUES('{version}','{mission}',1,'합성 미션','과학',3,6,'ANALYZE','NARRATIVE','이유를 말해 볼까?','{user}',now());
                INSERT INTO rubric_version(id,mission_id,version,created_by,created_at)
                VALUES('{rubric}','{mission}',1,'{user}',now());
                INSERT INTO rubric_element(id,rubric_version_id,code,label,description,points,good_thought,judge_verified,sort_order)
                VALUES('{element}','{rubric}','reason','까닭','까닭 찾기',1,false,true,1);
                UPDATE mission SET current_version_id='{version}',current_rubric_version_id='{rubric}',published_version_id='{version}',published_rubric_version_id='{rubric}' WHERE id='{mission}';""")
            attempt = request(f"/api/v1/missions/{mission}/attempts", {}, expected=201)["attemptId"]
            answer = request(f"/api/v1/attempts/{attempt}/answers", {"inputType": "NARRATIVE", "text": "햇빛이 비쳐서 식물이 자랐어요."},
                             expected=201, headers={"Idempotency-Key": str(uuid.uuid4())})["answerId"]
            return answer

        def row(answer):
            return json.loads(db(learning_db, f"""SELECT row_to_json(v) FROM (SELECT j.id,j.process_status,j.result,j.retry_count,j.failure_code,
                a.plain_text,(SELECT count(*) FROM judgment_element e WHERE e.judgment_id=j.id) AS elements,
                (SELECT count(*) FROM followup f WHERE f.judgment_id=j.id) AS followups
                FROM judgment j JOIN answer a ON a.id=j.answer_id WHERE a.id='{answer}') v;"""))

        def feedback(answer, raw=False):
            response = request(f"/api/v1/answers/{answer}/feedback", method="POST", raw=True,
                               headers={"Accept": "text/event-stream", "X-User-Role": "ADMIN", "X-Student-Scope": str(uuid.uuid4())})
            if raw:
                return response
            body = response.read().decode()
            events = []
            for frame in body.split("\n\n"):
                name = next((line[6:].strip() for line in frame.splitlines() if line.startswith("event:")), None)
                data = "\n".join(line[5:].strip() for line in frame.splitlines() if line.startswith("data:"))
                if name:
                    events.append((name, json.loads(data)))
            require(events[-1] == ("done", {}), "Missing terminal done")
            return events

        answer = new_answer()
        ai.reset("fail")
        failure = feedback(answer)
        failed = row(answer)
        require([event for event, _ in failure] == ["status", "error", "done"], "Failure event order")
        require(failure[1][1]["code"] == "AI_UNAVAILABLE" and failure[1][1]["retryable"] is True, "AI failure not preserved")
        require(failed["process_status"] == "FAILED" and failed["retry_count"] == 1 and failed["elements"] == failed["followups"] == 0,
                "Learning did not commit FAILED without partial results")
        require(failed["plain_text"] == "햇빛이 비쳐서 식물이 자랐어요.", "Stored answer changed")
        ai.mode = "success"
        retried = feedback(answer)
        saved = row(answer)
        require(saved["id"] == failed["id"] and saved["process_status"] == "DONE" and saved["retry_count"] == 1,
                "Learning did not reacquire the same FAILED judgment")
        require(saved["elements"] == saved["followups"] == 1, "Learning results not persisted")
        require(ai.counts == {"/internal/judgments": 2, "/internal/followups": 1}, "Actual reexecution call counts differ")
        counts = ai.counts.copy()
        replay = feedback(answer)
        require(dict(replay)["result"] == dict(retried)["result"] and ai.counts == counts, "DONE replay reran AI")
        require(not ai.errors, str(ai.errors))
        cases.append({"case": "actual_learning_FAILED_retry_DONE_replay", "states": ["FAILED", "DONE", "DONE"],
                      "sameJudgment": True, "retryCount": saved["retry_count"], "aiCalls": counts, "passed": True})

        with ThreadPoolExecutor(max_workers=1) as pool:
            for disconnected in (False, True):
                answer = new_answer()
                ai.reset("block")
                if disconnected:
                    response = feedback(answer, raw=True)
                    require(ai.entered.wait(5), "Learning did not call AI")
                    response.close()
                    require(row(answer)["process_status"] == "RUNNING", "Learning unexpectedly stopped")
                else:
                    first = pool.submit(feedback, answer)
                    require(ai.entered.wait(5), "Learning did not acquire judgment")
                    require(row(answer)["process_status"] == "RUNNING", "Missing real RUNNING lease")
                    busy = feedback(answer)
                    require(all(name in ("status", "done") for name, _ in busy), "RUNNING produced a final result")
                    require(ai.counts.get("/internal/judgments") == 1, "RUNNING duplicated the AI operation")
                ai.release.set()
                if not disconnected:
                    require("result" in dict(first.result(timeout=10)), "Original learning call did not complete")
                wait_for(lambda: row(answer)["process_status"] == "DONE", 10)
                counts = ai.counts.copy()
                require("result" in dict(feedback(answer)) and ai.counts == counts, "Stored result was not reused")
                require(row(answer)["elements"] == row(answer)["followups"] == 1 and not ai.errors, "Actual persistence/header failure")
                cases.append({"case": "actual_disconnect_still_persists" if disconnected else "actual_RUNNING_no_duplicate_execution",
                              "aiCalls": counts, "passed": True})

        answer = new_answer()
        ai.reset("held")
        held = dict(feedback(answer))["result"]
        require(held["judgment"]["result"] == "HELD" and row(answer)["process_status"] == "DONE", "HELD was treated as failure")
        cases.append({"case": "actual_HELD_saved_as_DONE", "passed": True})
        answer = new_answer()
        ai.reset("permanent")
        require(dict(feedback(answer))["error"]["retryable"] is False and row(answer)["process_status"] == "FAILED",
                "retryable=false was replaced with a success/retry fallback")
        cases.append({"case": "actual_permanent_AI_failure_preserved", "passed": True})
        return {"status": "PASS", "coreRef": args.core_ref, "learningRef": args.learning_ref,
                "learningMerged": args.learning_merged,
                "source": "real core and learning JARs, two disposable PostgreSQL databases, synthetic AI HTTP double; no real AI/LLM",
                "migrationSetup": "all SQL migrations in numeric order, one transaction per file; application auto-migration remains disabled",
                "coreJarSha256": hashlib.sha256(core_jar.read_bytes()).hexdigest(),
                "learningJarSha256": hashlib.sha256(learning_jar.read_bytes()).hexdigest(), "cases": cases}
    finally:
        ai.release.set()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in logs:
            log.close()
        if server:
            server.shutdown()
            server.server_close()
        if created:
            docker("stop", "-t", "5", container)  # --rm removes only this invocation's disposable DB.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-jar", type=Path, required=True)
    parser.add_argument("--learning-jar", type=Path, required=True)
    parser.add_argument("--learning-source", type=Path, required=True)
    parser.add_argument("--core-ref", required=True)
    parser.add_argument("--learning-ref", required=True)
    parser.add_argument("--learning-merged", action="store_true")
    parser.add_argument("--java", default="java")
    parser.add_argument("--db-host", help="Dedicated issue39-feedback-db-* sidecar; requires test-runtime psycopg")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = verify(arguments)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    arguments.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
