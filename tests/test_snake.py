"""Regression checks for the legacy Snake feel on the modern runtime."""
import json
from pathlib import Path
import runpy
import tempfile
import types
import unittest
from unittest.mock import patch

from tests.test_app import FakeFrameBuffer, FakeSurface, load_app

ROOT = Path(__file__).resolve().parents[1]
SNAKE = runpy.run_path(str(ROOT / 'src/files/help/snake.py'),
                      init_globals={'_SNAKE_AUTOSTART': False})
Game = SNAKE['SnakeGame']


class SnakeTests(unittest.TestCase):
    def test_initial_state_and_three_distinct_apples(self):
        game = Game()
        self.assertEqual(game.snake, [(7, 12)])
        self.assertEqual(game.snake_length, 3)
        self.assertEqual(game.move_delay, 250)
        self.assertEqual(len(set(game.apples)), 3)
        self.assertNotIn(game.snake[0], game.apples)
        game.apples = [(0, 0), (0, 1), (0, 2)]
        for unused in range(4):
            self.assertTrue(game.step())
        self.assertEqual(game.snake, [(9, 12), (10, 12), (11, 12)])

    def test_growth_bonus_and_speed_every_five_apples(self):
        game = Game()
        for count in range(1, 11):
            # Feed the next cell, isolating progression from random placement.
            game.snake = [(3, 3), (4, 3), (5, 3)]
            game.apples = [(6, 3), (0, 0), (0, 1)]
            self.assertTrue(game.step())
            self.assertEqual(game.snake_length, 3 + count)
            self.assertEqual(len(game.apples), 3)
            self.assertFalse(set(game.apples).intersection(game.snake))
            if count == 5:
                self.assertEqual((game.score, game.apple_bonus, game.move_delay),
                                 (5, 3, 200))
        self.assertEqual((game.score, game.apple_bonus, game.move_delay), (20, 5, 160))

    def test_wrap_reverse_and_self_collision(self):
        game = Game()
        game.snake = [(13, 12)]
        game.apples = [(0, 0)]
        game.turn('left')
        self.assertEqual(game.direction, (1, 0))
        self.assertTrue(game.step())
        self.assertEqual(game.snake[-1], (0, 12))
        game.snake = [(0, 0), (1, 0), (1, 1), (0, 1)]
        game.turn('up')
        self.assertFalse(game.step())

    def test_full_board_apple_placement_terminates(self):
        game = Game()
        game.snake = [(x, y) for y in range(25) for x in range(14)]
        game.apples = []
        game.place_apple()
        self.assertEqual(game.apples, [])

    def test_legacy_sprite_colors_geometry_and_portrait_rotation(self):
        app = load_app(types.SimpleNamespace())
        imports = {'tartlabutils.app': app,
                   'framebuf': types.SimpleNamespace(FrameBuffer=FakeFrameBuffer, RGB565=1)}
        with patch.dict('sys.modules', imports):
            for width, height in ((222, 480), (480, 222), (320, 480)):
                canvas = app.PortraitCanvas(FakeSurface(width, height))
                view = SNAKE['SnakeView'](canvas)
                if canvas.width == 222:
                    self.assertEqual((view.block, view.x, view.y), (15, 6, 52))
                self.assertGreaterEqual(view.text_height, 36)
                game = Game()
                view.begin(game)
                view.cell((4, 4), 'head')
                view.cell((5, 4), 'body')
                view.cell((6, 4), 'apple')
                x, y = view.x + 4 * view.block, view.y + 4 * view.block
                self.assertEqual(canvas.pixel(x, y), app.framebuffer_color(0x07E0))
                self.assertEqual(canvas.pixel(x + view.block // 4, y + view.block // 4), 0)
                self.assertEqual(canvas.pixel(x + view.block, y), app.framebuffer_color(0x0600))
                self.assertEqual(canvas.pixel(x + 2 * view.block, y), 0)
                half = view.block // 2
                self.assertEqual(canvas.pixel(x + 2 * view.block + half, y + half + 2),
                                 app.framebuffer_color(0xF800))
                canvas.close()

    def test_pause_requires_two_start_taps_to_quit(self):
        events = iter(['up', 'start', 'pause', 'start', 'start'])
        touch = types.SimpleNamespace(read=lambda: next(events))
        messages = []
        view = types.SimpleNamespace(controls=lambda: None, begin=lambda game: None,
                                     show_text=messages.append)
        timing = types.ModuleType('time')
        timing.sleep_ms = lambda ms: None
        timing.ticks_ms = lambda: 0
        timing.ticks_diff = lambda a, b: a - b
        with patch.dict('sys.modules', {'time': timing, 'ujson': json}):
            self.assertFalse(SNAKE['play'](view, touch))
        self.assertEqual(messages, ['Paused.\nPress start 2x to quit,\nAny key to resume.'])

    def test_high_score_file_is_legacy_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = str(Path(directory) / 'snake_high_score.json')
            with patch.dict('sys.modules', {'ujson': json}), patch.dict(
                    SNAKE['load_high_score'].__globals__, {'HIGH_SCORE_FILE': filename}):
                self.assertEqual(SNAKE['load_high_score'](), 0)
                SNAKE['save_high_score'](23)
                self.assertEqual(json.loads(Path(filename).read_text()), {'high_score': 23})
                self.assertEqual(SNAKE['load_high_score'](), 23)

    def test_pause_resume_and_game_over_wait_for_start(self):
        events = iter(['start', 'pause', 'start', 'up', 'down', 'start'])
        touch = types.SimpleNamespace(read=lambda: next(events))
        messages, restored, saved = [], [], []
        view = types.SimpleNamespace(
            controls=lambda: None, begin=lambda game: None,
            restore=restored.append, green=7, white=15,
            show_text=lambda *args: messages.append(args))
        game = Game()
        game.score = 9
        game.step = lambda: False
        timing = types.ModuleType('time')
        timing.sleep_ms = lambda ms: None
        ticks = iter([0, 300, 300])
        timing.ticks_ms = lambda: next(ticks)
        timing.ticks_diff = lambda a, b: a - b
        with patch.dict('sys.modules', {'time': timing}), patch.dict(
                SNAKE['play'].__globals__, {
                    'SnakeGame': lambda: game, 'load_high_score': lambda: 5,
                    'save_high_score': saved.append}):
            self.assertTrue(SNAKE['play'](view, touch))
        self.assertEqual(restored, [game])
        self.assertEqual(saved, [9])
        self.assertEqual(messages[-1],
                         ('New High Score!\nScore: 9\nHigh Score: 9', 7))


if __name__ == '__main__':
    unittest.main()
