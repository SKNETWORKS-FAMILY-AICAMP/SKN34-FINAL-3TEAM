"""#312: 앱 기본값·배포 values와 실제 Compose 환경 변수/의존성 전달을 대조한다."""

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[2]
AI_KEYS = (
    "JUDGE_DEADLINE",
    "SCORING_TIMEOUT",
    "SCORING_RESERVE",
    "M2_CROSS_CHECK_ENABLED",
    "M2_NARRATIVE_LOW",
    "M2_NARRATIVE_HIGH",
    "M2_ESSAY_LOW",
    "M2_ESSAY_HIGH",
    "M2_ESSAY_HIGH_ENABLED",
    "M2_NARRATIVE_MIN_CHARS",
    "M2_ESSAY_MIN_CHARS",
    "M1_CHECK_ENABLED",
    "M1_MIN_CONFIDENCE",
)
KEYS = {
    "ai-service": AI_KEYS,
    "core-service": (
        "APP_GUARDIAN_TRANSFER_ENABLED",
        "AUTH_NEW_ACCOUNT_DEMO",
        "AUTH_SIGNUP_LIMIT_PER_IP",
        "AUTH_SIGNUP_LIMIT_WINDOW",
    ),
    "scoring-service": ("M2_CONTENT3_RULE_ENABLED",),
}
FILES = (
    "compose.yaml",
    "compose.minio.yaml",
    "compose.e2e.yaml",
    "compose.transfer-local.yaml",
)


def python_defaults(service, keys):
    tree = ast.parse(
        (ROOT / "backend" / service / "app/config.py").read_text(encoding="utf-8")
    )
    settings = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    result = {}
    for node in settings.body:
        if isinstance(node, ast.AnnAssign) and node.target.id.upper() in keys:
            value = ast.literal_eval(node.value)
            result[node.target.id.upper()] = str(value).lower()
    if set(result) != set(keys):
        raise AssertionError(
            f"{service} Settings 기본값을 찾지 못함: {set(keys) - set(result)}"
        )
    return result


def defaults():
    return {
        "ai-service": python_defaults("ai-service", AI_KEYS),
        "scoring-service": python_defaults("scoring-service", KEYS["scoring-service"]),
        "core-service": {
            "APP_GUARDIAN_TRANSFER_ENABLED": "false",
            "AUTH_NEW_ACCOUNT_DEMO": "false",
            "AUTH_SIGNUP_LIMIT_PER_IP": "5",
            "AUTH_SIGNUP_LIMIT_WINDOW": "10m",
        },
    }


