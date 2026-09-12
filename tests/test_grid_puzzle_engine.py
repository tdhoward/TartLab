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


def state(cells=None, **fields):
    return g.create_state(g.validate_level(room(cells, **fields)))


def advance(level, milliseconds, direction=None):
    for unused in range(milliseconds // g.UPDATE_MS):
        g.step(level, direction)


class GridPuzzleMovementTests(unittest.TestCase):
    def test_cardinal_movement_and_edge_boundaries(self):
        for direction, expected in ((g.NORTH, 0), (g.WEST, 0), (g.EAST, 1), (g.SOUTH, 16)):
            level = state()
            g.step(level, direction)
            self.assertEqual(level.player.cell, expected)
            self.assertEqual(level.actor_at[expected], level.player.id)
            self.assertEqual(sum(a != -1 for a in level.actor_at), 1)
        for invalid in (True, -1, 4, (1, 1), "east"):
            with self.subTest(direction=invalid), self.assertRaises(ValueError):
                g.step(state(), invalid)
        with self.assertRaises(ValueError):
            g.step(state(), g.EAST, dt_ms=110)

    def test_locked_exit_wall_and_water_block_player(self):
        for token in ("#0", "#9", "W0", "W8", "E."):
            cells = {(1, 0): token, (3, 0): "K."}
            if token == "E.":
                cells[(15, 11)] = ".."
            level = state(cells)
            g.step(level, g.EAST)
            self.assertEqual(level.player.cell, 0)

    def test_failed_pushes_are_atomic_and_do_not_chain(self):
        for token in ("#0", "d1", "F2", "K.", "D.", "O.", "E.", "S.", "Xe", "RE", "T0"):
            cells = {(1, 0): "O.", (2, 0): token}
            if token == "E.":
                cells[(15, 11)] = ".."
            if token == "T0":
                cells[(3, 0)] = "T0"
            level = state(cells)
            before = (bytes(level.terrain), bytes(level.objects), list(level.actor_at))
            g.step(level, g.EAST)
            self.assertEqual((bytes(level.terrain), bytes(level.objects), level.actor_at), before)
            self.assertEqual(level.player.cell, 0)
            self.assertFalse(any(level.changed_cells))
        level = state({(0, 0): "..", (14, 0): "P.", (15, 0): "O."})
        g.step(level, g.EAST)
        self.assertEqual(level.player.cell, 14)
        self.assertEqual(level.objects[15], g.BOULDER)

    def test_push_moves_boulder_then_player_and_never_pulls(self):
        level = state({(1, 0): "O."})
        g.step(level, g.EAST)
        self.assertEqual(level.player.cell, 1)
        self.assertEqual(list(level.objects[:3]), [g.EMPTY, g.EMPTY, g.BOULDER])
        advance(level, 110, g.WEST)
        self.assertEqual(level.player.cell, 0)
        self.assertEqual(level.objects[2], g.BOULDER)
        self.assertEqual(level.objects[1], g.EMPTY)

    def test_all_water_variants_consume_boulder_and_become_floor(self):
        for variant in range(9):
            level = state({(1, 0): "O.", (2, 0): "W%s" % variant})
            g.step(level, g.EAST)
            self.assertEqual(level.player.cell, 1)
            self.assertEqual(level.terrain[2], g.FLOOR)
            self.assertEqual(level.variants[2], 0)
            self.assertFalse(any(level.objects))
            self.assertTrue(level.events[2] & g.TERRAIN_CHANGED)
            advance(level, 110, g.EAST)
            self.assertEqual(level.player.cell, 2)

    def test_first_move_and_repeat_are_110_ms_apart(self):
        level = state()
        movements = []
        for unused in range(50):
            previous = level.player.cell
            g.step(level, g.EAST)
            if level.player.cell != previous:
                movements.append(level.elapsed_ms)
        self.assertEqual(movements, [10, 120, 230, 340, 450])

    def test_failed_attempt_and_direction_changes_preserve_cooldown(self):
        level = state({(1, 0): "#0"})
        g.step(level, g.EAST)
        advance(level, 100, g.SOUTH)
        self.assertEqual(level.player.cell, 0)
        g.step(level, g.SOUTH)
        self.assertEqual(level.player.cell, 16)

    def test_release_stops_and_fresh_press_after_idle_moves_next_tick(self):
        level = state()
        g.step(level, g.EAST)
        advance(level, 1000)
        self.assertEqual(level.player.cell, 1)
        g.step(level, g.SOUTH)
        self.assertEqual(level.player.cell, 17)
        self.assertEqual(level.player.next_due_ms, 1130)

    def test_nonmultiple_interval_rounds_without_cumulative_drift(self):
        level = state(timers={"player_ms": 115})
        movements = []
        for unused in range(60):
            previous = level.player.cell
            g.step(level, g.EAST)
            if level.player.cell != previous:
                movements.append(level.elapsed_ms)
        self.assertEqual(movements, [10, 130, 240, 360, 470, 590])

    def test_collect_once_activate_exit_and_complete_once(self):
        level = state({(1, 0): "D.", (2, 0): "K.", (3, 0): "E.", (15, 11): ".."})
        g.step(level, g.EAST)
        self.assertEqual(level.score, 100)
        self.assertTrue(level.events[1] & g.COLLECTED)
        advance(level, 110, g.EAST)
        self.assertEqual(level.remaining_keys, 0)
        self.assertTrue(level.exit_active)
        self.assertTrue(level.changed_cells[3])
        advance(level, 110, g.EAST)
        self.assertEqual(level.status, g.COMPLETED)
        self.assertEqual(level.step_events, g.FINISHED)
        advance(level, 1000, g.WEST)
        self.assertEqual((level.elapsed_ms, level.score, level.player.cell), (230, 100, 3))
        self.assertEqual(level.step_events, 0)

    def test_zero_keys_and_optional_diamond(self):
        level = state({(1, 0): "E.", (15, 11): "..", (0, 1): "D."})
        self.assertTrue(level.exit_active)
        g.step(level, g.EAST)
        self.assertEqual((level.status, level.score), (g.COMPLETED, 0))

    def test_bonus_uses_unpaused_simulation_and_never_kills(self):
        level = state(bonusStart=2)
        advance(level, 990)
        self.assertEqual(level.bonus, 2)
        g.step(level)
        self.assertEqual(level.bonus, 1)
        level.paused = True
        advance(level, 10000, g.EAST)
        self.assertEqual((level.elapsed_ms, level.player.cell), (1000, 0))
        level.paused = False
        advance(level, 2000)
        self.assertEqual((level.bonus, level.status), (0, g.PLAYING))

    def test_death_and_nonliving_player_cannot_complete(self):
        for dead_status in (False, True):
            level = state()
            level.player.cell = level.definition["exit"]
            level.player.alive = False
            if dead_status:
                level.status = g.DEAD
            g.step(level)
            self.assertNotEqual(level.status, g.COMPLETED)
            self.assertEqual(level.step_events, 0)

    def test_change_buffers_are_reused_and_cleared(self):
        level = state()
        cells, events = level.changed_cells, level.events
        g.step(level, g.EAST)
        self.assertEqual([i for i, flag in enumerate(cells) if flag], [0, 1])
        g.step(level)
        self.assertIs(level.changed_cells, cells)
        self.assertIs(level.events, events)
        self.assertFalse(any(events) or any(cells))


class GridPuzzleSessionTests(unittest.TestCase):
    def test_restart_restores_playing_dead_paused_and_completed_attempts(self):
        definition = g.validate_level(room({(1, 0): "D.", (2, 0): "O.", (3, 0): "W4",
                                            (4, 0): "K.", (5, 0): "E.", (15, 11): ".."}))
        original = copy.deepcopy(definition)
        for status, paused in ((g.PLAYING, False), (g.PLAYING, True), (g.DEAD, False), (g.COMPLETED, False)):
            session = g.Session({"levels": (definition,)})
            session.direction = g.EAST
            session.advance(50)
            self.assertEqual((session.state.status, session.total_score()), (g.COMPLETED, 600))
            session.state.status, session.state.paused = status, paused
            session.restart()
            fresh = session.state
            self.assertEqual((fresh.player.cell, fresh.elapsed_ms, fresh.score, fresh.bonus), (0, 0, 0, 500))
            self.assertEqual((fresh.remaining_keys, fresh.paused, fresh.status), (1, False, g.PLAYING))
            self.assertEqual(fresh.objects, bytearray(definition["objects"]))
            self.assertEqual(fresh.terrain, bytearray(definition["terrain"]))
            self.assertEqual(session.banked_score, 0)
            self.assertIsNone(session.direction)
            self.assertEqual(definition, original)

    def test_room_score_banks_once_and_prior_rooms_survive_restart(self):
        first = g.validate_level(room({(1, 0): "D.", (2, 0): "E.", (15, 11): ".."}))
        second = g.validate_level(room({(1, 0): "E.", (15, 11): ".."}))
        session = g.Session({"levels": (first, second)})
        self.assertFalse(session.next_room())
        session.direction = g.EAST
        session.advance(30)
        self.assertEqual((session.banked_score, session.total_score()), (600, 600))
        session.advance(100)
        self.assertEqual(session.banked_score, 600)
        self.assertTrue(session.next_room())
        session.restart()
        self.assertEqual(session.banked_score, 600)
        session.direction = g.EAST
        session.advance(1)
        self.assertEqual(session.banked_score, 1100)
        self.assertFalse(session.next_room())
        session.restart()
        self.assertEqual(session.banked_score, 600)

    def test_future_mechanics_fail_clearly_at_play_time(self):
        for token in ("Xn", "S.", "RE"):
            definition = g.validate_level(room({(1, 0): token}))
            with self.assertRaisesRegex(ValueError, "Phase 4"):
                g.validate_playable_pack({"levels": (definition,)})

    def test_terrain_pads_and_messages_are_playable(self):
        definition = g.validate_level(room({(1, 0): "d0", (2, 0): "F0", (3, 0): "T0", (4, 0): "T0"},
            messages=[{"loc_x": 0, "loc_y": 0, "text": "Hi"}]))
        g.validate_playable_pack({"levels": (definition,)})


if __name__ == "__main__":
    unittest.main()
