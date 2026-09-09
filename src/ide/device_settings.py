"""Touchscreen settings pages owned by the IDE application."""


TIMEOUTS = (0, 30, 60, 180, 300, 600, 1800, 3600)


class DeviceSettings:
    def __init__(self, lvgl, width, height, get_display, save_display,
                 get_networks, forget_network, get_versions, check_updates,
                 install_updates, log_error):
        self._lv = lvgl
        self._width = width
        self._height = height
        self._get_display = get_display
        self._save_display = save_display
        self._get_networks = get_networks
        self._forget_network = forget_network
        self._get_versions = get_versions
        self._check_updates = check_updates
        self._install_updates = install_updates
        self._log_error = log_error
        self._home = lvgl.screen_active()
        self._screen = None
        self._pending = None
        self._busy = False
        self._page = None
        self._status = None
        self._updates = []
        self._buttons = []
        self._callbacks = []
        self._entry = lvgl.button(self._home)
        self._entry.set_size(36, 32)
        self._entry.set_pos(8, 8)
        label = lvgl.label(self._entry)
        label.set_text(getattr(getattr(lvgl, 'SYMBOL', None), 'SETTINGS', '...'))
        label.center()
        self._entry_callback = lambda event: self._queue('settings')
        self._entry.add_event_cb(self._entry_callback, lvgl.EVENT.CLICKED, None)

    def _queue(self, action, value=None):
        # LVGL callbacks only queue work. Filesystem and network operations run
        # in the IDE asyncio task, outside native input/event dispatch.
        if not self._busy and self._pending is None:
            self._pending = (action, value)

    def _button(self, parent, text, x, y, width, action, value=None):
        button = self._lv.button(parent)
        button.set_size(width, 40)
        button.set_pos(x, y)
        button.set_style_bg_color(self._lv.color_hex(0x245A85), 0)
        label = self._lv.label(button)
        label.set_text(text)
        label.set_size(max(1, width - 12), 20)
        label.set_style_text_align(self._lv.TEXT_ALIGN.CENTER, 0)
        label.center()
        callback = lambda event: self._queue(action, value)
        button.add_event_cb(callback, self._lv.EVENT.CLICKED, None)
        self._callbacks.append(callback)
        self._buttons.append(button)
        return button

    def _label(self, text, y, width=None):
        label = self._lv.label(self._body)
        label.set_text(text)
        label.set_width(width or self._content_width)
        label.set_pos(0, y)
        return label

    def _new_page(self, title, page, back='settings'):
        old = self._screen
        self._screen = self._lv.obj()
        self._page = page
        self._buttons = []
        self._screen.set_style_bg_color(self._lv.color_hex(0x101820), 0)
        self._screen.set_style_text_color(self._lv.color_hex(0xFFFFFF), 0)
        self._screen.set_style_pad_all(0, 0)
        self._screen.set_style_border_width(0, 0)
        self._screen.set_scroll_dir(self._lv.DIR.NONE)
        # All navigation is dispatched by run(), so old widgets can be deleted
        # synchronously without freeing a currently executing LVGL callback.
        self._lv.screen_load(self._screen)
        if old is not None:
            old.delete()
        self._callbacks = []
        self._button(self._screen, 'Back', 8, 6, 64, back)
        heading = self._lv.label(self._screen)
        heading.set_text(title)
        heading.set_pos(84, 16)
        self._body = self._lv.obj(self._screen)
        self._body.set_pos(8, 54)
        self._body.set_size(self._width - 16, self._height - 62)
        self._body.set_style_bg_color(self._lv.color_hex(0x101820), 0)
        self._body.set_style_border_width(0, 0)
        self._body.set_style_pad_all(0, 0)
        self._body.set_scroll_dir(self._lv.DIR.VER)
        self._content_width = self._width - 28
        self._status = None

    def _timeout_text(self):
        if self._timeout == 0:
            return 'Never dim'
        if self._timeout < 60:
            return 'Dim after %g sec' % self._timeout
        return 'Dim after %g min' % (self._timeout / 60)

    def _settings_page(self, message=''):
        self._new_page('Settings', 'settings', 'home')
        # Keep the editable draft on this page until Save or Back is chosen.
        control_x = self._content_width - 92
        self._brightness_label = self._label(
            'Brightness: %d%%' % round(self._brightness * 100), 10, control_x - 4)
        self._button(self._body, '-', control_x, 0, 40, 'brightness', -1)
        self._button(self._body, '+', control_x + 48, 0, 40, 'brightness', 1)
        self._timeout_label = self._label(self._timeout_text(), 54, control_x - 4)
        self._button(self._body, '-', control_x, 44, 40, 'timeout', -1)
        self._button(self._body, '+', control_x + 48, 44, 40, 'timeout', 1)
        width = (self._content_width - 12) // 3
        for index, (text, action) in enumerate((
                ('Save', 'save'), ('WiFi', 'wifi'), ('Updates', 'updates'))):
            self._button(self._body, text, index * (width + 6), 88, width, action)
        self._status = self._label(message, 134)

    def _wifi_page(self, message=''):
        self._new_page('Saved WiFi', 'wifi')
        self._status = self._label(message or 'Select a network to forget.', 0)
        networks = self._get_networks()
        if not networks:
            self._status.set_text(message or 'No saved WiFi networks.')
        for index, ssid in enumerate(networks):
            self._button(self._body, ssid, 0, 54 + index * 48,
                         self._content_width, 'select_network', ssid)

    def _network_page(self, ssid):
        self._selected_ssid = ssid
        self._new_page('Forget network', 'network', 'wifi')
        name = self._label(ssid, 0)
        name.set_size(self._content_width, 48)
        self._label('Current connection stays active\nuntil restart.', 54)
        self._button(self._body, 'Forget this network', 0, 110,
                     self._content_width, 'forget', ssid)
        self._status = self._label('', 158)

    def _updates_page(self, message='Tap Check now to look for updates.'):
        self._new_page('Updates', 'updates')
        self._status = self._label(message, 0)
        y = 56
        for name, version in self._get_versions():
            latest = next((item[2] for item in self._updates if item[0] == name), None)
            text = '%s: %s' % (name, version)
            if latest:
                text += '\nAvailable: ' + latest
            label = self._label(text, y)
            label.set_size(self._content_width, 48)
            y += 56
        available = any(item[2] for item in self._updates)
        width = (self._content_width - 8) // 2 if available else self._content_width
        self._button(self._body, 'Check now', 0, y, width, 'check')
        if available:
            self._button(self._body, 'Install update', width + 8, y,
                         width, 'confirm_update')

    def _confirm_update_page(self):
        self._new_page('Install update', 'confirm_update', 'updates')
        self._label('Keep the device plugged in.\nIt will restart after updating.', 0)
        self._button(self._body, 'Update and restart', 0, 78,
                     self._content_width, 'install')
        self._status = self._label('', 128)

    def _set_busy(self, busy):
        self._busy = busy
        for button in self._buttons:
            if busy:
                button.add_state(self._lv.STATE.DISABLED)
            else:
                button.remove_state(self._lv.STATE.DISABLED)

    def show_update_progress(self, status, step, steps):
        # Keep browser-started updates visible on the existing IDE status view.
        if self._page == 'installing' and self._status is not None:
            self._status.set_text('%s\nStep %s of %s' % (status, step, max(step, steps)))

    def _return_home(self):
        self._lv.screen_load(self._home)
        if self._screen is not None:
            self._screen.delete()
        self._screen = None
        self._page = None
        self._status = None
        self._buttons = []
        self._callbacks = []

    async def dispatch(self, action, value, asyncio_module):
        """Handle one queued action in ordinary task context."""
        try:
            if action == 'home':
                self._return_home()
            elif action == 'settings':
                display = self._get_display()
                self._brightness = max(0.1, display['max_brightness'])
                self._timeout = display['auto_dim_seconds']
                self._settings_page()
            elif action == 'brightness':
                self._brightness = min(1, max(0.1, round(self._brightness + value * 0.1, 2)))
                self._brightness_label.set_text('Brightness: %d%%' % round(self._brightness * 100))
                self._status.set_text('Tap Save to apply.')
            elif action == 'timeout':
                choices = [delay for delay in TIMEOUTS
                           if (delay > self._timeout if value > 0 else delay < self._timeout)]
                if choices:
                    self._timeout = choices[0] if value > 0 else choices[-1]
                self._timeout_label.set_text(self._timeout_text())
                self._status.set_text('Tap Save to apply.')
            elif action == 'save':
                self._save_display(self._brightness, self._timeout)
                self._status.set_text('Saved and applied.')
            elif action == 'wifi':
                self._wifi_page()
            elif action == 'select_network':
                self._network_page(value)
            elif action == 'forget':
                self._forget_network(value)
                self._wifi_page('Network forgotten.')
            elif action == 'updates':
                self._updates_page()
            elif action == 'confirm_update':
                self._confirm_update_page()
            elif action == 'check':
                self._updates = []
                self._updates_page('Checking for updates...')
                self._set_busy(True)
                await asyncio_module.sleep(0.1)
                self._updates = await self._check_updates()
                available = any(item[2] for item in self._updates)
                self._updates_page('Updates available.' if available else 'You are up to date.')
            elif action == 'install':
                self._updates = []
                self._new_page('Updating', 'installing', 'updates')
                self._status = self._label('Starting update...\nKeep the device plugged in.', 0)
                self._set_busy(True)
                await asyncio_module.sleep(0.1)
                await self._install_updates()
                self._updates = []
                self._updates_page('Updater finished. Check again for current versions.')
        except Exception as error:
            self._log_error(error)
            if action in ('check', 'install'):
                self._updates = []
                self._updates_page(str(error))
            elif self._status is not None:
                self._status.set_text('Could not save. Please try again.')
        finally:
            self._set_busy(False)

    async def run(self, asyncio_module):
        while True:
            if self._pending is not None:
                action, value = self._pending
                self._pending = None
                await self.dispatch(action, value, asyncio_module)
            await asyncio_module.sleep_ms(50)

    def close(self):
        self._pending = None
        self._return_home()
        self._entry.delete()
