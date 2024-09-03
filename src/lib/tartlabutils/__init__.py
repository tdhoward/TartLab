# Copyright 2021 (c) Erik de Lange
# Released under MIT license

from .miscutils import file_exists, unquote, rmvdir, split_on_first
from .updater import check_for_update, main_update_routine
from .logs import init_logs, log, get_logs
