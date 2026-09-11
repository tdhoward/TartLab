# Modern release qualification tooling

For routine operation, start with the short
[operator quick start](RELEASE_QUALIFICATION.md). Its generated text form and
`qualification_session.py` report pending work, hash evidence files, validate
results, and export promotion inputs without agent orchestration.

The modern release pipeline implements the model in
[`RELEASE_POLICY.md`](RELEASE_POLICY.md). One TartLab release contains a fixed
platform, browser client, and app set. Maintainers select its qualification
baseline in [`profiles/modern-release-plan.json`](profiles/modern-release-plan.json);
students continue to update the product as a whole.

## What runs automatically

Every modern candidate includes these authenticated JSON subjects:

- `qualification-snapshot.json`: the installed file inventory, exact and
  gzip-timestamp-normalized hashes, per-board platform identities, installation
  contracts, build inputs, and per-board storage usage;
- `qualification-request.json`: the selected release mode, resource envelope,
  and supported installed-source contracts;
- `qualification-report.json`: changed files, metadata-only differences,
  required checks, and fresh/inherited decisions for each board and gate; and
- `platform-baseline.json`, when selected: a capsule containing the exact signed
  snapshot, report, checksums, promotion record, evidence, and signature bundle
  from a previously promoted release.

These are maintainer metadata, not device OTA packages. The builder includes
them in candidate checksums and the existing workflows sign them. Promotion
recomputes the snapshot and report from the complete candidate, verifies the
baseline's signatures against the protected **release** signer and source tag,
and validates schema-3 evidence against the resulting requirements. A
qualification-signer attestation alone cannot establish a reusable baseline.

The qualification workflow also uploads a separate checklist and pending
evidence form. Pending results do not pass promotion; the tooling does not
invent physical observations or complete tests on an operator's behalf.

## Establish the first baseline

The checked-in plan remains in `platform` mode and now pins the authenticated
`modern-v0.16.0` baseline in `profiles/baselines/modern-v0.16.0.json`. That
release established the first baseline with fresh evidence for all five gates
on both included boards. Earlier published
releases, including `modern-v0.15.4`, lack these signed snapshots and schema-3
records. Their historical evidence is preserved, but it cannot be imported as
an automatically reusable baseline by this tool.

Build and qualify the first candidate with this tooling through the existing
protected workflow. Complete the generated schema-3 form, publish the sanitized
evidence at a durable HTTPS URL, and promote with the usual candidate checksum,
evidence checksum, and evidence-reference inputs. After promotion, download the
published release and its exact qualification evidence, then run:

```powershell
python tools/modern_release_baseline.py capture --release path/to/published-release --evidence path/to/qualification.json --output profiles/baselines/modern-vX.Y.Z.json
```

Capture verifies four signed subjects and all candidate/evidence bindings before
writing the capsule. GitHub CLI (`gh`) must be available and able to verify
GitHub Artifact Attestations. There is no CLI switch that bypasses signature
verification. Preserve the printed SHA-256 in the release plan and commit both
the capsule and the plan. Capsule pins hash its LF-normalized source bytes so
Git's Windows/Linux checkout conversion cannot break the pin; the embedded
signed documents retain their exact original bytes.

## Select a release path

The release plan has these fields:

| Field | Meaning |
| --- | --- |
| `schema` | Currently `1`. |
| `mode` | `platform` builds current platform content; `app-browser` assembles the selected qualified platform with current app/browser content. |
| `baseline` | `null`, or an object containing the capsule's checkout-relative `path` and printed `sha256`. Required in `app-browser` mode. |
| `resource_limits` | Empty to use this candidate's measured sizes, or a board-ID map containing `archive_bytes` and `expanded_bytes` limits for each included board. |
| `update_sources` | A map from supported source release tags to their `qualification-snapshot.json` `platform_sha256` values. |

For a routine release, select the captured capsule and set `mode` to
`app-browser`. Retain the qualified resource envelope unless it needs to grow,
and declare the installed versions the release must support. For platform work,
use `platform` mode; a selected baseline still lets the report identify which
boards and claims changed. With no baseline, everything requires fresh evidence.

An empty `resource_limits` object does not invent headroom: it uses measured
candidate sizes. Growth beyond the baseline's qualified envelope requires fresh
provisioning, OTA, and recovery evidence. A larger declared envelope is a test
claim: the operator must establish its staging/install margins and relevant
interruption behavior before marking those results passed. Download limits
count all archives; expanded limits count only the selected board subtree.
Runtime heap, rendering, and timing remain part of focused hardware testing.

