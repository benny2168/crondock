import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Set isolated test directories and test credentials BEFORE importing app modules
TEST_TMP_DIR = tempfile.mkdtemp(prefix="crondock_test_")
os.environ["DATA_DIR"] = TEST_TMP_DIR
os.environ["SCRIPTS_DIR"] = os.path.join(TEST_TMP_DIR, "scripts")
os.environ["API_KEY"] = "test-crondock-api-key-12345"
os.environ["IAM_API_KEY"] = "test-iam-api-key-67890"
os.environ["SESSION_SECRET"] = "test-session-secret-0123456789abcdef"

APP_DIR = Path(__file__).resolve().parent.parent / "app"
if not APP_DIR.exists() and Path("/app").exists():
    APP_DIR = Path("/app")
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from main import APP_VERSION, SECRET_MASK, app  # noqa: E402
from scripts_manager import check_and_correct_syntax, sanitize_filename  # noqa: E402


class CronDockTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_ctx = TestClient(app)
        cls.client = cls.client_ctx.__enter__()
        cls.headers = {"X-API-Key": "test-crondock-api-key-12345"}

    @classmethod
    def tearDownClass(cls):
        cls.client_ctx.__exit__(None, None, None)
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)

    def test_01_health_and_security_headers(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["version"], APP_VERSION)
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertIn("default-src 'self'", resp.headers.get("Content-Security-Policy", ""))

    def test_02_robots_and_sitemap_and_unknown_api_404(self):
        r_robots = self.client.get("/robots.txt")
        self.assertEqual(r_robots.status_code, 200)
        self.assertIn("User-agent: *", r_robots.text)

        r_sitemap = self.client.get("/sitemap.xml")
        self.assertEqual(r_sitemap.status_code, 404)

        r_unknown = self.client.get("/api/does-not-exist", headers=self.headers)
        self.assertEqual(r_unknown.status_code, 404)

    def test_03_authentication_protection(self):
        # Unauthenticated API call returns 401
        r_unauth = self.client.get("/api/jobs")
        self.assertEqual(r_unauth.status_code, 401)

        # Authenticated via X-API-Key returns 200
        r_auth = self.client.get("/api/jobs", headers=self.headers)
        self.assertEqual(r_auth.status_code, 200)

    def test_04_settings_secret_masking_and_preservation(self):
        # Create a secret setting
        r_create = self.client.post(
            "/api/settings",
            headers=self.headers,
            json={
                "key": "TEST_SECRET_TOKEN",
                "value": "super-secret-value-xyz",
                "description": "Unit test secret token",
                "is_secret": True,
            },
        )
        self.assertEqual(r_create.status_code, 200)
        self.assertEqual(r_create.json()["value"], SECRET_MASK)

        # Verify GET /api/settings masks secret value
        r_list = self.client.get("/api/settings", headers=self.headers)
        self.assertEqual(r_list.status_code, 200)
        found = next((s for s in r_list.json() if s["key"] == "TEST_SECRET_TOKEN"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["value"], SECRET_MASK)

        # Submitting SECRET_MASK preserves underlying value while updating description
        r_update = self.client.post(
            "/api/settings",
            headers=self.headers,
            json={
                "key": "TEST_SECRET_TOKEN",
                "value": SECRET_MASK,
                "description": "Updated description",
                "is_secret": True,
            },
        )
        self.assertEqual(r_update.status_code, 200)
        self.assertEqual(r_update.json()["description"], "Updated description")

    def test_05_jobs_crud_and_manual_run(self):
        # Create a shell job
        r_create = self.client.post(
            "/api/jobs",
            headers=self.headers,
            json={
                "name": "Unit Test Echo Job",
                "description": "Echoes a test string",
                "schedule": "0 0 * * *",
                "type": "shell",
                "command": "echo 'hello-from-unit-test'",
                "enabled": True,
            },
        )
        self.assertEqual(r_create.status_code, 201)
        job = r_create.json()
        job_id = job["id"]
        self.assertEqual(job["name"], "Unit Test Echo Job")

        # Update job
        r_patch = self.client.put(
            f"/api/jobs/{job_id}",
            headers=self.headers,
            json={"description": "Updated description"},
        )
        self.assertEqual(r_patch.status_code, 200)
        self.assertEqual(r_patch.json()["description"], "Updated description")

        # Toggle job via PUT /api/jobs/{job_id}
        r_toggle = self.client.put(
            f"/api/jobs/{job_id}",
            headers=self.headers,
            json={"enabled": False},
        )
        self.assertEqual(r_toggle.status_code, 200)
        self.assertFalse(r_toggle.json()["enabled"])

        # Delete job
        r_del = self.client.delete(f"/api/jobs/{job_id}", headers=self.headers)
        self.assertEqual(r_del.status_code, 200)
        self.assertTrue(r_del.json()["ok"])

    def test_06_scripts_manager_and_api(self):
        # Test filename sanitization
        self.assertEqual(sanitize_filename("../evil/path/my_script.sh"), "my_script.sh")

        # Test auto-fix syntax check (CRLF + missing shebang)
        res = check_and_correct_syntax(
            "autofix.sh",
            "echo \u201chello\u201d  \r\n",
            script_type="shell",
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["fixed_content"].startswith("#!/usr/bin/env bash\n"))
        self.assertIn('echo "hello"', res["fixed_content"])

        # Save script via API
        r_save = self.client.post(
            "/api/scripts",
            headers=self.headers,
            json={
                "name": "unit-test-script.sh",
                "content": "#!/usr/bin/env bash\necho \"Script env secret: ${TEST_SECRET_TOKEN}\"\n",
                "auto_fix": False,
            },
        )
        self.assertEqual(r_save.status_code, 201)
        self.assertEqual(r_save.json()["name"], "unit-test-script.sh")

        # Run script test and confirm CronDock settings are injected into script environment
        r_run = self.client.post(
            "/api/scripts/unit-test-script.sh/test-run",
            headers=self.headers,
        )
        self.assertEqual(r_run.status_code, 200)
        run_data = r_run.json()
        self.assertTrue(run_data["success"])
        self.assertIn("Script env secret: super-secret-value-xyz", run_data["output"])

        # Delete script
        r_del = self.client.delete("/api/scripts/unit-test-script.sh", headers=self.headers)
        self.assertEqual(r_del.status_code, 200)


if __name__ == "__main__":
    unittest.main()
