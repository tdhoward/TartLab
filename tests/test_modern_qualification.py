"""Hardware-free tests of baseline provenance, composition and release gating."""

from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import modern_qualification as qualification
import modern_release_baseline as baseline_tools
from check_modern_qualification import check as check_qualification
from release_utils import file_inventory, read_json, sha256_file, write_json


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = {"host": {"builder": "pinned"}, "browser": {"js/main.js": "pinned"}}
        self.files = {
            "main.py": b"print('boot')\n",
            "defaults/user/hello.py": b"print('hello')\n",
            "lib/tartlabutils/updater.py": b"print('update')\n",
            "board/board_alpha/config.py": b"BOARD_CONFIG={}\n",
            "ide/ide.py": b"print('server')\n",
            "ide/www/index.html.gz": gzip.compress(b"<html>editor</html>", mtime=11),
            "files/help/game.py": b"score=0\n",
            "files/assets/car.txt": b"sprite\n",
        }

    def build(self, name, *, files=None, inputs=None, baseline=None, request=None,
              board_names=("board_alpha",), epoch=123, version="modern-v1.0.0"):
        directory = self.root / name
        dist, release = directory / "dist", directory / "release"
        dist.mkdir(parents=True)
        release.mkdir()
        for path, data in (files or self.files).items():
            target = dist / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        package = release / "filesystem.tar"
        with tarfile.open(package, "w", format=tarfile.USTAR_FORMAT) as archive:
            for item in file_inventory(dist):
                member = tarfile.TarInfo(item["path"])
                member.size = item["size"]
                member.mtime = epoch
                member.mode = 0o644
                archive.addfile(member, io.BytesIO((dist / item["path"]).read_bytes()))
        manifest = {"schema": 1, "profile": qualification.PROFILE, "version": version,
                    "channel": {"repository": qualification.REPOSITORY, "manifest": "modern-manifest.json"},
                    "compatibility": {"runtime_profile": qualification.PROFILE,
                        "boards": {b: {"name": "Fixture " + b, "revisions": ["fixture"],
                                       "flash_size_bytes": 1000000, "psram_size_bytes": 1000000,
                                       "firmware": {"sha256": hashlib.sha256(b.encode()).hexdigest()}}
                                   for b in board_names}},
                    "packages": [{"name": "filesystem", "file_name": package.name,
                                  "target": "/", "clear_first": False, "ownership": "system",
                                  "sha256": sha256_file(package), "archive_size": package.stat().st_size,
                                  "expanded_size": sum(i["size"] for i in file_inventory(dist))}]}
        write_json(release / "modern-manifest.json", manifest)
        write_json(release / "build_metadata.json", {"source_date_epoch": epoch})
        write_json(release / "dist_inventory.json", file_inventory(dist))
        write_json(release / "support-window.json", {"contract": "pinned"})
        if baseline:
            (release / qualification.BASELINE).write_bytes(baseline["path"].read_bytes())
        qualification.write_candidate_metadata(release, request, baseline, inputs or self.inputs)
        self.rehash(release)
        return dist, release

    def rehash(self, release):
        write_json(release / "checksums.json", {p.name: sha256_file(p) for p in sorted(release.iterdir())
            if p.is_file() and p.name not in ("checksums.json", "promotion_attestation.json",
                                             "release-attestation.sigstore.json")})

    def passed_evidence(self, release):
        with mock.patch.object(qualification, "verify_signatures"):
            evidence = baseline_tools.template(release)
        evidence["operator"] = "Test operator"
        evidence["tested_at_utc"] = "2026-09-09T12:00:00Z"
        for board in evidence["boards"].values():
            board["board"]["pcb_revision"] = "fixture"
            board["board"]["chip_revision"] = "fixture"
        reference = {"url": "https://example.test/evidence/record", "sha256": "e" * 64}
        for item in list(evidence["checks"].values()) + [g for b in evidence["boards"].values()
                                                       for g in b["gates"].values() if g["mode"] == "fresh"]:
            item["status"] = "passed"
            item["evidence"] = [reference.copy()]
        return evidence

    def qualified_baseline(self):
        _, release = self.build("base")
        current = read_json(release / qualification.SNAPSHOT)
        # The fixture explicitly qualifies an envelope and installed updater
        # contract; this is never inferred from an old unstructured transcript.
        request = {"schema": 1, "mode": "platform", "resource_limits": {
            b: {key: amount + 100000 for key, amount in usage.items()}
            for b, usage in current["usage"].items()},
            "update_sources": {current["version"]: current["platform_sha256"]}}
        qualification.write_candidate_metadata(release, request, inputs=self.inputs)
        self.rehash(release)
        evidence = self.passed_evidence(release)
        evidence_path = release.parent / "evidence.json"
        write_json(evidence_path, evidence)
        write_json(release / "promotion_attestation.json", {
            "schema": 2, "profile": qualification.PROFILE, "target_repository": qualification.REPOSITORY,
            "tartlab_version": current["version"],
            "boards": {b: r["firmware"]["sha256"] for b, r in current["contract"]["compatibility"]["boards"].items()},
            "candidate_checksums_sha256": sha256_file(release / "checksums.json"),
            "hardware_evidence_sha256": sha256_file(evidence_path)})
        write_json(release / "release-attestation.sigstore.json", {"fixture": "signatures mocked at verification boundary"})
        path = self.root / "baseline.json"
        with mock.patch.object(qualification, "verify_signatures"):
            baseline_tools.capture(release, evidence_path, path)
            baseline = qualification.load_baseline(path)
        baseline["path"] = path
        baseline["release"] = release
        return baseline

    def request(self, baseline, mode="app-browser"):
        return dict(copy.deepcopy(baseline["report"]["request"]), mode=mode)

    def test_first_candidate_requires_all_fresh_gates_and_draft_cannot_pass(self):
        _, release = self.build("first")
        current, analysis = qualification.check_candidate(release)
        self.assertTrue(analysis["platform_changed"])
        self.assertTrue(all(d["mode"] == "fresh" for d in analysis["boards"]["board_alpha"].values()))
        draft = baseline_tools.template(release)
        with self.assertRaises(ValueError):
            qualification.validate_results(draft, analysis, current, sha256_file(release / "checksums.json"),
                                           sha256_file(release / qualification.REPORT))

    def test_standalone_report_and_template_commands(self):
        _, release = self.build("cli")
        for action, extension in (("report", "md"), ("template", "json")):
            output = self.root / (action + "." + extension)
            subprocess.run([sys.executable, str(ROOT / "tools/modern_release_baseline.py"),
                            action, "--release", str(release), "--output", str(output)],
                           cwd=self.root, check=True, capture_output=True, text=True)
            self.assertTrue(output.is_file())

    def test_library_build_is_offline_and_cli_selects_the_checked_in_plan(self):
        from build_modern_release import parse_args
        from tests.test_phase6 import ModernReleaseTests
        args = parse_args(["--dist", "dist", "--output", "output", "--version", "modern-v1.0.0"])
        self.assertEqual(args.qualification_plan, baseline_tools.DEFAULT_PLAN)
        with mock.patch.object(baseline_tools, "load_plan", side_effect=AssertionError("Unexpected live baseline")):
            ModernReleaseTests()._build(self.root)

    def test_game_change_reuses_update_evidence_but_requires_focused_hardware(self):
        baseline = self.qualified_baseline()
        files = dict(self.files, **{"files/help/game.py": b"score=100\n"})
        _, release = self.build("game", files=files, baseline=baseline, request=self.request(baseline))
        analysis = read_json(release / qualification.REPORT)
        gates = analysis["boards"]["board_alpha"]
        self.assertFalse(analysis["platform_changed"])
        self.assertEqual(gates["hardware"]["mode"], "fresh")
        for name in ("adult_provisioning", "ota", "recovery"):
            self.assertEqual(gates[name]["mode"], "inherited")
        self.assertEqual(gates["release_feed_isolation"]["mode"], "fresh")
        evidence = self.passed_evidence(release)
        path = self.root / "game-evidence.json"
        write_json(path, evidence)
        with mock.patch.object(qualification, "verify_signatures"):
            self.assertEqual(check_qualification(path, tag=evidence["version"],
                candidate_sha256=sha256_file(release / "checksums.json"), release=release)["passed_gates"], list(qualification.GATES))

    def test_cosmetic_browser_change_needs_browser_checks_without_physical_smoke(self):
        baseline = self.qualified_baseline()
        files = dict(self.files, **{"ide/www/index.html.gz": gzip.compress(b"<html>new label</html>", mtime=22)})
        _, release = self.build("cosmetic", files=files, baseline=baseline, request=self.request(baseline))
        analysis = read_json(release / qualification.REPORT)
        self.assertIn("browser", analysis["checks"])
        self.assertEqual(analysis["boards"]["board_alpha"]["hardware"]["mode"], "inherited")

    def test_browser_javascript_or_dependency_change_requires_device_integration(self):
        baseline = self.qualified_baseline()
        inputs = copy.deepcopy(self.inputs)
        inputs["browser"]["js/main.js"] = "changed"
        _, release = self.build("js", inputs=inputs, baseline=baseline, request=self.request(baseline))
        self.assertEqual(read_json(release / qualification.REPORT)["boards"]["board_alpha"]["hardware"]["mode"], "fresh")

    def test_gzip_timestamp_and_tar_epoch_do_not_invalidate_content_evidence(self):
        baseline = self.qualified_baseline()
        data = self.files["ide/www/index.html.gz"]
        files = dict(self.files, **{"ide/www/index.html.gz": data[:4] + (500).to_bytes(4, "little") + data[8:]})
        _, release = self.build("timestamp", files=files, epoch=999, baseline=baseline, request=self.request(baseline))
        analysis = read_json(release / qualification.REPORT)
        self.assertEqual(analysis["changed_files"], [])
        self.assertEqual(analysis["gzip_timestamp_only"], ["/ide/www/index.html.gz"])

    def test_platform_or_unknown_file_changes_cannot_use_routine_path(self):
        baseline = self.qualified_baseline()
        for index, path in enumerate(("lib/tartlabutils/updater.py", "unknown.py", "board/board_alpha/config.py")):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "changed the qualified platform"):
                self.build("platform%d" % index, files=dict(self.files, **{path: b"changed\n"}),
                           baseline=baseline, request=self.request(baseline))

    def test_host_build_dependency_change_invalidates_platform(self):
        baseline = self.qualified_baseline()
        inputs = copy.deepcopy(self.inputs)
        inputs["host"]["builder"] = "changed"
        with self.assertRaisesRegex(ValueError, "host contract"):
            self.build("host", inputs=inputs, baseline=baseline, request=self.request(baseline))

    def test_new_board_requires_full_qualification_and_no_default_board_inheritance(self):
        baseline = self.qualified_baseline()
        request = dict(self.request(baseline, "platform"), resource_limits={})
        _, release = self.build("boards", baseline=baseline, request=request,
                                board_names=("board_alpha", "board_beta"))
        gates = read_json(release / qualification.REPORT)["boards"]["board_beta"]
        self.assertTrue(all(g["mode"] == "fresh" for g in gates.values()))
        existing = read_json(release / qualification.REPORT)["boards"]["board_alpha"]
        self.assertEqual(existing["hardware"]["mode"], "inherited")

    def test_storage_envelope_growth_and_new_updater_sources_require_fresh_tests(self):
        baseline = self.qualified_baseline()
        for index, cause in enumerate(("limits", "sources", "missing_sources")):
            request = self.request(baseline)
            if cause == "limits":
                request["resource_limits"]["board_alpha"]["expanded_bytes"] += 1
            elif cause == "sources":
                request["update_sources"]["modern-v0.9.0"] = "f" * 64
            else:
                request["update_sources"] = {}
            _, release = self.build("growth%d" % index, baseline=baseline, request=request)
            gates = read_json(release / qualification.REPORT)["boards"]["board_alpha"]
            self.assertEqual(gates["ota"]["mode"], "fresh")
            self.assertEqual(gates["recovery"]["mode"], "fresh")

    def test_removed_app_file_is_reported(self):
        baseline = self.qualified_baseline()
        files = {p: d for p, d in self.files.items() if p != "files/help/game.py"}
        _, release = self.build("removed", files=files, baseline=baseline, request=self.request(baseline))
        self.assertIn({"path": "/files/help/game.py", "component": "apps", "change": "removed"},
                      read_json(release / qualification.REPORT)["changed_files"])

    def test_composition_restores_exact_platform_and_drops_unqualified_platform_additions(self):
        baseline = self.qualified_baseline()
        files = dict(self.files, **{"lib/tartlabutils/updater.py": b"unqualified\n",
                                  "lib/new.py": b"unqualified\n", "files/help/game.py": b"score=5\n"})
        dist, _ = self.build("working", files=files)
        output = self.root / "assembled"
        baseline_tools.assemble(dist, output, baseline, baseline["release"])
        self.assertEqual((output / "lib/tartlabutils/updater.py").read_bytes(), self.files["lib/tartlabutils/updater.py"])
        self.assertFalse((output / "lib/new.py").exists())
        self.assertEqual((output / "files/help/game.py").read_bytes(), b"score=5\n")
        self.assertEqual((dist / "lib/tartlabutils/updater.py").read_bytes(), b"unqualified\n")

    def test_bad_baseline_archive_is_rejected_before_existing_output_is_changed(self):
        baseline = self.qualified_baseline()
        output = self.root / "existing"
        output.mkdir()
        (output / "keep").write_text("keep")
        (baseline["release"] / "filesystem.tar").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "archive checksum"):
            baseline_tools.assemble(baseline["release"].parent / "dist", output, baseline,
                                    baseline["release"], clean=True)
        self.assertEqual((output / "keep").read_text(), "keep")

    def test_archive_traversal_links_duplicates_and_file_directory_collisions_fail(self):
        _, release = self.build("unsafe")
        manifest = read_json(release / "modern-manifest.json")
        archive_path = release / "filesystem.tar"
        cases = (("../escape.py",), ("/absolute.py",), ("a\\b.py",),
                 ("C:/outside.py",), ("link",), ("same", "same"), ("file", "file/child"))
        for names in cases:
            with self.subTest(names=names):
                with tarfile.open(archive_path, "w", format=tarfile.USTAR_FORMAT) as archive:
                    for name in names:
                        member = tarfile.TarInfo(name)
                        member.mtime = 123
                        member.mode = 0o644
                        member.size = 1
                        if name == "link":
                            member.type = tarfile.SYMTYPE
                            member.linkname = "../outside"
                            member.size = 0
                        archive.addfile(member, io.BytesIO(b"x"))
                package = manifest["packages"][0]
                package.update(sha256=sha256_file(archive_path), archive_size=archive_path.stat().st_size,
                               expanded_size=len(names))
                with self.assertRaises(ValueError):
                    qualification.payload_files(release, manifest, 123)

    def test_output_cannot_delete_sources_or_its_own_input(self):
        dist, _ = self.build("source")
        for path in (dist, dist / "child", ROOT / "src", ROOT / "tools/subdir"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                baseline_tools.assemble(dist, path, clean=True)

    def test_baseline_hash_and_signed_document_tampering_fail(self):
        baseline = self.qualified_baseline()
        with self.assertRaisesRegex(ValueError, "Pinned baseline"):
            qualification.load_baseline(baseline["path"], "0" * 64)
        capsule = read_json(baseline["path"])
        capsule["documents"][qualification.SNAPSHOT] += " "
        write_json(baseline["path"], capsule)
        with self.assertRaisesRegex(ValueError, "signed checksum"):
            qualification.load_baseline(baseline["path"])

    def test_signature_failure_is_not_downgraded_to_a_warning(self):
        baseline = self.qualified_baseline()
        with mock.patch.object(qualification.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "gh")):
            with self.assertRaises(subprocess.CalledProcessError):
                qualification.load_baseline(baseline["path"])

    def test_baseline_pin_survives_git_checkout_line_endings(self):
        baseline = self.qualified_baseline()
        data = baseline["path"].read_bytes().replace(b"\r\n", b"\n")
        for newline in (b"\n", b"\r\n"):
            baseline["path"].write_bytes(data.replace(b"\n", newline))
            with mock.patch.object(qualification, "verify_signatures"):
                self.assertEqual(qualification.load_baseline(baseline["path"], baseline["sha256"])["sha256"],
                                 baseline["sha256"])

    def test_verification_requires_promotion_signer_and_exact_source_tag(self):
        baseline = self.qualified_baseline()
        with mock.patch.object(qualification.subprocess, "run") as run:
            qualification.load_baseline(baseline["path"])
        self.assertEqual(run.call_count, 4)
        for call in run.call_args_list:
            command = call.args[0]
            self.assertIn("refs/tags/modern-v1.0.0", command)
            self.assertIn("tdhoward/TartLab/.github/workflows/promote-modern-release.yml", command)
            self.assertIn("--deny-self-hosted-runners", command)

    def test_forged_report_with_new_checksums_is_recomputed_and_rejected(self):
        _, release = self.build("tampered")
        analysis = read_json(release / qualification.REPORT)
        analysis["boards"]["board_alpha"]["ota"]["mode"] = "inherited"
        write_json(release / qualification.REPORT, analysis)
        self.rehash(release)
        with self.assertRaisesRegex(ValueError, "altered or is stale"):
            qualification.check_candidate(release)

    def test_missing_new_metadata_and_legacy_schema_cannot_bypass_gates(self):
        _, release = self.build("bypass")
        path = self.root / "legacy.json"
        write_json(path, {"schema": 2})
        with self.assertRaisesRegex(ValueError, "schema-3"):
            check_qualification(path, tag="modern-v1.0.0",
                candidate_sha256=sha256_file(release / "checksums.json"), release=release)
        checksums = read_json(release / "checksums.json")
        del checksums[qualification.REQUEST]
        write_json(release / "checksums.json", checksums)
        with self.assertRaisesRegex(ValueError, "missing qualification metadata"):
            qualification.check_candidate(release)

    def test_each_declared_board_and_fresh_check_needs_its_own_evidence(self):
        _, release = self.build("results")
        evidence = self.passed_evidence(release)
        current, analysis = qualification.check_candidate(release)
        for mutation in ("board", "pending", "baseline", "reference", "pcb", "memory"):
            value = copy.deepcopy(evidence)
            if mutation == "board":
                value["boards"] = {}
            elif mutation == "pending":
                value["checks"]["automated"]["status"] = "pending"
            elif mutation == "baseline":
                value["boards"]["board_alpha"]["gates"]["ota"] = {
                    "status": "passed", "mode": "inherited", "baseline_sha256": "f" * 64}
            elif mutation == "reference":
                value["checks"]["automated"]["evidence"][0]["url"] = "http://example.test/evidence"
            elif mutation == "pcb":
                value["boards"]["board_alpha"]["board"]["pcb_revision"] = "unqualified"
            else:
                value["boards"]["board_alpha"]["board"]["flash_size_bytes"] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                qualification.validate_results(value, analysis, current,
                    sha256_file(release / "checksums.json"), sha256_file(release / qualification.REPORT))


if __name__ == "__main__":
    unittest.main()
