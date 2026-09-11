import copy
import unittest
from unittest import mock

from tests.grid_puzzle_support import DEFAULT_ENGINE, ENGINE as g, room


class GridPuzzleStateTests(unittest.TestCase):
    def test_loading_definitions_performs_no_import_io_or_device_work(self):
        source = compile(DEFAULT_ENGINE.read_bytes(), str(DEFAULT_ENGINE), "exec")
        namespace = {"_GRID_PUZZLE_AUTOSTART": False}
        with mock.patch("builtins.open", side_effect=AssertionError("unexpected open")), \
                mock.patch("builtins.__import__", side_effect=AssertionError("unexpected import")):
            exec(source, namespace)
        self.assertTrue(callable(namespace["create_state"]))
        self.assertTrue(callable(namespace["main"]))

    def test_fresh_state_reconstructs_every_mutable_layer(self):
        definition = g.validate_level(room({(1, 0): "K.", (2, 0): "XW", (3, 0): "RE"},
            messages=[{"loc_x": 0, "loc_y": 0, "text": "Welcome"}]))
        before = copy.deepcopy(definition)
        first = g.create_state(definition)
        first.terrain[1] = g.WALL
        first.objects[1] = g.EMPTY
        first.variants[1] = 9
        first.actors[1].heading = g.SOUTH
        first.actors[1].next_due_ms += 1000
        first.actors[2].trap_state = g.STOPPED
        first.actor_at[0] = -1
        first.spear_at[7] = 2
        first.message_seen[0] = 0
        first.active_message = -1
        first.pending_explosions[3] = 1
        first.changed_cells[3] = 1
        first.status, first.elapsed_ms, first.score = g.DEAD, 9000, 100
        first.bonus, first.remaining_keys, first.exit_active = 0, 0, True
        restored = g.create_state(definition)
        self.assertEqual(definition, before)
        self.assertEqual(restored.terrain[1], g.FLOOR)
        self.assertEqual(restored.objects[1], g.KEY)
        self.assertEqual(restored.variants[1], 0)
        self.assertEqual((restored.actors[1].heading, restored.actors[1].follow), (g.WEST, g.FOLLOW_RIGHT))
        self.assertEqual(restored.actors[1].next_due_ms, g.SPIDER_MS)
        self.assertEqual(restored.actors[2].trap_state, g.IDLE)
        self.assertEqual(restored.actor_at[0], restored.player.id)
        self.assertEqual(restored.spear_at, [-1] * 192)
        self.assertEqual(list(restored.message_seen), [1])
        self.assertTrue(restored.paused)
        self.assertEqual(restored.active_message, 0)
        self.assertFalse(any(restored.changed_cells) or any(restored.pending_explosions))
        self.assertEqual((restored.status, restored.elapsed_ms, restored.score, restored.bonus), (g.PLAYING, 0, 0, 500))
        self.assertEqual(restored.remaining_keys, 1)
        self.assertFalse(restored.exit_active)

    def test_stable_actor_ids_and_independent_deadlines(self):
        state = g.create_state(g.validate_level(room({(2, 1): "Xn", (1, 1): "Xe", (3, 1): "S."})))
        self.assertEqual([actor.id for actor in state.actors], [0, 1, 2, 3])
        self.assertEqual([actor.cell for actor in state.actors], [0, 17, 18, 19])
        state.actors[1].next_due_ms += 150
        self.assertEqual(state.actors[2].next_due_ms, 150)
        self.assertEqual(state.actors[3].heading, g.WEST)
        self.assertEqual(len(state.terrain), 192)
        self.assertTrue(all(type(value) is int for value in state.terrain))

    def test_bounded_coordinates_and_cardinal_neighbors_do_not_wrap(self):
        for x, y in ((-1, 0), (16, 0), (0, -1), (0, 12)):
            self.assertEqual(g.cell_at(x, y), -1)
        for cell, direction in ((0, g.NORTH), (0, g.WEST), (15, g.EAST), (191, g.SOUTH), (-1, g.EAST)):
            self.assertEqual(g.neighbor(cell, direction), -1)
        self.assertEqual([g.neighbor(17, heading) for heading in range(4)], [1, 18, 33, 16])


if __name__ == "__main__":
    unittest.main()