An empty `update_sources` map prevents automatic reuse of OTA/recovery evidence.
To qualify source coverage, declare the actual installed releases and their
recorded platform identities before building the final candidate, and include
those paths in the fresh results. Different release tags with the same exact
platform contract can reuse qualified source coverage. A new source contract
requires fresh OTA/recovery results even when the destination platform is
unchanged. The global `update_paths` check must still establish that each named
installed release actually has the declared identity; editing the map is not
proof of a tested source.

## Build locally

Use the existing setup and board-selection instructions in
[`DEVELOPMENT.md`](DEVELOPMENT.md). These steps operate on generated output:

```powershell
python tools/modern_release_baseline.py prepare
python makedist.py --output build/modern/source-dist --clean --skip-web-build --board BOARD_ID
python tools/modern_release_baseline.py assemble --dist build/modern/source-dist --output build/modern/dist --clean
python tools/build_modern_release.py --dist build/modern/dist --output build/modern/release --version modern-vX.Y.Z --clean --board BOARD_ID
python tools/modern_release_baseline.py report --release build/modern/release --output build/modern/checklist.md
python tools/modern_release_baseline.py template --release build/modern/release --output build/modern/qualification.json
```

Build the browser first as usual; repeat `--board` on both build commands for
every included board. The protected workflows already perform preparation,
assembly, deterministic double builds, and checks. `prepare` downloads baseline
TARs only for app/browser composition and checks them against signed checksums.
The cache defaults to `build/modern-baseline`; corrupt cache entries fail rather
than being silently accepted. Remove or replace the identified generated cache
entry before retrying.

Assembly writes a separate distribution. It takes `/files/help`, `/files/assets`,
and `/ide/www` from the current built distribution and takes all managed
platform files from the baseline archives. It also reports the source platform
changes it excluded. Protected provisioning defaults must match the baseline.
Host build/provisioning code and installation contracts must still match for
the app/browser path; assembly cannot conceal a changed host tool or firmware.
The builder rejects an app/browser candidate with differing platform content.

The default plan is checked in and used by CI. Local `--plan` options on prepare
and assemble and `--qualification-plan` on the builder allow experiments, but
protected promotion must reproduce the plan committed at the release tag.
Keep checklists and editable evidence outside the immutable release directory.

## Complete and validate evidence

Schema-3 evidence binds the candidate checksum, report checksum, operator, UTC
test date, and every board's firmware and physical hardware observations.
Fill or confirm the PCB/chip revision and memory values for the tested board;
the validator checks them against the compatibility declaration. Global checks and fresh gates each need
`status: passed` and one or more `{ "url": "https://...", "sha256": "..." }`
records pointing to durable sanitized results. Inherited gates reference the
exact baseline capsule identity; they cannot substitute for a required fresh
gate. The generated form supplies the expected structure.

Validate the completed record before promotion:

```powershell
python tools/check_modern_qualification.py --release build/modern/release --evidence build/modern/qualification.json --tag modern-vX.Y.Z --candidate-checksums-sha256 CANDIDATE_HASH --expected-sha256 EVIDENCE_HASH
```

Rebuilding after a correction changes the candidate binding. Generate a new
report/form and complete the requirements for that candidate. The record
validator checks structure and bindings; maintainers still review the contents
and truth of the referenced test evidence, as with existing physical gates.

## Conservative classification boundaries

- App changes request focused app/resource/exit checks on every included board.
  Automatic representative-board reduction is not implemented.
- CSS and static asset changes require browser checks. JavaScript, HTML (which
  can contain inline scripts), dependency, webpack, or Node changes also request
  browser/device integration smoke.
- Shared platform or host-tool changes require full relevant physical gates on
  affected boards. Unknown managed paths are platform content. The initial
  classifier deliberately does not infer a fine-grained shared dependency graph.
- A board-only payload/firmware change invalidates that board's platform claims.
  Shared contract changes and storage/source effects can still affect other boards.
- Only TAR build metadata and the four gzip timestamp bytes receive explicit
  metadata treatment; executable content, modes, installation order, ownership,
  and clearing/selection semantics remain significant.
- Automated checks, resource checks, declared update-path checks, and current
  feed isolation always need current evidence. An unchanged baseline never
  substitutes for those candidate-specific checks.

Run the tooling's hardware-free regression tests with:

```text
python -m unittest tests.test_modern_qualification tests.test_phase6 tests.test_modern_profile tests.test_board_catalog tests.test_phase6_provisioning -v
```

Legacy evidence and promotion retain their existing behavior. The new snapshot
and schema-3 requirements apply to candidates built by the modern tooling.
