import copy
import json
from pathlib import Path
import tempfile
import unittest

from tests.grid_puzzle_support import ENGINE as g, pack, room
from tools.check_grid_puzzle_levels import DEFAULT_SOLUTIONS, check, replay


class GridPuzzleReplayTests(unittest.TestCase):
    def test_dismiss_is_explicit_and_cannot_silently_skip_an_absent_message(self):
        trace = {"room": 0, "end_ms": 1000, "events": [
            {"at_ms": 0, "action": "dismiss"},
            {"at_ms": 0, "action": "press", "direction": "east"}],
            "expected": {"status": "completed", "score": 0, "bonus": 500, "elapsed_ms": 10}}
        cells = {(1, 0): "E.", (15, 11): ".."}
        definition = g.validate_level(room(cells, messages=[{"loc_x": 0, "loc_y": 0, "text": "Welcome"}]))
        self.assertEqual(replay(g, definition, trace)["status"], "passed")
        with self.assertRaisesRegex(ValueError, "requires an active message"):
            replay(g, g.validate_level(room(cells)), trace)

    def test_custom_rooms_without_solutions_do_not_claim_solvability(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "custom.json"
            path.write_text(json.dumps(pack()), encoding="utf-8")
            report = check(levels_path=path)
            self.assertEqual(report["status"], "passed")
            self.assertIn("pending", report["solution_replay"])

    def test_missing_duplicate_or_wrong_solution_fails_qualification(self):
        original = json.loads(DEFAULT_SOLUTIONS.read_text())
        for failure in ("missing", "duplicate", "outcome", "direction", "time", "version"):
            traces = copy.deepcopy(original)
            if failure == "missing":
                traces["solutions"] = []
            elif failure == "duplicate":
                traces["solutions"].append(traces["solutions"][0])
            elif failure == "outcome":
                traces["solutions"][0]["expected"]["score"] = 200
            elif failure == "direction":
                traces["solutions"][0]["events"][0]["direction"] = "northeast"
            elif failure == "time":
                traces["solutions"][0]["events"][0]["at_ms"] = 7
            else:
                traces["schema_version"] = 2
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "solutions.json"
                path.write_text(json.dumps(traces), encoding="utf-8")
                report = check(solutions_path=path)
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["solution_replay"], "failed")
                self.assertTrue(report["errors"])

    def test_releasing_direction_during_wait_prevents_extra_moves(self):
        definition = g.validate_level(room({(2, 0): "E.", (15, 11): ".."}))
        trace = {"room": 0, "end_ms": 1100, "events": [
            {"at_ms": 0, "action": "press", "direction": "east"},
            {"at_ms": 10, "action": "release"}, {"at_ms": 100, "action": "wait"},
            {"at_ms": 1000, "action": "press", "direction": "east"}],
            "expected": {"status": "completed", "score": 0, "bonus": 499, "elapsed_ms": 1010}}
        self.assertEqual(replay(g, definition, trace)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
