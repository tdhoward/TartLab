# Phase 6 release security

TartLab authenticates published assets with GitHub Artifact Attestations and
keeps legacy and modern discovery feeds strictly separate.

## Legacy releases

The protected `.github/workflows/promote-legacy-release.yml` workflow rebuilds
a stable tag and attests every TAR/JSON asset with SLSA provenance using the
commit-pinned first-party `actions/attest` action and GitHub's short-lived
Sigstore identity. Policy is locked in
`profiles/release-authenticity.json`.

Verify a downloaded release with:

```text
python tools/check_release_authenticity.py --release path/to/release --source-ref refs/tags/vX.Y.Z --execute
```

A legacy candidate is not authorized until its exact clean tag, checksums, and
sanitized physical evidence pass review in the protected `legacy-release`
environment.

Stable `v0.14` passed this process in workflow run `33265569311`. Its candidate
`checksums.json` SHA-256 is
`95e5cc153728e00ee95ae82a40e718d96a8c098ee52082f6e6cda749c1cde730`;
qualification evidence SHA-256 is
`eeccf7f4db4dbbe061071b1ffda1c3caeaa89be9947f47605633b389acfb4f4c`.
All 19 authenticated TAR/JSON subjects verified against the exact `v0.14` tag,
the protected promotion workflow, and the published Sigstore bundle. The
release is <https://github.com/tdhoward/TartLab/releases/tag/v0.14>.

## Modern qualification and releases

Modern candidates use `modern-manifest.json`, profile `lvgl-modern`, and
repository `tdhoward/TartLab-modern-releases`. The manifest binds the exact
firmware, packages, compatibility declaration, locks, provenance, support
window, and rendered `MIGRATION.md`.

Physical testing starts from an unpublished candidate produced by the protected
`attest-modern-candidate.yml` workflow. It has a qualification signer and no
publish step. Verify it with:

```text
python tools/check_modern_release_authenticity.py --release path/to/candidate --purpose qualification --source-ref refs/tags/modern-vX.Y.Z --execute
```

Final publication uses the distinct protected
`promote-modern-release.yml` signer. It rebuilds twice, checks the candidate
checksum, downloads and hash-verifies the six-gate qualification summary, and
publishes only to the modern repository. Verify a published release with:

```text
python tools/check_modern_release_authenticity.py --release path/to/release --source-ref refs/tags/modern-vX.Y.Z --execute
```

Published alpha reference `modern-v0.14.8` passed this process in workflow run
`33223821198`.
Its candidate `checksums.json` SHA-256 is
`dd17b1d64f527f6d50dcea414bf5068c4b56e64ac93b8c093cb211e357d7d96e`;
qualification evidence SHA-256 is
`1d889e55d969a906c888af9a0ac6c3af355e5b9e6770175b2c5b0e02b7d4d8c8`.
The release is
<https://github.com/tdhoward/TartLab-modern-releases/releases/tag/modern-v0.14.8>.

Adult provisioning performs the attestation check before device mutation.
Any deployed devices validate package hashes, runtime profile, feed/manifest,
and firmware identity, but do not verify Sigstore certificates themselves.
There are currently no field-deployed modern devices, so this reference does
not impose a bridge-release requirement on the first supported multi-board
modern alpha.

## Feed isolation

- `tdhoward/TartLab` is permanently reserved for `legacy-mp123` and legacy
  `manifest.json`.
- `tdhoward/TartLab-modern-releases` is exclusively for `lvgl-modern` and
  `modern-manifest.json`.
- Firmware is an adult-provisioning asset and is never an on-device filesystem
  OTA package.
- CI artifacts, tags, drafts, and qualification artifacts are not public
  deployment channels.

Untouched v0.13 devices cannot filter by runtime profile and count every release
asset during their free-space check. Therefore modern assets must never appear
in the legacy feed, even under different names.

Run the read-only live check with:

```text
python tools/check_release_feed_isolation.py
```

The final `v0.14` post-promotion check observed 15 isolated legacy releases
selecting `v0.14` and one isolated modern release selecting
`modern-v0.14.8`, with no cross-profile assets. The check performed no
mutation.
