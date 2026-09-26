# TartLab documentation

Start with the [project index](projects/README.md) for current work, next gates,
and completed project history.

| Need | Entry point |
| --- | --- |
| Use or install TartLab | [Repository README](../README.md) |
| Find a project or its status | [Active and completed projects](projects/README.md) |
| Understand shared architecture and constraints | [Contributor context](../PROJECT_NOTES.md) |
| Build or test a change | [Development guide](../DEVELOPMENT.md), [test tiers](../tests/TEST_TIERS.md) |
| Find board support and bring-up results | [Board catalog](../boards/README.md), [board architecture](../BOARD_SUPPORT.md) |
| Load, convert, or prepare images and sprites | [Image and sprite reference](reference/image-assets.md) |
| Qualify a release | [Operator quick start](../RELEASE_QUALIFICATION.md) |
| Understand release scope and evidence reuse | [Release policy](../RELEASE_POLICY.md), [release tooling](../RELEASE_TOOLING.md) |
| Check published modern release evidence | [Modern qualification record](../tests/PHASE6_MODERN_QUALIFICATION.md) |

Project plans live in `projects/active`; completed project narratives live in
`projects/completed`. Current API and usage guides live in `reference`.
Board-specific plans remain beside their board descriptors, test procedures and
evidence remain under `tests`, and asset rebuild/provenance notes remain beside
their sources under `tools/assets`.

When a project finishes, record its outcome and evidence, move its plan to
`projects/completed`, and update the project index and incoming links. Preserve
historical results and their qualification scope. Commands in these documents
run from the repository root unless stated otherwise.
