"""Validate the live legacy/modern GitHub Release feeds without mutation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
LEGACY_REPOSITORY = "tdhoward/TartLab"
MODERN_REPOSITORY = "tdhoward/TartLab-modern-releases"
MODERN_ONLY_ASSETS = {
    "modern-manifest.json",
    "compatibility.json",
    "firmware-build-lock.json",
    "firmware-provenance.json",
    "filesystem-vendor-lock.json",
    "support-window.json",
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def validate_policy(root: Path = ROOT):
    legacy = load_json(root / "tests/fixtures/legacy_mp123/layout/repos.json")
    entries = [item for item in legacy.get("list", []) if item.get("name") == "TartLab"]
    if len(entries) != 1 or entries[0].get("repo", "").lower() != \
            LEGACY_REPOSITORY.lower():
        raise ValueError("Legacy fixture does not use the reserved legacy feed")

    modern = load_json(root / "profiles/lvgl-modern.json")
    channel = modern.get("release_channel", {})
    if channel.get("repository") != MODERN_REPOSITORY or \
            channel.get("manifest") != "modern-manifest.json":
        raise ValueError("Modern profile does not use the isolated modern feed")
    if channel.get("legacy_repository") != LEGACY_REPOSITORY or \
            channel.get("legacy_feed_allowed") is not False:
        raise ValueError("Modern profile permits the legacy feed")
    status = modern.get("status")
    if status not in ("promotion-gated-unreleased", "published"):
        raise ValueError("Modern profile has an unknown release status")
    return status == "promotion-gated-unreleased"


def _assets(release):
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Release assets are missing")
    names = []
    for asset in assets:
        name = asset.get("name") if isinstance(asset, dict) else None
        if not isinstance(name, str) or not name:
            raise ValueError("Release has an invalid asset name")
        names.append(name)
    if len(names) != len(set(names)):
        raise ValueError("Release contains duplicate asset names")
    return names


def _stable(releases):
    return next((release for release in releases
                 if not release.get("draft", False) and
                 not release.get("prerelease", False)), None)


def validate_feeds(legacy_releases, modern_releases, *, expect_modern_empty):
    if not isinstance(legacy_releases, list) or not legacy_releases:
        raise ValueError("Legacy release feed is empty")
    if not isinstance(modern_releases, list):
        raise ValueError("Modern release feed response is invalid")

    for release in legacy_releases:
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag:
            raise ValueError("Legacy release has no tag")
        names = _assets(release)
        lowered = {name.lower() for name in names}
        if "manifest.json" not in lowered:
            raise ValueError("Legacy release is missing manifest.json: " + tag)
        if lowered.intersection(MODERN_ONLY_ASSETS):
            raise ValueError("Legacy release contains modern-only assets: " + tag)
        if any(name.endswith(".bin") for name in lowered):
            raise ValueError("Legacy release contains a firmware image: " + tag)

    selected_legacy = _stable(legacy_releases)
    if selected_legacy is None:
        raise ValueError("Legacy feed has no stable release")

    if expect_modern_empty and modern_releases:
        raise ValueError("Promotion-gated modern feed is not empty")
    for release in modern_releases:
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag.startswith("modern-v"):
            raise ValueError("Modern release has an invalid tag")
        names = _assets(release)
        lowered = {name.lower() for name in names}
        if "modern-manifest.json" not in lowered:
            raise ValueError("Modern release is missing modern-manifest.json: " + tag)
        if "manifest.json" in lowered:
            raise ValueError("Modern release contains the legacy manifest: " + tag)
        if not any(name.endswith(".bin") for name in lowered):
            raise ValueError("Modern release is missing its firmware image: " + tag)

    selected_modern = _stable(modern_releases)
    return {
        "schema": 1,
        "mode": "prepromotion" if expect_modern_empty else "published",
        "legacy": {
            "repository": LEGACY_REPOSITORY,
            "manifest": "manifest.json",
            "release_count": len(legacy_releases),
            "selected_stable_tag": selected_legacy["tag_name"],
        },
        "modern": {
            "repository": MODERN_REPOSITORY,
            "manifest": "modern-manifest.json",
            "release_count": len(modern_releases),
            "selected_stable_tag": (
                selected_modern.get("tag_name") if selected_modern else None),
        },
        "cross_profile_assets": False,
        "mutation_performed": False,
    }


def fetch_releases(repository: str):
    releases = []
    for page in range(1, 21):
        request = Request(
            "https://api.github.com/repos/%s/releases?per_page=100&page=%d" %
            (repository, page),
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "TartLab-feed-isolation",
            })
        with urlopen(request, timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("GitHub release response is invalid for " + repository)
        releases.extend(batch)
        if len(batch) < 100:
            return releases
    raise ValueError("GitHub release feed exceeds the audit pagination limit")


def check(*, root: Path = ROOT, legacy_releases=None, modern_releases=None):
    expect_modern_empty = validate_policy(root)
    if legacy_releases is None:
        legacy_releases = fetch_releases(LEGACY_REPOSITORY)
    if modern_releases is None:
        modern_releases = fetch_releases(MODERN_REPOSITORY)
    return validate_feeds(
        legacy_releases, modern_releases,
        expect_modern_empty=expect_modern_empty)


def parser():
    result = argparse.ArgumentParser()
    result.add_argument("--legacy-response", type=Path)
    result.add_argument("--modern-response", type=Path)
    return result


def main():
    args = parser().parse_args()
    if bool(args.legacy_response) != bool(args.modern_response):
        raise ValueError("Both response files must be supplied together")
    legacy = load_json(args.legacy_response) if args.legacy_response else None
    modern = load_json(args.modern_response) if args.modern_response else None
    print(json.dumps(check(
        legacy_releases=legacy, modern_releases=modern), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
