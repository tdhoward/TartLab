"""Explicit selection for the experimental PyDevices modern comparison."""

from tartlabutils.pydevices_modern import create_t_display_s3_pro_platform


IDE_BUTTON_PIN = 12


def create_platform():
    return create_t_display_s3_pro_platform()
