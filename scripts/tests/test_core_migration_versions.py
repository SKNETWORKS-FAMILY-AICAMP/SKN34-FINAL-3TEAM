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
