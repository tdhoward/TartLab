import copy
import json
from pathlib import Path
import tempfile
import unittest

from tests.grid_puzzle_support import DEFAULT_LEVELS, ENGINE as g, pack, room


class GridPuzzleLevelTests(unittest.TestCase):
    def test_bundled_pack_and_all_symbol_fixture_validate(self):
        self.assertEqual(g.load_level_pack(str(DEFAULT_LEVELS))["levels"][0]["name"], "First Crossing")
        fixture = Path(__file__).parent / "fixtures/grid_puzzle/all_symbols.json"
        definition = g.load_level_pack(str(fixture))["levels"][0]
        self.assertEqual(len(definition["tokens"]), 192)
        for prefix, count in (("#", 10), ("W", 9), ("d", 10), ("F", 10)):
            cells = [i for i, token in enumerate(definition["tokens"]) if token[0] == prefix]
            self.assertEqual([definition["variants"][cell] for cell in cells], list(range(count)))
        self.assertEqual(sum(cell >= 0 for cell in definition["twins"]), 20)

    def test_pack_rejects_version_shape_types_and_unknown_fields(self):
        invalid = [None, [], {}, {"version": 1}, {"levels": []},
                   {"version": 1, "levels": []}, {"version": 1, "levels": {}},
                   {**pack(), "surprise": 1}]
        invalid += [{**pack(), "version": value} for value in (0, 2, True, "1", 1.0, None)]
        invalid += [pack(value) for value in ([], "room", True)]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                g.validate_level_pack(data)

    def test_room_shape_and_map_coordinates_in_diagnostics(self):
        invalid = [{}, {"name": "x"}, room(map=[]), room(map=[".."] * 12),
                   room(name=" "), room(teleporters=[]), room(remainingKeys=0)]
        invalid += [room(map=value) for value in (True, "..", [None] * 12)]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                g.validate_level(data)
        with self.assertRaisesRegex(ValueError, 'room 2 "Bad water", row 4, column 7:.*W9'):
            g.validate_level(room({(7, 4): "W9"}, name="Bad water"), 1)

    def test_token_spelling_and_case_are_strict(self):
        for token in ("W9", "W00", "xN", "xn", "XL", "XR", "X.", "Xq", "T.",
                      "Rn", "R.", "K0", "P", "E", "#", "dA", "F-", "T١"):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, "unknown token"):
                g.validate_level(room({(2, 2): token}))
        data = room()
        data["map"] = ["  \t" + row.replace(" ", "  ") + " " for row in data["map"]]
        self.assertEqual(len(g.validate_level(data)["terrain"]), 192)

    def test_exactly_one_start_and_exit_but_zero_keys_allowed(self):
        for cells in ({(0, 0): ".."}, {(15, 11): ".."}, {(2, 2): "P."}, {(2, 2): "E."}):
            with self.subTest(cells=cells), self.assertRaisesRegex(ValueError, "one player start and one exit"):
                g.validate_level(room(cells))
        state = g.create_state(g.validate_level(room()))
        self.assertEqual(state.remaining_keys, 0)
        self.assertTrue(state.exit_active)

    def test_tokens_expand_to_legal_separate_layers(self):
        cells = {(1, 0): "K.", (2, 0): "D.", (3, 0): "O.", (4, 0): "d7",
                 (5, 0): "F9", (6, 0): "W8", (7, 0): "T3", (8, 0): "T3"}
        definition = g.validate_level(room(cells))
        self.assertEqual(definition["objects"][1:4], (g.KEY, g.DIAMOND, g.BOULDER))
        self.assertEqual(definition["terrain"][1:9], (g.FLOOR, g.FLOOR, g.FLOOR,
                          g.DIRT, g.FALSE_WALL, g.WATER, g.FLOOR, g.FLOOR))
        self.assertEqual(definition["objects"][7:9], (g.EMPTY, g.EMPTY))
        self.assertEqual(definition["twins"][7:9], (8, 7))

    def test_all_eight_spider_tokens_preserve_heading_and_follow_mode(self):
        tokens = ("Xn", "Xe", "Xs", "Xw", "XN", "XE", "XS", "XW")
        definition = g.validate_level(room({(i, 1): token for i, token in enumerate(tokens)}))
        spiders = [actor for actor in definition["actors"] if actor[0] == g.SPIDER]
        self.assertEqual([actor[2] for actor in spiders], [0, 1, 2, 3] * 2)
        self.assertEqual([actor[3] for actor in spiders], [g.FOLLOW_LEFT] * 4 + [g.FOLLOW_RIGHT] * 4)

    def test_teleporter_counts_and_independent_rooms(self):
        for count in (1, 3, 4):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "T9 occurs %s times at" % count):
                g.validate_level(room({(i, 2): "T9" for i in range(count)}))
        rooms = [room({(1, y): "T0", (2, y): "T0", (3, y): "T1", (4, y): "T1"}) for y in (1, 2)]
        validated = g.validate_level_pack({"version": 1, "levels": rooms})
        for y, definition in enumerate(validated["levels"], 1):
            self.assertEqual(definition["twins"][16 * y + 1:16 * y + 5],
                             (16 * y + 2, 16 * y + 1, 16 * y + 4, 16 * y + 3))
        with self.assertRaises(ValueError):
            g.validate_level_pack({"version": 1, "levels": [room({(1, 1): "T0"}), room({(2, 2): "T0"})]})

    def test_timer_precedence_and_actor_metadata(self):
        definition = g.validate_level(room({(1, 1): "RN", (2, 1): "RE", (3, 1): "Xw"},
            timers={"spider_ms": 157, "projectile_ms": 43}, actors=[{"x": 1, "y": 1, "step_ms": 23}]))
        self.assertEqual([record[4] for record in definition["actors"]], [g.PLAYER_MS, 23, 43, 157])
        for cells in ({(1, 1): "Xw"}, {(1, 1): "S."}, {(1, 1): "K."}, {}):
            with self.subTest(cells=cells), self.assertRaisesRegex(ValueError, "only map spear emitters"):
                g.validate_level(room(cells, actors=[{"x": 1, "y": 1, "step_ms": 40}]))
        annotation = {"x": 1, "y": 1, "step_ms": 40}
        invalid = [[annotation, annotation], [{**annotation, "heading": "north"}],
                   [{"x": 1, "y": 1}], [True], {}, [annotation] * 193]
        for field, values in (("x", (-1, 16, True, "1", 1.5)), ("y", (-1, 12, False)),
                              ("step_ms", (0, 9, True, 40.5))):
            invalid.extend([[{**annotation, field: value}] for value in values])
        for annotations in invalid:
            with self.subTest(annotations=annotations), self.assertRaises(ValueError):
                g.validate_level(room({(1, 1): "RN"}, actors=annotations))

    def test_rules_scores_and_timers_are_validated(self):
        invalid = [{"bonusStart": value} for value in (-1, True, "500", 0.5)]
        invalid += [{"timers": {"player_ms": value}} for value in (-1, 0, 9, True, "10", 10.5)]
        invalid += [{"timers": {"frame_ms": 50}}, {"timers": []}, {"rules": []},
                    {"rules": {"explosion_radius": 5}},
                    {"rules": {"explosion_destructible": ["KEY"]}},
                    {"rules": {"explosion_destructible": ["DIRT", "DIRT"]}},
                    {"rules": {"explosion_destructible": "DIRT"}},
                    {"rules": {"explosion_diamonds": 1}}, {"rules": {"explosion_hurts_player": "false"}}]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                g.validate_level(room(**fields))
        definition = g.validate_level(room(bonusStart=0, timers={"player_ms": 11},
            rules={"explosion_destructible": [], "explosion_hurts_player": False}))
        self.assertEqual(definition["timers"]["player_ms"], 11)
        self.assertEqual(definition["rules"]["explosion_destructible"], ())

    def test_message_types_locations_and_bounds(self):
        message = {"text": "Look here", "loc_x": 1, "loc_y": 1}
        invalid = [True, {}, [None], [message] * 193, [message, message],
                   [{**message, "once": True}], [{**message, "text": ""}]]
        for field, values in (("loc_x", (-1, 16, True, "1", 0.1)), ("loc_y", (-1, 12, False))):
            invalid.extend([[{**message, field: value}] for value in values])
        for messages in invalid:
            with self.subTest(messages=messages), self.assertRaises(ValueError):
                g.validate_level(room(messages=messages))
        for token in ("#0", "W4", "S.", "RN"):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, "message location"):
                g.validate_level(room({(1, 1): token}, messages=[message]))
        for token in ("d0", "F0", "O.", "D.", "Xn"):
            g.validate_level(room({(1, 1): token}, messages=[message]))
        g.validate_level(room({(1, 1): "T0", (2, 1): "T0"}, messages=[message]))

    def test_selected_file_errors_include_path_without_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "custom.json"
            for data in (None, '{"version":', json.dumps(pack(room({(2, 2): "W9"})))):
                if data is not None:
                    path.write_text(data, encoding="utf-8")
                with self.subTest(data=data), self.assertRaises(ValueError) as caught:
                    g.load_level_pack(str(path))
                self.assertIn(str(path), str(caught.exception))

    def test_validation_does_not_mutate_or_alias_input(self):
        data = pack(room(timers={"player_ms": 30}, rules={"explosion_destructible": ["DIRT"]}))
        original = copy.deepcopy(data)
        result = g.validate_level_pack(data)
        self.assertEqual(data, original)
        data["levels"][0]["rules"]["explosion_destructible"].append("BOULDER")
        data["levels"][0]["timers"]["player_ms"] = 50
        self.assertEqual(result["levels"][0]["rules"]["explosion_destructible"], ("DIRT",))
        self.assertEqual(result["levels"][0]["timers"]["player_ms"], 30)


if __name__ == "__main__":
    unittest.main()
