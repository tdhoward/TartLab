# Board catalog

Each child directory contains one `board.json` descriptor. Directories are
discovered automatically; there is no central board list to edit.

Production runtime shims live beside the descriptor in `runtime/`. They are
staged only when a distribution explicitly selects that board and are packaged
under the matching `board-support.tar` subtree; they do not belong in
`src/lib/tartlabutils`.

Use `python tools/check_board_catalog.py` after changing a descriptor. See
[`BOARD_SUPPORT.md`](../BOARD_SUPPORT.md) for the schema semantics, lifecycle,
source layout, and new-board workflow.

Descriptors contain public model-level facts only. Do not store unit serial
numbers, USB port assignments, credentials, raw logs, private backups, or
factory dumps here.

## Current catalog

| Board | Lifecycle | Documentation |
| --- | --- | --- |
| LilyGO T-Display-S3 Pro | `qualified` | [`lilygo_t_display_s3_pro`](lilygo_t_display_s3_pro) |
| Elecrow DLE06235B | `bringup` | [`elecrow_dle06235b`](elecrow_dle06235b) |

Vendor-level research covering more than one board lives in a vendor directory,
such as [`elecrow`](elecrow). Board-specific results and qualification records
stay with the corresponding descriptor.
