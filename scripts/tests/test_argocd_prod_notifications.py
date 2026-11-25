"""#1003 prod Argo CD 알림 webhook 설정과 README 절차. 네트워크·클러스터 호출 없음."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALUES = ROOT / "infrastructure" / "gitops" / "environments" / "prod" / "argocd.json"
README = ROOT / "infrastructure" / "gitops" / "argocd" / "prod" / "README.md"


class ArgocdProdNotificationsTest(unittest.TestCase):
    def setUp(self):
        self.values = json.loads(VALUES.read_text(encoding="utf-8"))
        self.readme = README.read_text(encoding="utf-8")

    def test_webhook_url_comes_from_notifications_secret(self):
        notifications = self.values["notifications"]
        self.assertFalse(notifications["secret"]["create"])
        service = notifications["notifiers"]["service.webhook.discord"]
        self.assertIn("url: $discord-webhook-url", service)
        self.assertNotIn("discord.com", json.dumps(self.values))
        self.assertIn("--from-file=discord-webhook-url=", self.readme)

    def test_readme_uses_argocd_only_webhook(self):
        self.assertIn("sagomungchi/demo/argocd/discord-webhook", self.readme)
        self.assertNotIn("`DISCORD_WEBHOOK_URL`과 같은 값", self.readme)

    def test_readme_never_prints_notifications_log_directly(self):
        for line in self.readme.splitlines():
            if re.search(r"logs\s+deploy/argocd-notifications-controller", line):
                self.assertTrue(
                    line.lstrip().startswith("$log ="),
                    f"notifications-controller 로그는 변수로만 받아 가린 뒤 본다: {line}",
                )
        self.assertIn("-replace 'https://discord(app)?\\.com/api/webhooks/\\S+', '<webhook>'", self.readme)


if __name__ == "__main__":
    unittest.main()
