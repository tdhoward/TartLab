"""Operator handoff tests using real candidate and evidence validation."""

import contextlib
import io
import subprocess
import sys
import unittest
from unittest import mock

from tests import test_modern_qualification as fixtures
import qualification_session as session
import modern_qualification as qualification
from check_modern_qualification import check
from release_utils import read_json, sha256_file


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.QualificationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        _, self.release = self.fixture.build("candidate")
        self.form = session.prepare(self.release, self.root / "session")

    def load(self):
        form = session.parser()
        form.read(self.form, encoding="utf-8")
        return form

    def save(self, form):
        with self.form.open("w", encoding="utf-8") as stream:
            form.write(stream)

    def complete(self):
        form = self.load()
        form["operator"] = {"name": "Fixture operator", "tested_at_utc": "2026-09-11T18:30:00Z",
                            "evidence_url": "https://example.test/qualification.json"}
        (self.form.parent / "results.txt").write_text("Sanitized fixture results\n", encoding="utf-8")
        form["artifact:results"] = {"path": "results.txt", "url": "https://example.test/results.txt"}
        for name in form.sections():
            if name.startswith("board:"):
                form[name]["pcb_revision"] = "fixture"
                form[name]["chip_revision"] = "fixture-chip"
                form[name]["confirmed"] = "yes"
            if name.startswith(("check:", "gate:")):
                form[name]["status"] = "passed"
        self.save(form)
        return form

    def test_pending_form_reports_all_tasks_and_exports_nothing(self):
        self.assertTrue((self.form.parent / "checklist.md").is_file())
        self.assertEqual(read_json(self.form.parent / "qualification-template.json")["schema"], 3)
        output = self.root / "export"
        _, issues = session.finalize(self.release, self.form, output)
        self.assertFalse(output.exists())
        self.assertTrue(any("operator: fill name" in item for item in issues))
        self.assertTrue(any("check:automated: pending" in item for item in issues))
        self.assertTrue(any("gate:board_alpha:hardware: pending" in item for item in issues))
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = session.main(["status", "--release", str(self.release), "--form", str(self.form)])
        self.assertEqual(code, 1)
        self.assertIn("items need attention", captured.getvalue())

    def test_export_hashes_actual_bytes_and_passes_existing_promotion_validator(self):
        self.complete()
        output = self.root / "export"
        inputs, issues = session.finalize(self.release, self.form, output)
        self.assertEqual(issues, [])
        evidence = output / "qualification.json"
        self.assertEqual(read_json(output / "promotion-inputs.json"), inputs)
        self.assertEqual(inputs["hardware_evidence_sha256"], sha256_file(evidence))
        reference = read_json(evidence)["checks"]["automated"]["evidence"][0]
        self.assertEqual(reference["sha256"], sha256_file(self.form.parent / "results.txt"))
        check(evidence, tag=inputs["tag"], candidate_sha256=inputs["candidate_checksums_sha256"],
              expected_sha256=inputs["hardware_evidence_sha256"], release=self.release)
        with self.assertRaisesRegex(ValueError, "must be new"):
            session.finalize(self.release, self.form, output)

    def test_form_and_export_cannot_write_inside_candidate(self):
        self.complete()
        for output in (self.release / "nested" / "form", self.release.parent):
            with self.assertRaisesRegex(ValueError, "immutable candidate"):
                session.prepare(self.release, output)
            with self.assertRaisesRegex(ValueError, "immutable candidate"):
                session.finalize(self.release, self.form, output)

    def test_changed_evidence_produces_new_hash_without_changing_old_export(self):
        self.complete()
        first, _ = session.finalize(self.release, self.form, self.root / "first-export")
        old_bytes = (self.root / "first-export/qualification.json").read_bytes()
        (self.form.parent / "results.txt").write_bytes(b"Corrected sanitized fixture results")
        second, issues = session.finalize(self.release, self.form, self.root / "second-export")
        self.assertEqual(issues, [])
        self.assertNotEqual(first["hardware_evidence_sha256"], second["hardware_evidence_sha256"])
        self.assertEqual(old_bytes, (self.root / "first-export/qualification.json").read_bytes())

    def test_signature_failure_is_a_concise_blocker(self):
        with mock.patch.object(session, "template", side_effect=subprocess.CalledProcessError(1, "gh")):
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                result = session.main(["status", "--release", str(self.release), "--form", str(self.form)])
        self.assertEqual(result, 1)
        self.assertIn("Qualification blocked:", captured.getvalue())

    def test_stale_form_and_tampered_candidate_are_rejected(self):
        self.complete()
        _, other = self.fixture.build("other", version="modern-v1.0.1")
        _, _, issues = session.inspect(other, self.form)
        self.assertIn("Candidate changed", issues[0])
        (self.release / "filesystem.tar").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            session.inspect(self.release, self.form)

    def test_missing_failed_and_unexpected_fields_block(self):
        mutations = (
            lambda f: f.remove_section("check:automated"),
            lambda f: f["check:automated"].update(status="failed"),
            lambda f: f["check:automated"].update(artifacts="missing"),
            lambda f: f["check:automated"].update(artifacts=""),
            lambda f: f["board:board_alpha"].update(confirmed="no"),
            lambda f: f["board:board_alpha"].update(flash_size_bytes="123"),
            lambda f: f["artifact:results"].update(url="https://example.test/file?secret=hidden"),
            lambda f: f["artifact:results"].update(path="missing.txt"),
            lambda f: f["operator"].update(tested_at_utc="yesterday"),
            lambda f: f["operator"].update(extra="typo"),
            lambda f: f["DEFAULT"].update(status="passed"),
        )
        original = self.form.read_text(encoding="utf-8")
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.form.write_text(original, encoding="utf-8")
                form = self.complete()
                mutate(form)
                self.save(form)
                _, issues = session.finalize(self.release, self.form, self.root / "export")
                self.assertTrue(issues)
                self.assertFalse((self.root / "export").exists())

    def test_inherited_gates_are_generated_without_editable_passes(self):
        baseline = self.fixture.qualified_baseline()
        files = dict(self.fixture.files, **{"files/help/game.py": b"score=100\n"})
        with mock.patch.object(qualification, "verify_signatures"):
            _, self.release = self.fixture.build("app", files=files, baseline=baseline,
                                                request=self.fixture.request(baseline))
            self.form = session.prepare(self.release, self.root / "app-session")
            self.assertNotIn("gate:board_alpha:ota", self.load())
            self.complete()
            evidence, _, issues = session.inspect(self.release, self.form)
            self.assertEqual(issues, [])
            self.assertEqual(evidence["boards"]["board_alpha"]["gates"]["ota"], {
                "status": "passed", "mode": "inherited", "baseline_sha256": baseline["sha256"]})
            form = self.load()
            form["gate:board_alpha:ota"] = {"status": "passed", "artifacts": "results"}
            self.save(form)
            self.assertTrue(session.inspect(self.release, self.form)[2])

    def test_multiple_artifacts_and_boards(self):
        _, self.release = self.fixture.build("two", board_names=("board_alpha", "board_beta"))
        self.form = session.prepare(self.release, self.root / "two-session")
        form = self.complete()
        second = self.form.parent / "second report.txt"
        second.write_bytes(b"Second sanitized result\r\n")
        form["artifact:second"] = {"path": str(second), "url": "https://example.test/second%20report"}
        form["check:automated"]["artifacts"] = "results, second"
        self.save(form)
        evidence, _, issues = session.inspect(self.release, self.form)
        self.assertEqual(issues, [])
        self.assertEqual(len(evidence["boards"]), 2)
        self.assertEqual(evidence["checks"]["automated"]["evidence"][1]["sha256"], sha256_file(second))

    def test_cli_handles_invalid_form_without_traceback(self):
        self.form.write_text("not an INI file", encoding="utf-8")
        result = subprocess.run([sys.executable, str(fixtures.ROOT / "tools/qualification_session.py"),
                                 "status", "--release", str(self.release), "--form", str(self.form)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Qualification blocked:", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
