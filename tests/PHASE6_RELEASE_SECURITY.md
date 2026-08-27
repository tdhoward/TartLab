# Phase 6 release-authenticity policy

## Legacy authenticity policy

TartLab stable release assets are authenticated with GitHub Artifact
Attestations generated only by the protected
`.github/workflows/promote-legacy-release.yml` workflow. The workflow uses the
commit-pinned first-party `actions/attest` action to bind every published TAR
and JSON asset to SLSA build provenance with a short-lived Sigstore signing
certificate. No long-lived signing key is stored in the repository or in a
GitHub Actions secret.

The exact repository, signer workflow, predicate type, action commit, subject
patterns, and scope are locked in `profiles/release-authenticity.json`. The
promotion workflow publishes `release-attestation.sigstore.json` beside the
release assets so an administrator can verify the downloaded files against the
recorded bundle. Online lookup through GitHub remains available as well.
Before building, the workflow requires its GitHub OIDC repository, tag ref, and
commit identity to match the requested stable tag and checked-out commit. This
prevents a run launched from a branch from producing tag-looking provenance.

Verify one downloaded asset for a specific stable tag with:

```text
gh attestation verify manifest.json --repo tdhoward/TartLab --signer-workflow tdhoward/TartLab/.github/workflows/promote-legacy-release.yml --predicate-type https://slsa.dev/provenance/v1 --deny-self-hosted-runners --bundle release-attestation.sigstore.json --source-ref refs/tags/vX.Y.Z
```

Or validate the policy and verify every downloaded TAR/JSON asset with:

```text
python tools/check_release_authenticity.py --release path/to/release --source-ref refs/tags/vX.Y.Z --execute
```

This closes publisher/workflow authentication for the existing stable release
pipeline. It does not claim that deployed MicroPython devices verify Sigstore
certificates. Deployed MicroPython devices still do not verify Sigstore
certificates; the adult-admin modern provisioning tool performs that host-side
enforcement before installation.

## Modern promotion-gated path

The separate modern builder emits `modern-manifest.json`, never the legacy
`manifest.json`. Its versioned object schema declares the isolated
`tdhoward/TartLab-modern-releases` channel, the `lvgl-modern` runtime profile,
and the exact compatible firmware artifact, SHA-256, build lock, provenance,
and runtime source identities. Build metadata continues to list the remaining
promotion gates, so creating or uploading a CI candidate does not claim that
the modern profile is production-qualified.

The candidate is self-contained: `tartlab-modern-vX.Y.Z.bin`, the filesystem
TAR files, `firmware-build-lock.json`, `firmware-provenance.json`,
`filesystem-vendor-lock.json`, `compatibility.json`, and `MIGRATION.md` are all
listed by `modern-manifest.json`, covered by `checksums.json`, and included in
the signed attestation subject set. The migration guide is rendered with the
release's exact version, firmware name, digest, and flash offset, while clearly
retaining the uncompleted physical migration and recovery gates.

Before an adult provisioning or migration tool changes a device, run the
read-only preflight with the identity observed from that device:

```text
python tools/check_modern_release.py --release path/to/release --runtime-profile lvgl-modern --firmware-sha256 187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab
```

The preflight fails closed on a runtime-profile or firmware-hash mismatch and
performs no mutation. The protected `modern-release` environment rebuilds the
candidate twice, requires byte identity, repeats this preflight, binds the
candidate to physical evidence, authenticates every release asset with the
commit-pinned attestation action, and publishes with a target-repository token.
`profiles/modern-release-authenticity.json` statically locks the source and
target repositories, signer workflow, manifest, profile, and preflight.

After downloading every modern release asset, verify the source tag and signed
bundle with:

```text
python tools/check_modern_release_authenticity.py --release path/to/release --source-ref refs/tags/modern-vX.Y.Z --execute
```

This is release machinery, not release authorization. The adult provisioning
host transaction and virtual migration gate are implemented, while physical
provisioning/migration, modern OTA/recovery qualification, the support window,
and the final profile-specific physical gate remain incomplete.

## Release-channel isolation

`tdhoward/TartLab` GitHub Releases are the immutable discovery feed stored on
deployed v0.13 devices and are therefore reserved for the `legacy-mp123`
profile. The old updater selects a release by GitHub prerelease status and tag
inequality; it does not understand profile names, tag prefixes, compatibility
declarations, or alternate manifest filenames. Some devices may also have
prerelease updates enabled.

`lvgl-modern` promotion uses a separate protected workflow that publishes only
to `tdhoward/TartLab-modern-releases`. Its policy binds the source repository
and workflow identity, target release repository, profile, firmware identity,
and hardware evidence. Provisioning must record the modern feed explicitly and
invoke the checked preflight before changing active files.

Modern firmware images and modern filesystem packages must not be attached to a
GitHub Release in `tdhoward/TartLab`, even under different filenames. Besides
making the release visible to legacy users, v0.13 sums every attached asset in
its free-space check before it loads `manifest.json`. Firmware remains an
adult-admin provisioning artifact and cannot be installed by the filesystem
updater.

CI artifacts, plain tags, and draft releases are not device-visible stable
promotion. A release-feed isolation test must fail any modern promotion whose
target is not `tdhoward/TartLab-modern-releases`, and must fail any legacy
promotion containing modern firmware or modern filesystem assets.
