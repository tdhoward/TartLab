"""Prepare, inspect and finalize an operator form for a modern candidate.

No device access, publishing, or inferred passes. The existing candidate and
evidence validators remain authoritative; this is only an operator interface.
"""

from __future__ import annotations

import argparse
import configparser
from datetime import datetime
import io
import json
from pathlib import Path
import subprocess

from modern_qualification import REPORT, SNAPSHOT, _references, validate_results
from modern_release_baseline import checklist, template
from release_utils import read_json, sha256_file, write_json


def parser():
    result = configparser.ConfigParser(interpolation=None)
    result.optionxform = str
    return result


def tasks(evidence):
    for name, result in evidence["checks"].items():
        yield "check:" + name, result
    for board, record in evidence["boards"].items():
        for gate, result in record["gates"].items():
            if result["mode"] == "fresh":
                yield "gate:" + board + ":" + gate, result


def form_for(evidence):
    form = parser()
    form["candidate"] = {key: evidence[key] for key in (
        "version", "candidate_checksums_sha256", "report_sha256")}
    form["operator"] = {"name": "", "tested_at_utc": "", "evidence_url": ""}
    form["artifact:results"] = {"path": "", "url": ""}
    for board, record in evidence["boards"].items():
        # Require explicit confirmation even if an earlier operator used the
        # same board model. A fresh session might use a different physical unit.
        form["board:" + board] = {
            key: str(value) for key, value in record["board"].items()}
        form["board:" + board]["confirmed"] = "no"
    for name, _ in tasks(evidence):
        form[name] = {"status": "pending", "artifacts": "results"}
    return form


def new_output(path, release, *inputs):
    target = path.resolve()
    candidate = release.resolve()
    if target == candidate or candidate in target.parents or target in candidate.parents:
        raise ValueError("Output must be outside the immutable candidate directory")
    if target.exists() or any(target == p.resolve() or target in p.resolve().parents
                              for p in inputs):
        raise ValueError("Output must be new and must not contain an input")
    return target


def prepare(release, output):
    output = new_output(output, release)
    evidence = template(release)  # Verifies bytes, report and signed baseline.
    analysis = read_json(release / REPORT)
    buffer = io.StringIO()
    form_for(evidence).write(buffer)
    output.mkdir(parents=True)
    write_json(output / "qualification-template.json", evidence)
    (output / "operator.ini").write_text(
        "# Fill this form in a text editor. Save and rerun status at any time.\n"
        "# Follow checklist.md and RELEASE_QUALIFICATION.md. Do not edit candidate IDs.\n"
        "# UTC example: 2026-09-11T18:30:00Z (actual test completion time).\n"
        "# evidence_url: planned durable HTTPS URL for final qualification.json.\n"
        "# Artifacts: local sanitized files plus their durable HTTPS URLs.\n"
        "# Paths are relative to this form, or absolute; do not add quotes.\n"
        "# Add [artifact:NAME] sections as needed; reference names separated by commas.\n"
        "# One results file may cover multiple tasks if it records each outcome.\n"
        "# Set confirmed = yes after checking each physical board's details.\n"
        "# Set each status to passed only after performing/reviewing that test.\n"
        "# pending and failed block finalization. Inherited gates need no entries.\n\n"
        + buffer.getvalue(), encoding="utf-8")
    (output / "checklist.md").write_text(checklist(analysis), encoding="utf-8")
    return output / "operator.ini"


