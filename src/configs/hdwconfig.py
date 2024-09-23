# This file is not able to be upgraded, since it is meant to target specific hardware.
# This should be set up once for a particular piece of hardware, and never changed again.

# Import the appropriate PyDevices board_config for your device
from board_configs.t_display_s3_pro.board_config import *

# Set the button for starting up in IDE mode
IDE_BUTTON_PIN = 12

# Other board-related settings here
