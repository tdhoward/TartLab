# Release qualification: operator quick start

The protected **Attest modern qualification candidate** workflow already builds
twice, compares results, runs the host test matrix, and produces the testing
scope. Let it finish without an AI agent polling or narrating each step. Download
the authenticated candidate artifact and the separate checklist artifact from
that same successful run. Keep the candidate directory unchanged.

The checklist artifact includes `operator.ini`, `checklist.md`, and the advanced
JSON template. Open `operator.ini` in any text editor. For a local candidate or older
artifact containing schema-3 metadata, generate them yourself:

```powershell
python tools/qualification_session.py prepare --release build/modern/release --output build/qualification-session
```

Substitute your downloaded candidate directory and form path in these commands
if they differ. The CLI uses the existing candidate validator, including GitHub
CLI signature verification for any signed baseline. Use the release dependencies
and authenticated `gh` described in [DEVELOPMENT.md](DEVELOPMENT.md).

## Fill the form yourself

1. Follow `checklist.md`. It lists global checks, fresh board gates, and evidence
   inherited from the signed baseline. Physical procedures remain in
   [tests/TEST_TIERS.md](tests/TEST_TIERS.md#tier-4-physical-release-qualification),
   [tests/PHASE6_PROVISIONING.md](tests/PHASE6_PROVISIONING.md), and
   [tests/PHASE6_MODERN_QUALIFICATION.md](tests/PHASE6_MODERN_QUALIFICATION.md).
2. Enter your name, actual test completion time in UTC, and the planned durable
   HTTPS URL for final `qualification.json`. Confirm each tested board's prefilled
   identity/memory and fill PCB/chip revisions, then set `confirmed = yes`.
3. Save sanitized results locally. Enter each file's path and durable HTTPS URL
   once in an `[artifact:NAME]` section. Files may be logs or a written report;
   record the exact candidate, boards, steps and observed outcomes. Include the
   successful CI run and automated results in the evidence. Download and preserve
   needed logs; expiring Actions downloads are not durable evidence.
4. For each task, enter the artifact names that establish the result, separated
   by commas, and set `status = passed` only after completing/reviewing it. A
   single report can cover multiple tasks when it documents each outcome. Leave
   unfinished tests `pending`; record unsuccessful tests as `failed`.

Example entries (edit generated sections; do not duplicate them):

```ini
[artifact:results]
path = sanitized-results.md
url = https://example.org/releases/modern-vX.Y.Z/sanitized-results.md

[check:automated]
status = passed
artifacts = results
```

Paths are relative to the form or absolute. Do not quote them. Add another
`[artifact:NAME]` section with `path` and `url` for each additional file. The tool
hashes files automatically. Upload those exact sanitized bytes to their declared
URLs before promotion. Keep private logs, credentials, device identifiers and
the local form private. Publish only sanitized evidence and `qualification.json`.

## Check progress and export

```powershell
python tools/qualification_session.py status --release build/modern/release --form build/qualification-session/operator.ini
python tools/qualification_session.py finalize --release build/modern/release --form build/qualification-session/operator.ini --output build/qualification-session/export
```

`status` lists unfinished tasks and form issues together; exit code 1 means
attention is needed. Save the form and resume whenever convenient. `finalize`
requires every result and hardware observation to pass the existing validator.
It generates:

- `qualification.json`: candidate-bound schema-3 evidence, with hashes of local
  evidence files and inherited gates filled automatically.
- `promotion-inputs.json`: the four exact fields for **Promote tested modern
  release**, including candidate/evidence hashes and the evidence URL.

Publish the exact `qualification.json` bytes to the URL entered in the form, then
copy the four generated values into the existing promotion workflow. These
commands do not publish, operate devices, verify hosted file contents, or
establish the truth of a report; the operator still reviews those claims.
Candidate authentication and protected promotion retain their existing checks.

Exports are never overwritten. If evidence changes, use a new output directory
and its new hash. If the candidate changes, generate a new form and establish
results for that candidate. Do not transplant old form identifiers.

## When to involve the agent

Use the agent for a failed check, unclear physical procedure, or release scope
change. Share short `status` output and a relevant failing log excerpt or local
file paths. Successful routine checks need no transcript review or repetition.
Scope and inheritance come from the generated report. For baseline selection,
build setup, or policy exceptions, see [RELEASE_TOOLING.md](RELEASE_TOOLING.md)
and [RELEASE_POLICY.md](RELEASE_POLICY.md).

This form supports modern schema-3 candidates. Legacy qualification retains its
existing workflow. Changing host tooling changes tracked build inputs and thus
requires fresh platform qualification for the first release using it; the form
does not weaken that classification.
