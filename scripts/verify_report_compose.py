"""#56 isolated Compose integration. Run with report-service's .venv Python.

Requires up-to-date core/learning bootJars and Docker. Always removes only its own
unique Compose project; does not use .env, publish ports, or touch shared volumes.
"""

import argparse
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def verify(output, *, admin_retry=False):
    for service in ("core", "learning"):
        source = ROOT / f"backend/{service}-service"
        jar = source / f"build/libs/{service}-service-0.0.1-SNAPSHOT.jar"
        if not jar.is_file() or any(
            p.is_file() and p.stat().st_mtime > jar.stat().st_mtime
            for p in (source / "src/main").rglob("*")
        ):
            raise RuntimeError(f"Rebuild {service} bootJar from current sources first")
    output.mkdir(parents=True, exist_ok=True)
    project = ("report152-" if admin_retry else "report56-") + uuid4().hex[:10]
    base = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(ROOT / "scripts/report_integration/compose.yaml"),
    ]

    def run(name, args, timeout=600, check=True):
        with (output / (name + ".log")).open("w", encoding="utf-8") as log:
            result = subprocess.run(
                base + args,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        if check and result.returncode:
            raise RuntimeError(f"{name} failed; inspect {output / (name + '.log')}")
        return result

    try:
        run("config", ["config", "--quiet"])
        run("build", ["build", "report-worker"], timeout=900)
        scale = ["--scale", "report-worker=2"] if admin_retry else []
        run(
            "up",
            [
                "up",
                "-d",
                *scale,
                "report-api",
                "report-worker",
                "core",
                "learning",
                "fixture",
                "minio",
            ],
            timeout=600,
        )
        command = ["python", "/verification/admin_retry.py"] if admin_retry else []
        run("verify", ["run", "--rm", "--no-deps", "verify", *command], timeout=600)
        raw = (output / "verify.log").read_text(encoding="utf-8")
        result = json.loads(
            next(
                line.removeprefix("RESULT_JSON=")
                for line in raw.splitlines()
                if line.startswith("RESULT_JSON=")
            )
        )
        for event in result["requests"] + result["events"]:
            for filename, value in [
                ("envelope.schema.json", event),
                (event["dataschema"] + ".schema.json", event["data"]),
            ]:
                schema = json.loads(
                    (ROOT / "contracts/events" / filename).read_text(encoding="utf-8")
                )
                Draft202012Validator(schema, format_checker=FormatChecker()).validate(
                    value
                )
        (output / "results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for case in result["cases"]:
            print("PASS " + case["case"], flush=True)
        print("PASS shared event envelope/payload schemas", flush=True)
    finally:
        try:
            run("services", ["ps", "-a"], check=False)
            run("services-output", ["logs", "--no-color"], check=False)
        finally:
            run("cleanup", ["down", "--volumes", "--remove-orphans"], check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--admin-retry", action="store_true", help="#152 new-job retry scenarios"
    )
    args = parser.parse_args()
    verify(args.output.resolve(), admin_retry=args.admin_retry)
