"""#85 real team model verification in an isolated local Compose project.

Run with a Python containing boto3/httpx/PyYAML. Model archives stay outside Git;
only selected regular members are streamed to a fresh local MinIO instance.
"""

import argparse
import base64
import hashlib
import hmac
import json
import subprocess
import tarfile
import time
from pathlib import Path
from uuid import uuid4

import boto3
import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
BUCKET = "issue85-local-models"
NAMES = ("m2-klue-narrative", "m2-klue-essay")
FILES = (
    "config.json",
    "model.safetensors",
    "tokenizer_config.json",
    "tokenizer.json",
    "train_info.json",
    "score_cuts.json",
)


def wait(url, predicate, headers=None, seconds=240):
    end, status = time.monotonic() + seconds, None
    while time.monotonic() < end:
        try:
            response = httpx.get(url, headers=headers, timeout=5)
            status = response.status_code
            if predicate(response):
                return response
        except httpx.HTTPError:
            status = None
        time.sleep(1)
    raise RuntimeError(f"Local endpoint not ready; status={status}")


def verify(
    archive, core_root, output, image, *, events=False, scores=False, epic=False
):
    if archive.is_relative_to(ROOT) or archive.is_relative_to(core_root):
        raise ValueError("Model archive must be outside repository checkouts")
    if output.is_relative_to(ROOT) or output.is_relative_to(core_root):
        raise ValueError(
            "Local Compose credentials/results must be outside repository checkouts"
        )
    jar = core_root / "backend/core-service/build/libs/core-service-0.0.1-SNAPSHOT.jar"
    if not jar.is_file() or any(
        p.is_file() and p.stat().st_mtime > jar.stat().st_mtime
        for p in (core_root / "backend/core-service/src/main").rglob("*")
    ):
        raise RuntimeError("Rebuild current core bootJar first")
    output.mkdir(parents=True, exist_ok=True)
    project = "issue85-" + uuid4().hex[:10]
    password, token = uuid4().hex, uuid4().hex
    jwt_key = base64.b64encode((uuid4().hex + uuid4().hex).encode()).decode()
    scoring_env = {
        "INTERNAL_TOKEN": token,
        "RABBITMQ_URL": f"amqp://verify:{password}@rabbitmq:5672/",
        "CORE_URL": "http://core:8080",
        "S3_ENDPOINT_URL": "http://minio:9000",
        "S3_BUCKET": BUCKET,
        "S3_REGION": "us-east-1",
        "MODEL_RETRY_INTERVAL": "2",
        "AWS_ACCESS_KEY_ID": "verify",
        "AWS_SECRET_ACCESS_KEY": password,
    }

    def healthy(service):
        return {service: {"condition": "service_healthy"}}

    compose = {
        "services": {
            "postgres": {
                "image": "postgres:17.11-alpine",
                "environment": {
                    "POSTGRES_USER": "verify",
                    "POSTGRES_PASSWORD": password,
                    "POSTGRES_DB": "core_db",
                },
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U verify"],
                    "interval": "2s",
                    "retries": 40,
                },
            },
            "rabbitmq": {
                "image": "rabbitmq:4.3.7-management-alpine",
                "environment": {
                    "RABBITMQ_DEFAULT_USER": "verify",
                    "RABBITMQ_DEFAULT_PASS": password,
                },
                "healthcheck": {
                    "test": [
                        "CMD",
                        "rabbitmq-diagnostics",
                        "-q",
                        "check_port_connectivity",
                    ],
                    "interval": "5s",
                    "timeout": "10s",
                    "retries": 30,
                },
            },
            "rabbit-init": {
                "image": "curlimages/curl:8.17.0",
                "depends_on": healthy("rabbitmq"),
                "environment": {
                    "RABBITMQ_USER": "verify",
                    "RABBITMQ_PASSWORD": password,
                },
                "volumes": [
                    str(
                        core_root
                        / "infrastructure/gitops/charts/platform-data/files/rabbitmq"
                    )
                    + ":/definitions:ro"
                ],
                "entrypoint": ["/bin/sh", "/definitions/import-definitions.sh"],
            },
            "redis": {"image": "redis:8.2.10-alpine"},
            "migrate": {
                "image": "flyway/flyway:13.11.1-alpine",
                "depends_on": healthy("postgres"),
                "volumes": [
                    str(
                        core_root
                        / "backend/core-service/src/main/resources/db/migration"
                    )
                    + ":/flyway/sql:ro"
                ],
                "command": [
                    "-url=jdbc:postgresql://postgres:5432/core_db",
                    "-user=verify",
                    f"-password={password}",
                    "migrate",
                ],
            },
            "core": {
                "image": "eclipse-temurin:21-jdk",
                "user": "10001",
                "volumes": [str(jar) + ":/app/core.jar:ro"],
                "command": ["java", "-Xmx512m", "-jar", "/app/core.jar"],
                "ports": ["127.0.0.1::8080"],
                "depends_on": {
                    "migrate": {"condition": "service_completed_successfully"},
                    "rabbit-init": {"condition": "service_completed_successfully"},
                    "redis": {"condition": "service_started"},
                },
                "environment": {
                    "DB_URL": "jdbc:postgresql://postgres:5432/core_db",
                    "DB_USERNAME": "verify",
                    "DB_PASSWORD": password,
                    "INTERNAL_TOKEN": token,
                    "RABBITMQ_HOST": "rabbitmq",
                    "RABBITMQ_USERNAME": "verify",
                    "RABBITMQ_PASSWORD": password,
                    "REDIS_HOST": "redis",
                    "AUTH_JWT_SECRET": jwt_key,
                    "AUTH_COOKIE_SECURE": "false",
                },
            },
            "minio": {
                "image": "cgr.dev/chainguard/minio@sha256:"
                "98c819b873cbd455860c1fb5a9171a62b2f48d86554a4b2c6847e60a14a9ef30",
                "environment": {
                    "MINIO_ROOT_USER": "verify",
                    "MINIO_ROOT_PASSWORD": password,
                },
                "ports": ["127.0.0.1::9000"],
                "tmpfs": ["/data:uid=65532,gid=65532,mode=0700"],
                "command": [
                    "--certs-dir",
                    "/tmp/certs",
                    "server",
                    "--address",
                    ":9000",
                    "/data",
                ],
            },
            "scoring": {
                "image": image,
                "environment": scoring_env,
                "ports": ["127.0.0.1::8001"],
            },
        }
    }
    if scores:
        compose["services"]["rabbitmq"]["ports"] = ["127.0.0.1::15672"]
        scoring_env["OMP_NUM_THREADS"] = "4"
        scoring_env["MKL_NUM_THREADS"] = "4"
    config = output / "compose.local.yaml"
    if events or scores:
        compose["services"]["scoring2"] = {
            "image": image,
            "environment": scoring_env,
            "ports": ["127.0.0.1::8001"],
        }
        compose["services"]["rabbitmq"]["ports"] = ["127.0.0.1::15672"]
    config.write_text(yaml.safe_dump(compose, sort_keys=False), encoding="utf-8")
    base = ["docker", "compose", "-p", project, "-f", str(config)]

    def run(args, *, stdin=None, timeout=300, check=True):
        result = subprocess.run(
            base + args,
            input=stdin,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if check and result.returncode:
            (output / "failed-command.log").write_text(
                result.stdout + result.stderr, encoding="utf-8"
            )
            raise RuntimeError(
                "Local Docker command failed; inspect failed-command.log"
            )
        return result.stdout

    def url(service, port):
        return "http://" + run(["port", service, str(port)]).strip()

    results = {"models": [], "checks": []}

    def passed(label):
        results["checks"].append(label)
        print("PASS " + label, flush=True)

    try:
        run(["up", "-d"], timeout=600)
        core, scoring, minio = (
            url("core", 8080),
            url("scoring", 8001),
            url("minio", 9000),
        )
        headers = {"X-Internal-Token": token}
        wait(core + "/actuator/health/readiness", lambda r: r.status_code == 200)
        wait(scoring + "/health/ready", lambda r: r.status_code == 200)
        assert httpx.get(scoring + "/internal/versions", headers=headers).json() == {
            "items": []
        }
        assert httpx.get(scoring + "/internal/versions").status_code == 401
        passed("empty active snapshot ready; unauthenticated versions 401")
        if epic:
            for input_type in ("NARRATIVE", "ESSAY"):
                response = httpx.post(
                    scoring + "/internal/m2/scores",
                    headers=headers,
                    json={
                        "prompt": "생각을 설명하세요",
                        "text": "합성 검증 문장",
                        "grade": 5,
                        "inputType": input_type,
                        "keywords": ["생각"],
                    },
                )
                assert response.status_code == 200 and response.json() == {
                    "active": False
                }
            passed("both M2 input types return inactive before any model is activated")
        user, session = str(uuid4()), str(uuid4())
        sql = f"""INSERT INTO user_account(id,role,login_id,status,is_demo,created_at,updated_at)
        VALUES('{user}','ADMIN','issue85-{user}@test.invalid','ACTIVE',false,now(),now());
        INSERT INTO admin_permission(user_id,permission,granted_by,granted_at)
        VALUES('{user}','SERVICE_OPS','{user}',now());
        INSERT INTO auth_session(id,user_id,role,version,expires_at,created_at)
        VALUES('{session}','{user}','ADMIN',1,now()+interval '1 hour',now());"""
        run(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "verify",
                "-d",
                "core_db",
                "-v",
                "ON_ERROR_STOP=1",
            ],
            stdin=sql,
        )

        def b64(value):
            return base64.urlsafe_b64encode(value).decode().rstrip("=")

        now = int(time.time())
        message = (
            b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
            + "."
            + b64(
                json.dumps(
                    {
                        "iss": "sagomungchi-core",
                        "aud": ["access"],
                        "iat": now,
                        "exp": now + 3600,
                        "jti": str(uuid4()),
                        "sub": user,
                        "sid": session,
                        "ver": 1,
                        "role": "ADMIN",
                    }
                ).encode()
            )
        )
        access = (
            message
            + "."
            + b64(
                hmac.new(
                    base64.b64decode(jwt_key), message.encode(), hashlib.sha256
                ).digest()
            )
        )
        with httpx.Client(
            base_url=core, headers={"Authorization": "Bearer " + access}, timeout=30
        ) as client:
            for name in NAMES:
                scope = (
                    f"judgment/grade-5/{name.removeprefix('m2-klue-')}"
                    if scores
                    else "verification/" + name
                )
                evidence = {
                    key: "LOCAL integration fixture, NOT model quality approval"
                    for key in (
                        "datasetId",
                        "datasetVersion",
                        "baselineVersion",
                        "comparisonReport",
                        "trainingEvaluationSeparation",
                        "quoteAccuracy",
                        "calculationAccuracy",
                        "humanReview",
                    )
                }
                evidence["evaluatedScopes"] = [scope]
                uri = f"s3://{BUCKET}/models/{name}/2.0/"
                response = client.post(
                    "/api/v1/admin/model-versions",
                    json={
                        "kind": "MODEL",
                        "name": name,
                        "version": "2.0",
                        "artifactUri": uri,
                        "evaluation": evidence,
                    },
                )
                response.raise_for_status()
                model_id = response.json()["id"]
                response = client.post(
                    f"/api/v1/admin/model-versions/{model_id}/activate",
                    json={
                        "approved": True,
                        "scopes": [scope],
                        "reason": "Local transport/load verification only",
                        "reanalysisPlanned": False,
                    },
                )
                response.raise_for_status()
                results["models"].append(
                    {"name": name, "version": "2.0", "artifactUri": uri, "scope": scope}
                )
        results["snapshot"] = httpx.get(
            core + "/internal/model-versions/active", headers=headers
        ).json()
        run(["restart", "scoring", *(["scoring2"] if events or scores else [])])
        # Docker may reallocate an automatically assigned host port on restart.
        scoring = url("scoring", 8001)
        wait(
            scoring + "/health/ready",
            lambda r: (
                r.status_code == 503 and r.json()["checks"].get("models") == "DOWN"
            ),
        )
        assert httpx.get(scoring + "/health/live").status_code == 200
        assert httpx.get(scoring + "/internal/versions", headers=headers).json() == {
            "items": []
        }
        passed(
            "actual core registration/activation; missing files keep models DOWN and process live"
        )
        before = json.loads(run(["ps", "--format", "json", "scoring"]))
        wait(minio + "/minio/health/live", lambda r: r.status_code == 200)
        s3 = boto3.client(
            "s3",
            endpoint_url=minio,
            region_name="us-east-1",
            aws_access_key_id="verify",
            aws_secret_access_key=password,
        )
        try:
            s3.create_bucket(Bucket=BUCKET)
            manifest = []
            with tarfile.open(archive, "r:*") as source:
                for name in NAMES:
                    for filename in FILES:
                        key = f"models/{name}/2.0/{filename}"
                        member = source.getmember(key)
                        if filename == "score_cuts.json":
                            results.setdefault("cuts", {})[name] = json.load(
                                source.extractfile(member)
                            )
                        if not member.isfile():
                            raise ValueError("Expected a regular model member")
                        with source.extractfile(member) as stream:
                            digest = hashlib.file_digest(stream, "sha256").hexdigest()
                        with source.extractfile(member) as stream:
                            s3.upload_fileobj(stream, BUCKET, key)
                        assert (
                            s3.head_object(Bucket=BUCKET, Key=key)["ContentLength"]
                            == member.size
                        )
                        manifest.append(
                            {"key": key, "bytes": member.size, "sha256": digest}
                        )
                    print("Uploaded locally: " + name, flush=True)
            results["manifest"] = manifest
        finally:
            s3.close()
        ready = wait(
            scoring + "/health/ready", lambda r: r.status_code == 200, seconds=300
        )
        versions = httpx.get(scoring + "/internal/versions", headers=headers).json()
        assert versions == {
            "items": [
                {"name": n, "version": "2.0", "revision": 1} for n in sorted(NAMES)
            ]
        }
        after = json.loads(run(["ps", "--format", "json", "scoring"]))
        assert before["ID"] == after["ID"]
        results["versions"], results["readiness"] = versions, ready.json()
        passed("real 2.0 checkpoints loaded; readiness recovered; versions match")
        if scores:
            from verify_scoring_m2 import check_scores

            check_scores(
                run, url, core, access, headers, password, results, passed, epic=epic
            )
            (output / "results.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return
        if events:
            from verify_scoring_events import check_events

            check_events(run, url, core, access, headers, password, results, passed)
            (output / "results.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return
        stats = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", after["ID"]],
            capture_output=True,
            text=True,
            check=True,
        )
        results["scoring_memory_sample"] = json.loads(stats.stdout)
        probe = ROOT / "scripts/scoring_model_probe.py"
        raw = run(
            [
                "run",
                "--rm",
                "--no-deps",
                "-v",
                str(probe) + ":/probe.py:ro",
                "-e",
                "PYTHONPATH=/app",
                "scoring",
                "python",
                "/probe.py",
            ],
            timeout=300,
        )
        (output / "probe.log").write_text(raw, encoding="utf-8")
        results["probe"] = json.loads(
            next(
                line.removeprefix("PROBE_JSON=")
                for line in raw.splitlines()
                if line.startswith("PROBE_JSON=")
            )
        )
        passed(
            "CPU loader: finite 1x9 outputs, metadata, scope rejection, temporary cleanup"
        )
        logs = run(["logs", "--no-color", "scoring"])
        assert (
            token not in logs
            and password not in logs
            and "Traceback (most recent call last)" not in logs
        )
        passed("scoring logs omit test credentials and unhandled tracebacks")
        (output / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    finally:
        try:
            (output / "services.log").write_text(
                run(["logs", "--no-color"], check=False), encoding="utf-8"
            )
        finally:
            (output / "cleanup.log").write_text(
                run(["down", "--volumes", "--remove-orphans"]), encoding="utf-8"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="local/scoring85-models:20261029")
    args = parser.parse_args()
    verify(
        args.archive.resolve(),
        args.core_root.resolve(),
        args.output.resolve(),
        args.image,
    )
