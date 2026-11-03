"""Reject duplicate Flyway versions before the isolated database cycle runs."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FlywayVersionTest(unittest.TestCase):
    def test_service_migration_versions_are_unique(self):
        for service in ("core", "learning"):
            folder = ROOT / f"backend/{service}-service/src/main/resources/db/migration"
            versions = {}
            for path in sorted(folder.glob("V*__*.sql")):
                # Flyway treats trailing zero components as the same version.
                version = list(map(int, path.name[1:].split("__", 1)[0].replace("_", ".").split(".")))
                while len(version) > 1 and version[-1] == 0:
                    version.pop()
                key = tuple(version)
                self.assertNotIn(key, versions, f"{service}: {versions.get(key)} / {path.name}")
                versions[key] = path.name


class GitOpsMigrationRevisionTest(unittest.TestCase):
    """The local PreSync Job is named by revision; a stale value skips new migrations on sync."""

    def revision(self, values):
        text = (ROOT / "infrastructure/gitops/environments/local" / values).read_text(encoding="utf-8")
        section = text.split("\nmigration:\n", 1)[1]
        line = next(line for line in section.splitlines() if line.strip().startswith("revision:"))
        return line.split(":", 1)[1].strip().strip('"')

    def latest_flyway(self, service):
        folder = ROOT / f"backend/{service}-service/src/main/resources/db/migration"
        return max(int(path.name[1:].split("__", 1)[0].split("_")[0]) for path in folder.glob("V*__*.sql"))

    def test_local_revisions_follow_latest_migration(self):
        self.assertEqual(self.revision("core-service.yaml"), f"v{self.latest_flyway('core')}")
        self.assertEqual(self.revision("learning-service.yaml"), f"v{self.latest_flyway('learning')}")
        report = max(path.stem for path in (ROOT / "backend/report-service/migrations/versions").glob("2*.py"))
        # 20261102_05_event_retention_index -> 20261102-05
        self.assertEqual(self.revision("report-api.yaml"), "-".join(report.split("_")[:2]))