def compose(files, overrides=None):
    # 실제 .env나 셸의 자격 증명/사용자 설정을 읽지 않고 저장소 합성 값만 사용한다.
    env = os.environ.copy()
    for path in FILES:
        for key in re.findall(
            r"\$\{([A-Z_][A-Z_0-9]*)", (ROOT / path).read_text(encoding="utf-8")
        ):
            env.pop(key, None)
    for key in list(env):
        if key.startswith("COMPOSE_"):
            env.pop(key)
    with tempfile.TemporaryDirectory() as temp:
        env_path = Path(temp) / "synthetic.env"
        fixture = (ROOT / "infrastructure/stubs/e2e.env").read_text(encoding="utf-8")
        values = dict(
            line.split("=", 1)
            for line in fixture.splitlines()
            if line and not line.startswith("#")
        )
        values.update(overrides or {})
        env_path.write_text(
            "\n".join(f"{key}={value}" for key, value in values.items()),
            encoding="utf-8",
        )
        command = [
            "docker",
            "compose",
            "-p",
            "issue312-config-test",
            "--env-file",
            str(env_path),
        ]
        for path in files:
            command.extend(("-f", str(ROOT / path)))
        result = subprocess.run(
            command + ["config", "--format", "json"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=45,
        )
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class RuntimeConfigTests(unittest.TestCase):
    def test_example_and_local_values_preserve_application_defaults(self):
        example = dict(
            line.split("=", 1)
            for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        )
        for service, expected in defaults().items():
            values = yaml.safe_load(
                (
                    ROOT
                    / "infrastructure/gitops/environments/local"
                    / f"{service}.yaml"
                ).read_text(encoding="utf-8")
            )
            entries = values["env"]
            self.assertEqual(
                len(entries), len({item["name"] for item in entries}), service
            )
            actual = {item["name"]: item.get("value") for item in entries}
            for key, value in expected.items():
                with self.subTest(service=service, key=key):
                    self.assertEqual(example.get(key), value)
                    self.assertEqual(actual.get(key), value)
                    self.assertIsInstance(actual[key], str)

    def test_core_defaults_match_application_yml(self):
        # app.auth.* 기본값은 Spring 자리표시자 ${KEY:기본값}과 같아야 한다 (#517)
        text = (
            ROOT / "backend/core-service/src/main/resources/application.yml"
        ).read_text(encoding="utf-8")
        for key, value in defaults()["core-service"].items():
            if not key.startswith("AUTH_"):
                continue
            with self.subTest(key=key):
                self.assertIn(f"${{{key}:{value}}}", text)

    def test_report_worker_explanation_settings_and_grace_period(self):
        # #508: local·prod report-worker가 같은 설명 시간 값을 쓰고, 종료 유예가 설명 단계보다 김
        keys = (
            "REPORT_NARRATIVE_TIMEOUT_SECONDS",
            "REPORT_EXPLANATION_TIMEOUT_SECONDS",
            "REPORT_EXPLANATION_BUDGET_SECONDS",
            "REPORT_THEME_SUMMARY_ENABLED",
        )
        base = ROOT / "infrastructure/gitops/environments"
        local = yaml.safe_load(
            (base / "local/report-worker.yaml").read_text(encoding="utf-8")
        )
        prod = json.loads(
            (base / "prod/report-worker.json").read_text(encoding="utf-8")
        )
        for name, values in (("local", local), ("prod", prod)):
            env = {item["name"]: item.get("value") for item in values["env"]}
            with self.subTest(env=name):
                self.assertEqual(
                    {key: env.get(key) for key in keys},
                    # #747: ai SageMaker 호출 1회(마감 75초) 기준
                    dict(zip(keys, ("80", "80", "300", "true"))),
                )
                self.assertGreater(
                    values["terminationGracePeriodSeconds"],
                    float(env["REPORT_EXPLANATION_BUDGET_SECONDS"]),
                )

    def test_prod_memory_book_asset_origin_matches_learning_bucket(self):
        # #974: learning이 서명하는 테마 그림 주소(SDK 기본 virtual-hosted regional)의 출처만 허용
        base = ROOT / "infrastructure/gitops/environments/prod"
        learning = {
            item["name"]: item.get("value")
            for item in json.loads((base / "learning-service.json").read_text(encoding="utf-8"))["env"]
        }
        worker = json.loads((base / "report-worker.json").read_text(encoding="utf-8"))
        env = {item["name"]: item.get("value") for item in worker["env"]}
        self.assertNotIn("S3_PUBLIC_ENDPOINT_URL", learning)
        self.assertEqual(
            env.get("MEMORY_BOOK_ASSET_ORIGINS"),
            f"https://{learning['ASSET_S3_BUCKET']}.s3.{learning['S3_REGION']}.amazonaws.com",
        )
        # prod는 S3를 직접 받으므로 클러스터 안 주소 치환(kind MinIO용)이 없어야 함
        self.assertNotIn("MEMORY_BOOK_ASSET_INTERNAL_ORIGINS", env)
        https_egress = [
            rule for rule in worker["networkPolicy"]["egress"]
            if {"port": 443, "protocol": "TCP"} in rule.get("ports", [])
        ]
        self.assertTrue(https_egress, "S3 서명 URL을 받을 443 egress 필요")

    @unittest.skipUnless(shutil.which("docker"), "Compose CLI 필요(컨테이너 실행 없음)")
    def test_compose_omitted_and_explicit_false_keep_defaults(self):
        for overrides in (
            {},
            {
                key: "false"
                for keys in KEYS.values()
                for key in keys
                if key.endswith("ENABLED")
            },
        ):
            services = compose(("compose.yaml",), overrides)["services"]
            for service, expected in defaults().items():
                for key, value in expected.items():
                    with self.subTest(
                        service=service, key=key, explicit=bool(overrides)
                    ):
                        self.assertEqual(
                            services[service]["environment"].get(key), value
                        )

    @unittest.skipUnless(shutil.which("docker"), "Compose CLI 필요(컨테이너 실행 없음)")
    def test_env_can_override_every_exposed_setting(self):
        # 기본값과 다른 유효한 값: 파일을 편집해도 앱에 전달되지 않던 누락을 검출한다.
        overrides = {
            "JUDGE_DEADLINE": "32.0",
            "SCORING_TIMEOUT": "9.0",
            "SCORING_RESERVE": "4.0",
            "M2_CROSS_CHECK_ENABLED": "true",
            "M2_NARRATIVE_LOW": "2.1",
            "M2_NARRATIVE_HIGH": "3.9",
            "M2_ESSAY_LOW": "1.1",
            "M2_ESSAY_HIGH": "1.9",
            "M2_ESSAY_HIGH_ENABLED": "true",
            "M2_NARRATIVE_MIN_CHARS": "101",
            "M2_ESSAY_MIN_CHARS": "141",
            "M1_CHECK_ENABLED": "true",
            "M1_MIN_CONFIDENCE": "0.9",
            "APP_GUARDIAN_TRANSFER_ENABLED": "true",
            "AUTH_NEW_ACCOUNT_DEMO": "true",
            "AUTH_SIGNUP_LIMIT_PER_IP": "50",
            "AUTH_SIGNUP_LIMIT_WINDOW": "1m",
            "M2_CONTENT3_RULE_ENABLED": "true",
        }
        services = compose(("compose.yaml",), overrides)["services"]
        for service, keys in KEYS.items():
            for key in keys:
                with self.subTest(service=service, key=key):
                    self.assertEqual(
                        services[service]["environment"].get(key), overrides[key]
                    )

    @unittest.skipUnless(shutil.which("docker"), "Compose CLI 필요(컨테이너 실행 없음)")
    def test_transfer_stack_starts_its_scoring_target_without_published_port(self):
        config = compose(FILES)
        services = config["services"]
        ai = services["ai-service"]
        target = urlparse(ai["environment"]["SCORING_URL"])
        self.assertEqual(target.hostname, "scoring-service")
        self.assertEqual(target.port, 8001)
        scoring = services[target.hostname]
        self.assertFalse(scoring.get("profiles"))
        self.assertFalse(scoring.get("ports"))
        # #305 이후 교차 확인 off면 scoring을 부르지 않으므로 기동 의존을 두지 않는다 (#502)
        self.assertNotIn(target.hostname, ai.get("depends_on", {}))
        for service in ("ai-service", "scoring-service"):
            for key, value in defaults()[service].items():
                self.assertEqual(services[service]["environment"][key], value)
        for service in services.values():
            for port in service.get("ports", []):
                self.assertEqual(port["host_ip"], "127.0.0.1")
        for volume in config["volumes"].values():
            self.assertFalse(volume.get("external"))
            self.assertTrue(volume["name"].startswith("issue312-config-test_"))


if __name__ == "__main__":
    unittest.main()
