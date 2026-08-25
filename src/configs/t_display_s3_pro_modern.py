"""Explicit platform selection for the experimental modern firmware.

Adult provisioning can select this configuration from ``/hdwconfig.py`` with
``from t_display_s3_pro_modern import *``.  It is intentionally separate from
the qualified legacy T-Display-S3 Pro configuration.
"""

from tartlabutils.modern import create_t_display_s3_pro_platform


IDE_BUTTON_PIN = 12


def create_platform():
    return create_t_display_s3_pro_platform()
