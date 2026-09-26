# Project index

[Documentation index](../README.md)

Status reviewed 2026-09-22 against the project plans and recorded results.
Implementation, bench checks, and release qualification are distinct milestones;
the linked records define the evidence for each summary.

## Active work

| Project | Current state | Next unfinished gate |
| --- | --- | --- |
| [Scrolling Racer](active/scrolling-racer.md) | Phases 1–4 implemented, followed by sprite gameplay, animals, difficulty and high scores. Phase 5 remains open. | Final workload/cadence selection, performance cleanup, full timing matrix and visual qualification. |
| [Button navigation](active/button-navigation.md) | Experimental non-touch integration; navigation, settings, browser access and dim/wake demonstrated. | Counter/restart observations and full board/reset/provisioning/recovery qualification, including affected touch-board regressions. |
| [Grid Puzzle](active/grid-puzzle.md) | Engine, art, dirty rendering and debug inspection implemented. Phase 5 performance gate failed. | Fix dense/debug workloads, remeasure revised spider rules and finish operator observations before the teaching campaign and packaging. |
| [CrowPanel 7-inch](../../boards/elecrow_dis08070h/BRINGUP_PLAN.md) | Experimental SD-root/RGB runtime; display, touch, settings and brightness have bench evidence. | Diagnose intermittent GT911 transport faults and post-interrupt scheduler stalls; complete current-image cold-boot and recovery qualification. See [investigation](../../boards/elecrow_dis08070h/GT911_INVESTIGATION.md). |
| [Nearby Chat](../../tests/MESSAGING_HARDWARE.md) | Example and repeatable two-device tooling implemented; its guide has no completed physical acceptance record. | Record two-device results and actual typing, readability and reset/relaunch observations. |

## Deferred follow-up

[CST226 upstream contribution](active/cst226-upstream.md) is planning guidance,
not an outstanding dependency of TartLab's tested local workaround. No upstream
change or merge is established by that document.

## Completed projects and milestones

| Project | Outcome and evidence |
| --- | --- |
| [Modern display class](completed/modern-display-class.md) | Compiled drawing/packing optimizations, unified four-rotation canvas and matching input transforms; [performance evidence](../../tests/DRAWING_PERFORMANCE.md). |
| [Panel-scroll presentation](completed/panel-scroll-presentation.md) | Portable scroll API and ST7796 rotation-270 hardware/visual qualification; [hardware record](../../tests/PANEL_SCROLL_HARDWARE.md). |
| [Image and sprite pipeline](completed/image-sprite-pipeline.md) | TS16/QOI decoding, reusable sprite preparation and modern driver packaging implemented; device assertions and visual smoke recorded. The [API reference](../reference/image-assets.md) remains current. |
| [Touchscreen startup and IDE power](completed/touchscreen-startup.md) | Launcher, chooser, settings and dim/wake shipped in the qualified modern release. Original design and engineering history are retained separately from current qualification. |
| [Elecrow DLE06235B support](../../boards/elecrow_dle06235b/BRINGUP_RESULTS.md) | Qualified and first published in `modern-v0.15.4`; included with LilyGO T-Display-S3 Pro in the fresh `modern-v0.16.0` qualification. |
| [Modern release baseline](../../tests/PHASE6_MODERN_QUALIFICATION.md#modern-v0160-promotion) | `modern-v0.16.0` published on 2026-09-10 with schema-3 evidence for both qualified boards; signed baseline captured and pinned. Routine entry point: [release qualification](../../RELEASE_QUALIFICATION.md). |
| [Legacy release modernization](../../PROJECT_NOTES.md#release-milestones-and-open-decisions) | Legacy `v0.15` published and qualified. Phases 1–4 and their release evidence remain under [tests](../../tests/TEST_TIERS.md#tier-4-physical-release-qualification). |

Completed records preserve the scope and dates of their tests. Later runtime,
firmware, board or app changes require the applicable new evidence; moving a
document here does not qualify those changes.
