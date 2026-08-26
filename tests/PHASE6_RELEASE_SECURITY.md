# Phase 6 release-authenticity policy

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
certificates. On-device authenticity, or an adult-admin provisioning tool that
enforces this policy before installation, remains part of the provisioning and
migration work required before modern-profile promotion.
