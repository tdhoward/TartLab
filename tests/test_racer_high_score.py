import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_racer_sprites import RACER, PixelCanvas, load_art


class RacerHighScoreTests(unittest.TestCase):
    def test_record_survives_reload_and_only_higher_scores_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "racer.json")
            best = RACER.HighScore(path)
            self.assertEqual(best.value, 0)
            self.assertFalse(best.record(0))
            self.assertFalse(Path(path).exists())
            self.assertTrue(best.record(7))
            self.assertEqual(RACER.HighScore(path).value, 7)
            with patch("builtins.open", side_effect=AssertionError("unneeded write")):
                self.assertFalse(best.record(5))
                self.assertFalse(best.record(7))
            self.assertTrue(best.record(9))
            self.assertEqual(RACER.HighScore(path).value, 9)
            self.assertFalse(Path(path + ".new").exists())

    def test_invalid_saved_data_starts_at_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "racer.json"
            for value in ("broken", "[]", "null", '{}', '{"high_score": -1}',
                          '{"high_score": true}', '{"high_score": "9"}',
                          '{"high_score": 2.5}'):
                path.write_text(value)
                self.assertEqual(RACER.HighScore(str(path)).value, 0)

    def test_interrupted_save_preserves_last_record_and_game_can_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "racer.json"
            path.write_text(json.dumps({"high_score": 4}))
            best = RACER.HighScore(str(path))
            with patch("os.replace", side_effect=OSError("disk failure")), patch("builtins.print"):
                self.assertTrue(best.record(8))
            self.assertEqual(best.value, 8)
            self.assertEqual(RACER.HighScore(str(path)).value, 4)

    def test_crash_hud_compares_scores_and_shows_new_record(self):
        with tempfile.TemporaryDirectory() as directory:
            best = RACER.HighScore(str(Path(directory) / "racer.json"))
            best.record(12)
            art = load_art()
            canvas = PixelCanvas(240, 320)
            game = RACER.create_race(240, 320)
            hud = RACER.RacerHUD(canvas, game, art, best)
            game.score = 7
            game.crashed = True
            with patch.object(art, "text", wraps=art.text) as text:
                hud.draw()
                self.assertEqual([call.args[1] for call in text.call_args_list],
                                 ["SCORE 0007", "HI 0012", "CRASHED - TAP"])
                for call in text.call_args_list:
                    unused, value, x, unused_y, unused_clip = call.args
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x + len(value) * 12, canvas.width)
                text.reset_mock()
                game.score = 15
                hud.new_record = best.record(game.score)
                hud.draw()
                self.assertEqual([call.args[1] for call in text.call_args_list],
                                 ["SCORE 0015", "HI 0015", "NEW HIGH - TAP"])
            self.assertTrue(all(not any(row) for row in canvas.pixels[48:]))
            hud.game = RACER.create_race(240, 320)
            hud.new_record = False
            self.assertTrue(hud.draw())
            self.assertEqual(hud.high_score.value, 15)


if __name__ == "__main__":
    unittest.main()
