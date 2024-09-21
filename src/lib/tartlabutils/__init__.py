# Copyright 2021 (c) Erik de Lange
# Released under MIT license

from .miscutils import file_exists, unquote, rmvdir, mkdirs, split_on_first, \
  init_logs, log, get_logs, load_settings, save_settings, default_settings
from .updater import check_for_update, main_update_routine
