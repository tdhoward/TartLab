# Image and sprite pipeline

[Project index](../README.md) · [Current API reference](../../reference/image-assets.md)

Status: implementation complete; Elecrow device and visual smoke recorded on
2026-09-08. This record summarizes the completed work; ongoing API usage and
conversion instructions are maintained in the reference above.

## Outcome

- Modern image APIs detect and decode TS16 and QOI without PyDevices.
- Sprite preparation supports one-pass batch extraction, compact transparency,
  scaling, flipping, clipping, and additional compatible decoders.
- Modern display adapters are packaged under `tartlabdrivers`, with declarative
  board selection and separate legacy payloads.
- Image and sprite examples demonstrate the APIs. Racer and Grid Puzzle own
  their art coordinates, visual policy, and gameplay.

## Recorded verification

The [physical smoke record](../../../tests/IMAGE_DRIVER_HARDWARE.md) reports
101 on-device assertions, matching TS16/QOI output, alpha cutoff and background
compositing, animated partial updates, ownership cycles, and repeated extraction
and initialization checks. The guided repeat confirmed the visual results and
all five touch targets on the Elecrow DLE06235B.

That was a bounded working-tree smoke, not a firmware flash, release promotion,
long-duration stability result, or qualification of every display adapter.
The record retains its original inventory, source identities and limitations.

For later changes, use the image/asset and driver-package checks in
[test tiers](../../../tests/TEST_TIERS.md), and the normal
[release qualification workflow](../../../RELEASE_QUALIFICATION.md).
