"""Experimental platform selector for the Elecrow DLE06235B."""

from tartlabutils.elecrow_dle06235b import (
    create_elecrow_dle06235b_platform,
)


IDE_BUTTON_PIN = None


def create_platform():
    return create_elecrow_dle06235b_platform()
