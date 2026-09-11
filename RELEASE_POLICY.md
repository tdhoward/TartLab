# TartLab release policy

TartLab has one public product version. Students update TartLab as a whole;
they do not select separate platform, browser IDE, or example-app versions.
The platform should remain stable across frequent app and browser releases,
with testing effort determined by the behavior and artifacts that change.

## Policy and implementation status

The modern builders and protected workflows implement baseline capture,
platform assembly, change reports, and validation of inherited qualification.
Every included board still needs applicable candidate-bound evidence. Follow
[`RELEASE_TOOLING.md`](RELEASE_TOOLING.md) for the release plan, commands,
schema-3 evidence, and conservative classification rules.

The checked-in plan pins the signed `modern-v0.16.0` baseline. Earlier
published candidates lack the signed snapshot and schema-3 records required
for automatic reuse. Historical modern v0.15.4 evidence remains an audit record
and precedent, not an automatically imported qualification. Routine operators
can use the [generated form workflow](RELEASE_QUALIFICATION.md).

Legacy release gates and profile-specific feed isolation remain in force.
Introducing automated evidence reuse into the legacy workflow would require
its own implementation and validation.

## One public version

Use `MAJOR.MINOR.PATCH` for the product, independently of testing scope:

- **Major:** incompatible changes to student programs or the supported
  installation/runtime contract.
- **Minor:** compatible features in the platform, browser IDE, or apps.
- **Patch:** compatible fixes in any of those areas.

This follows the general [Semantic Versioning convention](https://semver.org/).
While TartLab remains `0.x`, it remains explicitly alpha; a version increment
does not establish a stable API or qualify hardware. Existing `v...` and
`modern-v...` tag conventions and profile-specific feeds remain compatible with
their installed updaters. This policy does not rename historical releases.

A small updater fix may require extensive physical qualification even when
released as a patch. A substantial browser feature may require no hardware
testing. Neither the version number nor a manually chosen release label can
authorize a reduced test scope.

Each product release fixes one complete combination of platform, browser
client, apps, and assets. Internal identities and compatibility records let
tooling select the right board payload without exposing component-version
choices to students. Multiple product releases may share one platform baseline.

Normal updates remain one action to the latest compatible stable TartLab
release. Firmware changes still require authenticated adult provisioning;
filesystem OTA cannot perform them. Keep firmware baselines long-lived to
make routine student updates practical. A single product version does not
remove firmware compatibility checks or combine legacy and modern feeds.

## Qualified platform baseline

A qualified platform baseline identifies the exact implementation and contracts
for which physical evidence exists. It includes:

- each supported board's firmware, declarative configuration, and capabilities;
- shared runtime and libraries, drivers, rendering ownership, startup, and
  platform APIs;
- device-side IDE services, networking, and filesystem access;
- updater, recovery, provisioning behavior, and protected-state rules; and
- package targets, ownership, clearing and selection rules, supported update
  paths, dependencies, toolchain inputs, and resource limits relevant to those
  claims.

The baseline binds these identities to board-specific qualification records.
The shared runtime-profile name or an unchanged firmware hash alone is not
proof that the platform is unchanged. Internal baseline identifiers are
maintainer metadata, not additional student-facing versions.

The browser client and example apps consume this platform contract. App rules,
state, rendering policy, and geometry remain in the app; reusable capabilities
belong in `tartlabutils`. Board parameters remain in declarative board payloads
as described in [`BOARD_SUPPORT.md`](BOARD_SUPPORT.md).

An app/browser release must use the qualified platform content. Unqualified
platform development must not enter that release incidentally through the
current checkout. The assembly tool combines the selected baseline's platform
files with the current built app/browser files and reports excluded platform
changes. Host and installation-contract differences still reject the routine
path. Separate public component releases or repository forks are not required.

## Release paths and test scope

The routine **app/browser path** retains the qualified platform and installation
contract. It runs the normal automated release checks, tests the changed app or
browser behavior, and performs focused physical checks where the change needs
hardware evidence. It carries forward applicable platform qualification.

The **platform path** changes the baseline. It requires fresh qualification for
affected behavior and boards, with full relevant provisioning, interruption,
OTA, and recovery testing for changes to firmware or the update/install
mechanism. New boards always require their own full qualification.

The change matrix in [`tests/TEST_TIERS.md`](tests/TEST_TIERS.md#selecting-release-tests)
defines the starting scope. Classify the complete built candidate, including
dependencies and packaging. A Racer change that modifies a shared renderer is
a platform change. Browser file-saving, device commands, and update controls
need integration coverage beyond a cosmetic browser change. App changes can
require physical memory, input, or timing checks without changing the platform.

Every release runs the normal automated build, integrity, compatibility, and
update/recovery checks applicable to its profile, plus tests of changed
behavior. Validate the complete candidate's package sizes, staging and install
space, API compatibility, and supported update paths. A release changing only
apps does not, by itself, invalidate physical power-loss evidence for an
unchanged update mechanism operating within its qualified contract and limits.

## Reusing qualification evidence

Qualification belongs to specific claims, artifacts, and boards. For each gate
and board, the new candidate record must distinguish fresh results from prior
evidence and explain why any inherited claim still applies.

Compare actual built file inventories and installation semantics with the
qualified baseline, including additions and removals. Account for dependency,
toolchain, configuration, payload-size, and resource-use changes. Source-path
filters help identify likely impact but cannot establish equivalence alone.
If unchanged behavior cannot be established, perform the relevant fresh checks.

Prefer stable, reusable platform artifacts. Build-epoch TAR or gzip metadata can
change archive hashes without changing executable or rendered content. Any
equivalence comparison must identify such differences explicitly, retain exact
archive hashes for authentication, and still check packaging and size effects.
Do not broadly ignore generated files, version fields, or changed runtime bytes.

Reuse only evidence for the same applicable board and firmware identities;
qualification on one board does not qualify another. Review dependencies to
decide whether a shared change affects all supported boards. Focused app smoke
may cover representative capabilities and geometries when justified, while
each included board still needs applicable platform evidence.

Assess updates from the supported installed baselines, not just the immediately
preceding release: those devices initially run their installed updater. Record
which update paths are covered and repeat affected physical gates when their
contracts or implementation change. New evidence must remain tied to the final
candidate, including after any correction or rebuild.

Keep historical evidence immutable. Add a new candidate record referencing
durable prior artifacts and the comparison that justifies reuse. Protected
promotion must still bind the exact candidate, board set, firmware identities,
and evidence; signatures and feed-isolation checks apply to both release paths.

## Routine release process

1. Select the qualified platform baseline and supported board set; prepare the
   intended app/browser changes or identify the platform changes to qualify.
2. Build the complete candidate and run the normal automated release checks.
3. Compare it with the baseline and record changed claims, inherited evidence,
   supported update paths, and the focused or full checks required.
4. Complete those checks and bind their results to the exact final candidate.
5. Promote through the existing protected workflow and verify publication.

The tooling stores signed baseline inventories and evidence bindings, assembles
routine releases, generates a concrete testing checklist, and validates reuse
during promotion. Maintainers review and supply the fresh test results. The
initial classifier is conservative for shared platform changes and checks all
included boards for app smoke; it does not infer a dependency graph or choose
representative hardware automatically. See [`RELEASE_TOOLING.md`](RELEASE_TOOLING.md).
