"""Physical-input contracts; native LVGL and usability need device evidence."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'src/lib/tartlabutils' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Pin:
    IN, PULL_UP, PULL_DOWN = 0, 1, 2
    levels = {}

    def __init__(self, number, mode, pull):
        self.number = number

    def value(self):
        return self.levels.get(self.number, 1)


class Group:
    def __init__(self):
        self.widgets = []
        self.deleted = False

    def set_wrap(self, wrap):
        self.wrap = wrap

    def add_obj(self, widget):
        self.widgets.append(widget)

    def remove_all_objs(self):
        self.widgets = []

    def delete(self):
        self.deleted = True


class Indev:
    def set_type(self, value):
        self.type = value

    def set_read_cb(self, value):
        self.read = value

    def reset(self, obj):
        pass

    def set_group(self, value):
        self.group = value

    def enable(self, value):
        self.enabled = value

    def delete(self):
        self.deleted = True


class LV:
    KEY = SimpleNamespace(NEXT=9, ENTER=10)
    INDEV_STATE = SimpleNamespace(RELEASED=0, PRESSED=1)
    INDEV_TYPE = SimpleNamespace(KEYPAD=2)

    def indev_create(self):
        self.indev = Indev()
        return self.indev

    def group_create(self):
        return Group()


class ButtonTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        Pin.levels = {}
        self.definitions = ({'name': 'first', 'number': 101, 'active_high': False},
                            {'name': 'second', 'number': 102, 'active_high': False})
        self.buttons = load('buttons').ButtonInput(self.definitions, Pin, ticks_ms=lambda: self.now)
        self.now = 31
        self.buttons.poll()

    def poll(self, elapsed=31):
        self.now += elapsed
        return self.buttons.poll()

    def edge(self, number, value):
        Pin.levels[number] = value
        self.buttons.poll()
        return self.poll()

    def test_debounce_bounce_release_and_no_repeat(self):
        Pin.levels[101] = 0
        self.assertEqual(self.poll(1), ())
        Pin.levels[101] = 1
        self.assertEqual(self.poll(5), ())
        self.assertEqual(self.poll(), ())
        self.assertEqual(self.edge(101, 0), (('first', True),))
        self.assertEqual(self.poll(5000), ())
        self.assertEqual(self.edge(101, 1), (('first', False),))

    def test_held_button_is_suppressed_across_reset(self):
        self.edge(101, 0)
        self.buttons.reset()
        self.assertEqual(self.poll(500), ())
        self.assertEqual(self.edge(101, 1), ())
        self.assertEqual(self.edge(101, 0), (('first', True),))

    def test_active_high_and_simultaneous_independent_edges(self):
        Pin.levels[102] = 0
        definitions = [dict(item) for item in self.definitions]
        definitions[1]['active_high'] = True
        buttons = load('buttons').ButtonInput(definitions, Pin, ticks_ms=lambda: self.now)
        self.now += 31
        buttons.poll()
        Pin.levels.update({101: 0, 102: 1})
        buttons.poll()
        self.now += 31
        self.assertEqual(buttons.poll(), (('first', True), ('second', True)))

    def test_named_pins_preserve_unique_lookup_and_absent_touch(self):
        board = load('board')
        config = {'id': 'test', 'pins': [dict(p, type='BUTTON') for p in self.definitions],
                  'display': {'driver': 'test.Panel'}, 'touch': None,
                  'navigation': {'next': 'first', 'activate': 'second'}}
        board.validate_board_config(config)
        with self.assertRaisesRegex(ValueError, 'more than once'):
            board.pin_definition(config, 'BUTTON')
        self.assertEqual(board.pin_definition(config, 'BUTTON', name='second')['number'], 102)
        config['pins'][1]['name'] = 'first'
        with self.assertRaises(ValueError):
            board.validate_board_config(config)


class NavigationTests(ButtonTests):
    def setUp(self):
        super().setUp()
        self.lv = LV()
        self.nav = load('navigation').ButtonNavigation(
            self.lv, self.buttons, {'next': 'first', 'activate': 'second'})
        self.page = self.nav.page()
        self.addCleanup(self.nav.close)
        self.sample(31)

    def sample(self, elapsed=31):
        self.now += elapsed
        data = SimpleNamespace()
        self.nav._read(None, data)
        return data.state, data.key

    def key_edge(self, number, value):
        Pin.levels[number] = value
        self.sample(1)
        return self.sample()

    def test_action_waits_for_release_and_sends_one_complete_key(self):
        self.assertEqual(self.key_edge(102, 0)[0], 0)
        self.assertEqual(self.sample(5000)[0], 0)
        self.assertEqual(self.key_edge(102, 1), (1, self.lv.KEY.ENTER))
        self.assertEqual(self.sample(), (0, self.lv.KEY.ENTER))
        self.assertEqual(self.sample()[0], 0)

    def test_page_replacement_drops_held_and_queued_input(self):
        self.key_edge(102, 0)
        group = self.page._group
        self.page.close()
        self.page = self.nav.page()
        self.assertTrue(group.deleted)
        self.assertEqual(self.key_edge(102, 1)[0], 0)
        self.key_edge(102, 0)
        self.assertEqual(self.key_edge(102, 1)[0], 1)

    def test_game_ownership_suppresses_navigation_and_stale_release(self):
        self.key_edge(102, 0)
        self.nav.enable(False)
        self.assertEqual(self.sample()[0], 0)
        self.nav.enable(True)
        self.assertEqual(self.key_edge(102, 1)[0], 0)

    def test_wake_consumes_entire_gesture_and_listener_is_removed(self):
        calls = []
        def wake():
            calls.append('wake')
            return True
        self.nav.add_activity_listener(wake)
        self.key_edge(102, 0)
        self.assertEqual(calls, ['wake'])
        self.assertEqual(self.key_edge(102, 1)[0], 0)
        self.nav.remove_activity_listener(wake)
        self.key_edge(102, 0)
        self.assertEqual(self.key_edge(102, 1)[0], 1)


if __name__ == '__main__':
    unittest.main()
