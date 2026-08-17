# SPDX-License-Identifier: GPL-3.0-or-later
"""Legacy ``graphics`` imports backed by the pinned ``pygraphics`` package.

Only the eager drawing surface used by TartLab and its shipped examples is
exported here.  Current upstream package names stay behind this adapter.
"""

from pygraphics import (
    Area,
    FrameBuffer,
    GS2_HMSB,
    GS4_HMSB,
    GS8,
    MONO_HLSB,
    MONO_HMSB,
    MONO_VLSB,
    RGB565,
    RGB888,
    arc,
    blit,
    blit_rect,
    blit_transparent,
    circle,
    ellipse,
    fill,
    fill_rect,
    gradient_rect,
    hline,
    line,
    pixel,
    poly,
    polygon,
    rect,
    round_rect,
    text,
    text8,
    text14,
    text16,
    triangle,
    vline,
)

__all__ = (
    "Area", "FrameBuffer", "GS2_HMSB", "GS4_HMSB", "GS8",
    "MONO_HLSB", "MONO_HMSB", "MONO_VLSB", "RGB565", "RGB888",
    "arc", "blit", "blit_rect", "blit_transparent", "circle",
    "ellipse", "fill", "fill_rect", "gradient_rect", "hline", "line",
    "pixel", "poly", "polygon", "rect", "round_rect", "text", "text8",
    "text14", "text16", "triangle", "vline",
)
