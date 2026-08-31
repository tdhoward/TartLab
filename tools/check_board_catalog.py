"""Validate all TartLab modern board descriptors."""

from __future__ import annotations

from board_catalog import load_catalog


def main() -> int:
    catalog = load_catalog()
    counts: dict[str, int] = {}
    for descriptor in catalog.values():
        status = descriptor["support_status"]
        counts[status] = counts.get(status, 0) + 1
    summary = ", ".join(
        "%s=%d" % (status, counts[status]) for status in sorted(counts))
    print("Board catalog valid: %d board(s); %s" % (len(catalog), summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