def inspect(release, path):
    evidence = template(release)
    current = read_json(release / SNAPSHOT)
    analysis = read_json(release / REPORT)
    expected = form_for(evidence)
    form = parser()
    with path.open(encoding="utf-8-sig") as stream:
        form.read_file(stream)
    issues = []
    if form.defaults():
        issues.append("DEFAULT values are not allowed; fill each field explicitly")
    required = set(expected.sections()) - {"artifact:results"}
    for name in sorted(required - set(form.sections())):
        issues.append("Missing section: " + name)
    for name in form.sections():
        if name not in required and not name.startswith("artifact:"):
            issues.append("Unexpected section: " + name)
            continue
        keys = {"path", "url"} if name.startswith("artifact:") else set(expected[name])
        if set(form[name]) != keys:
            issues.append("Fields differ in " + name + "; expected " + ", ".join(sorted(keys)))
    if issues:
        return evidence, None, issues
    if dict(form["candidate"]) != dict(expected["candidate"]):
        return evidence, None, ["Candidate changed; prepare a new form and qualify the new candidate"]

    operator = form["operator"]
    evidence["operator"] = operator["name"].strip()
    evidence["tested_at_utc"] = operator["tested_at_utc"].strip()
    if not evidence["operator"]:
        issues.append("operator: fill name")
    try:
        stamp = evidence["tested_at_utc"]
        if not stamp.endswith("Z"):
            raise ValueError()
        datetime.fromisoformat(stamp[:-1] + "+00:00")
    except ValueError:
        issues.append("operator: fill tested_at_utc with the actual UTC test time ending in Z")
    try:
        _references([{"url": operator["evidence_url"], "sha256": "0" * 64}])
    except ValueError as exc:
        issues.append("operator.evidence_url: " + str(exc))

    references = {}
    used = {alias.strip() for name, _ in tasks(evidence)
            for alias in form[name]["artifacts"].split(",") if alias.strip()}
    for alias in sorted(used):
        section = "artifact:" + alias
        if section not in form:
            issues.append("Missing section: " + section)
            continue
        record = form[section]
        try:
            if not record["path"].strip():
                raise ValueError("fill path to a sanitized results file")
            local = path.parent / record["path"]
            reference = {"url": record["url"], "sha256": sha256_file(local)}
            _references([reference])
            references[alias] = reference
        except (ValueError, OSError) as exc:
            issues.append(section + ": " + str(exc))

    for board, record in evidence["boards"].items():
        name = "board:" + board
        observed = dict(form[name])
        if observed.pop("confirmed") != "yes":
            issues.append(name + ": confirm the physical board details with confirmed = yes")
        identity = current["contract"]["compatibility"]["boards"][board]
        for key in ("flash_size_bytes", "psram_size_bytes"):
            try:
                observed[key] = int(observed[key])
            except ValueError:
                issues.append(name + ": " + key + " must be an integer")
        if observed["pcb_revision"] not in identity["revisions"]:
            issues.append(name + ": pcb_revision must be one of " + ", ".join(identity["revisions"]))
        if not observed["chip_revision"].strip():
            issues.append(name + ": fill chip_revision")
        for key in ("model", "flash_size_bytes", "psram_size_bytes"):
            if observed[key] != identity["name" if key == "model" else key]:
                issues.append(name + ": " + key + " differs from candidate hardware")
        record["board"] = observed
    for name, result in tasks(evidence):
        result["status"] = form[name]["status"]
        if result["status"] != "passed":
            issues.append(name + ": " + result["status"])
        aliases = [s.strip() for s in form[name]["artifacts"].split(",") if s.strip()]
        if not aliases:
            issues.append(name + ": select at least one artifact")
        result["evidence"] = [references[a] for a in aliases if a in references]
    if not issues:
        validate_results(evidence, analysis, current,
                         evidence["candidate_checksums_sha256"], evidence["report_sha256"])
    return evidence, operator["evidence_url"], issues


def finalize(release, form, output):
    output = new_output(output, release, form)
    evidence, url, issues = inspect(release, form)
    if issues:
        return None, issues
    # Never overwrite a previously exported qualification or its hashes.
    output.mkdir(parents=True)
    path = output / "qualification.json"
    write_json(path, evidence)
    inputs = {"tag": evidence["version"],
              "candidate_checksums_sha256": evidence["candidate_checksums_sha256"],
              "hardware_evidence_sha256": sha256_file(path),
              "hardware_evidence_reference": url}
    write_json(output / "promotion-inputs.json", inputs)
    return inputs, []


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest="action", required=True)
    for name in ("prepare", "status", "finalize"):
        action = actions.add_parser(name)
        action.add_argument("--release", type=Path, required=True)
        if name != "prepare":
            action.add_argument("--form", type=Path, required=True)
        if name != "status":
            action.add_argument("--output", type=Path, required=True)
    args = cli.parse_args(argv)
    try:
        if args.action == "prepare":
            print("Prepared " + str(prepare(args.release, args.output)))
            return 0
        if args.action == "status":
            evidence, _, issues = inspect(args.release, args.form)
            count = sum(1 for _ in tasks(evidence))
            print("%s: %d fresh tasks; %d items need attention" % (
                evidence["version"], count, len(issues)))
        else:
            inputs, issues = finalize(args.release, args.form, args.output)
            if not issues:
                print("Validated export: " + str(args.output))
                print(json.dumps(inputs, indent=2))
        for issue in issues:
            print("- " + issue)
        return 1 if issues else 0
    except (ValueError, OSError, configparser.Error, subprocess.CalledProcessError) as exc:
        print("Qualification blocked: " + str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
