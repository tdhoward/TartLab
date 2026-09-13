"""Hazard outcomes through the actual student-editable source, with exact time."""

import copy
from pathlib import Path
import unittest

from tests.grid_puzzle_support import ENGINE as g, room
from tests.test_grid_puzzle_engine import state, advance


FIXTURES = Path(__file__).parent / "fixtures/grid_puzzle/hazards.json"


def actor_of(level, kind):
    return next(actor for actor in level.actors if actor.kind == kind)


def fixture(name):
    return g.create_state(next(d for d in g.load_level_pack(str(FIXTURES))["levels"] if d["name"] == name))


class SnakeTests(unittest.TestCase):
    def test_horizontal_both_directions_never_vertical_and_faces_player(self):
        for player, expected in (((2, 4), g.DEAD), ((8, 4), g.DEAD), ((5, 1), g.PLAYING)):
            level = state({(0, 0): "..", player: "P.", (5, 4): "S."})
            g.step(level)
            snake = actor_of(level, g.SNAKE)
            self.assertEqual(level.status, expected)
            self.assertEqual(snake.heading, g.WEST if player[0] < 5 else g.EAST)
            self.assertEqual(snake.cell, g.cell_at(5, 4))

    def test_every_blocker_and_transparent_terrain(self):
        for token in ("#9", "F8", "d7", "K.", "D.", "O.", "E.", "RE", "Xe", "W8", "..", "T0"):
            cells = {(0, 0): "..", (1, 3): "S.", (3, 3): token, (6, 3): "P."}
            if token == "E.":
                cells.update({(15, 11): "..", (2, 8): "K."})
            if token == "T0":
                cells[(8, 8)] = "T0"
            level = state(cells)
            g.step(level)
            self.assertEqual(level.status, g.DEAD if token in ("W8", "..", "T0") else g.PLAYING, token)
        level = state({(0, 0): "..", (1, 3): "S.", (3, 3): "E.", (6, 3): "P.", (15, 11): ".."})
        g.step(level)
        self.assertEqual(level.status, g.DEAD)  # Unlocked exit is transparent.

    def test_collecting_cover_kills_in_same_tick(self):
        for token in ("K.", "D."):
            level = state({(0, 0): "..", (1, 3): "S.", (4, 3): token, (5, 3): "P."})
            g.step(level, g.WEST)
            self.assertEqual((level.status, level.objects[g.cell_at(4, 3)]), (g.DEAD, g.EMPTY))
            self.assertEqual(level.remaining_keys, 0)
            self.assertEqual(level.score, 100 if token == "D." else 0)

    def test_idle_player_dies_when_cover_spider_moves(self):
        level = fixture("Moving cover")
        advance(level, 140)
        self.assertEqual(level.status, g.PLAYING)
        g.step(level)
        self.assertEqual((level.status, level.elapsed_ms), (g.DEAD, 150))
        self.assertEqual(actor_of(level, g.SPIDER).cell, g.cell_at(3, 2))

    def test_explosion_removes_cover_immediately_unless_drop_replaces_it(self):
        for diamonds in (False, True):
            level = state({(0, 0): "..", (1, 5): "S.", (8, 5): "P.",
                           (5, 4): "Xe", (4, 4): "#0", (6, 4): "#0", (5, 3): "#0", (5, 5): "O."},
                          rules={"explosion_diamonds": diamonds})
            g.step(level)
            self.assertEqual(level.status, g.PLAYING if diamonds else g.DEAD)
            self.assertEqual(level.objects[g.cell_at(5, 5)], g.DIAMOND if diamonds else g.EMPTY)

    def test_growing_and_stopped_spears_both_provide_cover(self):
        for mode in (g.EXTENDING, g.STOPPED):
            level = state({(0, 0): "..", (1, 4): "S.", (7, 4): "P.", (4, 2): "RS"})
            trap = actor_of(level, g.EMITTER)
            trap.trap_state, trap.next_due_ms = mode, 1000
            level.spear_at[g.cell_at(4, 4)] = trap.id
            g.step(level)
            self.assertEqual(level.status, g.PLAYING)


class SpiderTests(unittest.TestCase):
    def test_all_eight_tokens_move_autonomously_and_restart_restores_heading(self):
        for token in ("Xn", "Xe", "Xs", "Xw", "XN", "XE", "XS", "XW"):
            level = state({(5, 5): token})
            spider = actor_of(level, g.SPIDER)
            heading = "nesw".index(token[1].lower())
            follow = g.FOLLOW_LEFT if token[1].islower() else g.FOLLOW_RIGHT
            expected = heading
            advance(level, 140)
            self.assertEqual(spider.cell, g.cell_at(5, 5))
            g.step(level)
            self.assertEqual((spider.cell, spider.heading, spider.follow),
                             (g.neighbor(g.cell_at(5, 5), expected), expected, follow))
            fresh = actor_of(g.create_state(level.definition), g.SPIDER)
            self.assertEqual((fresh.heading, fresh.follow, fresh.next_due_ms), (heading, follow, 150))

    def test_both_turn_orders_including_dead_end_reverse(self):
        for token, order in (("Xe", (g.EAST, g.SOUTH, g.WEST, g.NORTH)),
                             ("XE", (g.EAST, g.NORTH, g.WEST, g.SOUTH))):
            for blocked in range(4):
                cells = {(5, 5): token}
                for heading in order[:blocked]:
                    cell = g.neighbor(g.cell_at(5, 5), heading)
                    cells[(cell % 16, cell // 16)] = "#0"
                level = state(cells)
                advance(level, 150)
                spider = actor_of(level, g.SPIDER)
                self.assertEqual((spider.heading, spider.cell),
                                 (order[blocked], g.neighbor(g.cell_at(5, 5), order[blocked])))

    def test_open_area_continues_straight_for_both_types_and_all_headings(self):
        for token in ("Xn", "Xe", "Xs", "Xw", "XN", "XE", "XS", "XW"):
            level = state({(6, 5): token})
            spider = actor_of(level, g.SPIDER)
            heading = spider.heading
            dx, dy = g.DIRECTIONS[heading]
            for moves in range(1, 5):
                advance(level, 150)
                self.assertEqual((spider.cell, spider.heading),
                                 (g.cell_at(6 + moves * dx, 5 + moves * dy), heading), token)
            self.assertEqual(level.status, g.PLAYING)

    def test_move_into_any_orthogonal_neighbor_kills_idle_player(self):
        for token, x, y in (("Xe", 3, 5), ("Xw", 7, 5), ("Xs", 5, 3), ("Xn", 5, 7)):
            level = state({(0, 0): "..", (5, 5): "P.", (x, y): token})
            advance(level, 140)
            self.assertEqual(level.status, g.PLAYING)
            g.step(level)
            self.assertEqual((level.status, level.elapsed_ms, level.step_events),
                             (g.DEAD, 150, g.DIED), token)
            snapshot = [(a.cell, a.next_due_ms) for a in level.actors]
            g.step(level)
            self.assertEqual([(a.cell, a.next_due_ms) for a in level.actors], snapshot)
            self.assertEqual(level.step_events, 0)

    def test_diagonal_and_row_wrapped_cells_are_not_adjacent(self):
        for player, spider, token in (((5, 5), (3, 4), "Xe"),
                                      ((0, 6), (15, 4), "Xs"),
                                      ((5, 5), (1, 5), "Xe")):
            level = state({(0, 0): "..", player: "P.", spider: token})
            advance(level, 150)
            self.assertEqual(level.status, g.PLAYING, (player, spider))

    def test_adjacent_spider_waits_for_move_then_kills_even_on_departure(self):
        level = state({(0, 0): "..", (5, 5): "P.", (6, 5): "XE"})
        advance(level, 140)
        self.assertEqual(level.status, g.PLAYING)
        g.step(level)
        self.assertEqual((level.status, actor_of(level, g.SPIDER).cell),
                         (g.DEAD, g.cell_at(7, 5)))
        # A spider that cannot move does not apply the movement-contact rule.
        level = fixture("Exit blast")
        level.definition["rules"]["explosion_hurts_player"] = False
        g.step(level, g.EAST)
        self.assertEqual(level.status, g.COMPLETED)

    def test_teleport_entry_and_arrival_both_check_orthogonal_neighbors(self):
        for player in ((9, 7), (2, 2)):
            level = state({(0, 0): "..", (8, 8): "Xe", (9, 8): "T0", (2, 3): "T0", player: "P."})
            advance(level, 150)
            self.assertEqual(level.status, g.DEAD, player)
            spider = actor_of(level, g.SPIDER)
            self.assertEqual((spider.cell, spider.heading, spider.next_due_ms),
                             (g.cell_at(2, 3), g.EAST, 300))

    def test_adjacent_spider_move_wins_over_exit_completion(self):
        level = state({(0, 0): "..", (15, 11): "..", (5, 5): "P.",
                       (6, 5): "E.", (8, 5): "Xw"}, timers={"spider_ms": 10})
        g.step(level, g.EAST)
        self.assertTrue(level.exit_active)
        self.assertEqual(level.player.cell, level.definition["exit"])
        self.assertEqual((level.status, level.step_events), (g.DEAD, g.DIED))

    def test_blockers_reject_moves_and_active_exit_is_always_blocked(self):
        for token in ("#0", "F0", "d0", "W0", "K.", "D.", "O.", "E.", "S.", "RE", "Xn"):
            cells = {(5, 5): "Xe", (5, 4): token}
            if token == "E.":
                cells[(15, 11)] = ".."
            level = state(cells)
            spider = next(a for a in level.actors if a.cell == g.cell_at(5, 5))
            self.assertEqual(g.spider_destination(level, spider, g.NORTH), -1, token)
        for mode in (g.EXTENDING, g.STOPPED):
            level = state({(5, 5): "Xe", (8, 4): "RE"})
            spider, trap = actor_of(level, g.SPIDER), actor_of(level, g.EMITTER)
            trap.trap_state = mode
            level.spear_at[g.cell_at(5, 4)] = trap.id
            self.assertEqual(g.spider_destination(level, spider, g.NORTH), -1)

    def test_independent_nonmultiple_deadlines_do_not_drift(self):
        level = state({(5, 5): "Xe", (10, 5): "XE"}, timers={"spider_ms": 155})
        spiders = [a for a in level.actors if a.kind == g.SPIDER]
        spiders[1].next_due_ms += 20
        traces = [[], []]
        for unused in range(64):
            previous = [a.cell for a in spiders]
            g.step(level)
            for i, actor in enumerate(spiders):
                if actor.cell != previous[i]:
                    traces[i].append(level.elapsed_ms)
        self.assertEqual(traces, [[160, 310, 470, 620], [180, 330, 490, 640]])
        self.assertEqual([a.next_due_ms for a in spiders], [775, 795])

    def test_stable_order_resolves_competing_destinations_without_overlap(self):
        cells = {(4, 5): "Xe", (6, 5): "Xw", (4, 4): "#0", (6, 6): "#0"}
        level = state(cells)
        advance(level, 150)
        spiders = [a for a in level.actors if a.kind == g.SPIDER]
        self.assertEqual([a.cell for a in spiders], [g.cell_at(5, 5), g.cell_at(6, 4)])
        for spider in spiders:
            self.assertEqual(level.actor_at[spider.cell], spider.id)

    def test_adjacent_spiders_cannot_swap_and_trapped_set_is_one_snapshot(self):
        level = fixture("Trapped neighbors")
        g.step(level)  # Neither timer is due, but both are already trapped.
        spiders = [a for a in level.actors if a.kind == g.SPIDER]
        self.assertFalse(any(a.alive for a in spiders))
        self.assertEqual(sum(obj == g.DIAMOND for obj in level.objects), 4)
        self.assertEqual(sum(level.blast_cells), 8)
        self.assertFalse(any(level.pending_explosions))
        self.assertEqual(level.objects[g.cell_at(4, 5)], g.DIAMOND)
        self.assertEqual(level.terrain[g.cell_at(7, 5)], g.FLOOR)

    def test_player_enemy_crossing_and_idle_contact_are_lethal(self):
        for direction in (g.EAST, None):
            level = state({(0, 0): "..", (4, 5): "P.", (5, 5): "Xw", (5, 6): "#0"},
                          timers={"spider_ms": 10})
            g.step(level, direction)
            self.assertEqual((level.status, level.step_events), (g.DEAD, g.DIED))
        # The player moves first, but the pursuing spider finishes adjacent.
        level = state({(0, 0): "..", (4, 5): "P.", (5, 5): "Xw", (5, 6): "#0"},
                      timers={"spider_ms": 10})
        g.step(level, g.NORTH)
        self.assertEqual(level.status, g.DEAD)
        self.assertEqual(actor_of(level, g.SPIDER).cell, g.cell_at(4, 5))

    def test_committed_spider_hop_matches_preview_and_preserves_deadline(self):
        for blocked in (False, True):
            cells = {(5, 5): "Xn", (5, 4): "T0", (10, 7): "T0", (12, 8): "RE"}
            level = state(cells)
            spider, emitter = actor_of(level, g.SPIDER), actor_of(level, g.EMITTER)
            if blocked:
                level.spear_at[g.cell_at(10, 7)] = emitter.id
                emitter.trap_state = g.STOPPED
            before = (list(level.actor_at), spider.cell, spider.heading, spider.next_due_ms)
            destination = g.spider_destination(level, spider, g.NORTH)
            self.assertEqual((level.actor_at, spider.cell, spider.heading, spider.next_due_ms), before)
            advance(level, 150)
            self.assertEqual((spider.cell, spider.heading, spider.next_due_ms), (destination, g.NORTH, 300))
            advance(level, 140)
            self.assertEqual(spider.cell, destination)  # No bounce/retry while stationary.

    def test_spider_teleport_arrival_on_player_kills_and_own_twin_is_legal(self):
        level = state({(5, 5): "Xn", (5, 4): "T0", (10, 7): "T0"})
        g.place_actor(level, level.player, g.cell_at(10, 7))
        advance(level, 150)
        self.assertEqual((level.status, actor_of(level, g.SPIDER).cell), (g.DEAD, level.player.cell))
        level = state({(5, 5): "T0", (5, 4): "T0", (10, 7): "Xe",
                       (4, 5): "#0", (6, 5): "#0", (5, 6): "#0"})
        spider = actor_of(level, g.SPIDER)
        g.place_actor(level, spider, g.cell_at(5, 5))
        advance(level, 150)
        self.assertTrue(spider.alive)
        self.assertEqual((spider.cell, spider.heading), (g.cell_at(5, 5), g.NORTH))


class SpearTests(unittest.TestCase):
    def test_all_map_directions_activate_then_extend_exactly_one_cell_per_deadline(self):
        for token, dx, dy in (("RN", 0, -1), ("RE", 1, 0), ("RS", 0, 1), ("RW", -1, 0)):
            level = state({(0, 0): "..", (5, 5): token, (5 + 3 * dx, 5 + 3 * dy): "P."})
            trap = actor_of(level, g.EMITTER)
            g.step(level)
            self.assertEqual((trap.trap_state, trap.next_due_ms, trap.tip), (g.EXTENDING, 50, g.cell_at(5, 5)))
            advance(level, 30)
            self.assertFalse(any(i >= 0 for i in level.spear_at))
            g.step(level)
            self.assertEqual(trap.tip, g.cell_at(5 + dx, 5 + dy))
            self.assertEqual(sum(i >= 0 for i in level.spear_at), 1)
            advance(level, 40)
            self.assertEqual(trap.tip, g.cell_at(5 + 2 * dx, 5 + 2 * dy))
            self.assertEqual(level.status, g.PLAYING)
            advance(level, 40)
            self.assertEqual((level.status, level.elapsed_ms), (g.DEAD, 130))

    def test_wrong_direction_and_every_obstructing_layer_prevent_activation(self):
        for token in ("#0", "F0", "d0", "K.", "D.", "O.", "E.", "S.", "Xe", "RW"):
            cells = {(0, 0): "..", (2, 5): "RE", (4, 5): token, (7, 5): "P."}
            if token == "E.":
                cells.update({(15, 11): "..", (9, 8): "K."})
            level = state(cells)
            g.step(level)
            self.assertEqual(actor_of(level, g.EMITTER).trap_state, g.IDLE, token)
        for player in ((1, 5), (7, 4), (2, 8)):
            level = state({(0, 0): "..", (2, 5): "RE", player: "P."})
            g.step(level)
            self.assertEqual(actor_of(level, g.EMITTER).trap_state, g.IDLE)

    def test_water_open_exit_and_hidden_pads_transmit_detection_and_extension(self):
        for token in ("W8", "E.", "T0"):
            cells = {(0, 0): "..", (2, 5): "RE", (3, 5): token, (5, 5): "P."}
            if token == "E.":
                cells[(15, 11)] = ".."
            if token == "T0":
                cells[(8, 8)] = "T0"
            level = state(cells)
            advance(level, 50)
            self.assertEqual(actor_of(level, g.EMITTER).tip, g.cell_at(3, 5))

    def test_tip_contact_before_blocker_is_fatal_before_same_advance_stops(self):
        level = fixture("Spear lane")
        advance(level, 130)
        trap = actor_of(level, g.EMITTER)
        self.assertEqual((level.status, trap.trap_state, trap.tip), (g.DEAD, g.STOPPED, g.cell_at(5, 5)))
        self.assertEqual(level.terrain[g.cell_at(6, 5)], g.WALL)

    def test_stops_before_edge_and_never_rearms_after_blocker_removed(self):
        for edge in (False, True):
            level = state({(0, 0): "..", (12, 5): "RE", (14, 5): "P.", (15, 5): ".." if edge else "O."})
            g.step(level)
            g.step(level, g.NORTH)
            advance(level, 160)
            trap = actor_of(level, g.EMITTER)
            self.assertEqual((level.status, trap.trap_state), (g.PLAYING, g.STOPPED))
            self.assertEqual(trap.tip, g.cell_at(15 if edge else 14, 5))
            self.assertEqual(level.objects[g.cell_at(15, 5)], g.EMPTY if edge else g.BOULDER)
            tip, shaft = trap.tip, list(level.spear_at)
            level.objects[g.cell_at(15, 5)] = g.EMPTY
            advance(level, 1000)
            self.assertEqual((trap.tip, level.spear_at, trap.trap_state), (tip, shaft, g.STOPPED))
            self.assertFalse(g.can_player_enter(level, tip))
            self.assertFalse(g.accepts_boulder(level, tip))

    def test_new_blocker_stops_before_it_without_damage_or_consumption(self):
        for token in ("#0", "d0", "F0", "W0", "K.", "D.", "O.", "E.", "S.", "Xe", "RE"):
            level = fixture("Spear lane")
            trap = actor_of(level, g.EMITTER)
            g.step(level)
            g.step(level, g.NORTH)
            cell = g.cell_at(3, 5)
            terrain, variant, obj, kind, heading, follow, label = g.decode_token(token)
            level.terrain[cell], level.objects[cell] = terrain, obj
            if token == "E.":
                level.exit_active = False
            if kind != -1:
                other = g.Actor(len(level.actors), (kind, cell, heading, follow, 150))
                level.actors.append(other)
                level.actor_at[cell] = other.id
            level.elapsed_ms = 50
            g.advance_spears(level)
            if token == "W0":
                self.assertEqual(trap.tip, cell)
            else:
                self.assertEqual((trap.tip, trap.trap_state), (trap.cell, g.STOPPED), token)
            self.assertEqual((level.terrain[cell], level.objects[cell]), (terrain, obj))

    def test_existing_growing_shaft_contact_is_fatal_and_stopped_is_solid(self):
        level = fixture("Spear lane")
        g.step(level)
        g.step(level, g.NORTH)
        advance(level, 70)  # Shaft reaches (4,5); player above (5,5).
        level.player.next_due_ms = 100
        g.step(level, g.WEST)
        level.player.next_due_ms = 110
        g.step(level, g.SOUTH)
        self.assertEqual((level.player.cell, level.status), (g.cell_at(4, 5), g.DEAD))

    def test_crossing_spears_resolve_in_actor_order_without_overlap(self):
        level = state({(2, 5): "RE", (5, 2): "RS"})
        traps = [a for a in level.actors if a.kind == g.EMITTER]
        for trap in traps:
            trap.trap_state, trap.next_due_ms = g.EXTENDING, 10
        advance(level, 90)
        first, second = traps
        self.assertEqual(first.tip, g.cell_at(5, 5))
        self.assertEqual(level.spear_at[first.tip], first.id)
        self.assertEqual((second.tip, second.trap_state), (g.cell_at(4, 5), g.STOPPED))

    def test_room_interval_and_per_emitter_override_keep_independent_deadlines(self):
        level = state({(2, 5): "RE", (8, 8): "RN"}, timers={"projectile_ms": 45},
                      actors=[{"x": 8, "y": 8, "step_ms": 65}])
        traps = [a for a in level.actors if a.kind == g.EMITTER]
        for trap in traps:
            trap.trap_state, trap.next_due_ms = g.EXTENDING, trap.interval_ms + 10
        moves = [[], []]
        for unused in range(21):
            previous = [a.tip for a in traps]
            g.step(level)
            for i, trap in enumerate(traps):
                if previous[i] != trap.tip:
                    moves[i].append(level.elapsed_ms)
        self.assertEqual(moves, [[60, 100, 150, 190], [80, 140, 210]])


class ExplosionAndOrderingTests(unittest.TestCase):
    def test_clipped_footprint_and_drops_only_on_center_or_newly_cleared_floor(self):
        for origin, expected in ((0, {0, 1, 16}), (15, {14, 15, 31}),
                                 (191, {175, 190, 191}), (80, {64, 80, 81, 96})):
            level = state({(0, 0): "..", (9, 9): "P.", (15, 11): "..", (13, 11): "E."})
            level.pending_explosions[origin] = 1
            g.resolve_explosions(level)
            self.assertEqual({i for i, flag in enumerate(level.blast_cells) if flag}, expected)
            self.assertEqual({i for i, obj in enumerate(level.objects) if obj == g.DIAMOND}, {origin})
            self.assertEqual(level.score, 0)

    def test_destructible_options_and_generation_are_independent(self):
        for types in ([], ["BOULDER"], ["DIRT"], ["BOULDER", "DIRT"]):
            for diamonds in (False, True):
                level = state({(5, 4): "O.", (5, 6): "d8"}, rules={
                    "explosion_destructible": types, "explosion_diamonds": diamonds})
                level.pending_explosions[g.cell_at(5, 5)] = 1
                g.resolve_explosions(level)
                north, south = g.cell_at(5, 4), g.cell_at(5, 6)
                drop = g.DIAMOND if diamonds else g.EMPTY
                self.assertEqual(level.objects[north], drop if "BOULDER" in types else g.BOULDER)
                self.assertEqual(level.terrain[south], g.FLOOR if "DIRT" in types else g.DIRT)
                self.assertEqual(level.objects[south], drop if "DIRT" in types else g.EMPTY)

    def test_protected_layers_actors_pads_and_spears_never_receive_drops(self):
        for token in ("#0", "F0", "W0", "K.", "D.", "E.", "S.", "Xe", "RE", "T0", "P."):
            cells = {(5, 5): token}
            if token == "E.":
                cells[(15, 11)] = ".."
            if token == "P.":
                cells[(0, 0)] = ".."
            if token == "T0":
                cells[(8, 8)] = "T0"
            level = state(cells, rules={"explosion_hurts_player": False})
            before = (bytes(level.terrain), bytes(level.objects), list(level.actor_at))
            level.pending_explosions[g.cell_at(5, 5)] = 1
            g.resolve_explosions(level)
            self.assertEqual((bytes(level.terrain), bytes(level.objects), level.actor_at), before, token)
            self.assertTrue(all(a.alive for a in level.actors))
        level = state({(8, 5): "RW"})
        trap = actor_of(level, g.EMITTER)
        level.spear_at[g.cell_at(5, 5)] = trap.id
        level.pending_explosions[g.cell_at(5, 5)] = 1
        g.resolve_explosions(level)
        self.assertEqual(level.spear_at[g.cell_at(5, 5)], trap.id)
        self.assertEqual(level.objects[g.cell_at(5, 5)], g.EMPTY)

    def test_overlapping_blasts_deduplicate_and_animation_has_no_collision(self):
        level = state({(5, 5): "O."})
        level.pending_explosions[g.cell_at(4, 5)] = 1
        level.pending_explosions[g.cell_at(6, 5)] = 1
        g.resolve_explosions(level)
        self.assertEqual(sum(obj == g.DIAMOND for obj in level.objects), 3)
        self.assertEqual(sum(level.blast_cells), 9)
        self.assertEqual(level.score, 0)
        # Walk into the still-visible blast and collect exactly one diamond.
        g.place_actor(level, level.player, g.cell_at(5, 4))
        g.step(level, g.SOUTH)
        self.assertEqual((level.status, level.score), (g.PLAYING, 100))
        advance(level, 180)
        self.assertFalse(any(level.blast_until))
        self.assertEqual((level.status, level.score), (g.PLAYING, 100))

    def test_blast_damage_toggle_and_death_beats_exit_after_committed_environment(self):
        for hurts in (False, True):
            level = fixture("Exit blast")
            level.definition["rules"]["explosion_hurts_player"] = hurts
            g.step(level, g.EAST)
            self.assertEqual(level.status, g.DEAD if hurts else g.COMPLETED)
            self.assertEqual(level.step_events, g.DIED if hurts else g.FINISHED)
            self.assertFalse(actor_of(level, g.SPIDER).alive)
            self.assertEqual(level.objects[g.cell_at(5, 5)], g.DIAMOND)
            before = (level.elapsed_ms, bytes(level.objects), list(level.blast_until))
            g.step(level, g.WEST)
            self.assertEqual((level.elapsed_ms, bytes(level.objects), level.blast_until), before)
            self.assertEqual(level.step_events, 0)

    def test_snake_death_on_exit_still_finishes_the_committed_explosion_batch(self):
        level = state({(0, 0): "..", (15, 11): "..", (3, 5): "P.", (4, 5): "E.", (7, 5): "S.",
                       (10, 8): "Xe", (9, 8): "d0", (11, 8): "O.", (10, 7): "#0", (10, 9): "#0"})
        g.step(level, g.EAST)
        self.assertEqual((level.player.cell, level.status, level.step_events), (g.cell_at(4, 5), g.DEAD, g.DIED))
        self.assertFalse(actor_of(level, g.SPIDER).alive)
        self.assertEqual(sum(obj == g.DIAMOND for obj in level.objects), 3)
        self.assertEqual(level.terrain[g.cell_at(9, 8)], g.FLOOR)

    def test_simultaneously_due_spear_kills_player_on_active_exit(self):
        level = state({(0, 0): "..", (15, 11): "..", (1, 5): "RE", (3, 5): "P.", (4, 5): "E."})
        trap = actor_of(level, g.EMITTER)
        trap.trap_state, trap.next_due_ms, trap.tip = g.EXTENDING, 10, g.cell_at(3, 5)
        level.spear_at[g.cell_at(2, 5)] = level.spear_at[trap.tip] = trap.id
        g.step(level, g.EAST)
        self.assertEqual((level.status, level.step_events, trap.tip), (g.DEAD, g.DIED, level.definition["exit"]))

    def test_blast_clear_activates_trap_next_quantum_not_retroactively(self):
        level = fixture("Blast reveals trap")
        trap = actor_of(level, g.EMITTER)
        g.step(level)
        self.assertEqual((trap.trap_state, level.objects[g.cell_at(5, 5)]), (g.IDLE, g.EMPTY))
        g.step(level)
        self.assertEqual((trap.trap_state, trap.next_due_ms, trap.tip), (g.EXTENDING, 60, trap.cell))
        advance(level, 40)
        self.assertEqual(trap.tip, g.cell_at(3, 5))

    def test_growing_spear_can_trap_spider_on_following_quantum(self):
        level = state({(5, 5): "Xe", (4, 5): "#0", (6, 5): "#0", (5, 6): "#0", (4, 4): "RE"})
        trap, spider = actor_of(level, g.EMITTER), actor_of(level, g.SPIDER)
        trap.trap_state, trap.next_due_ms = g.EXTENDING, 10
        g.step(level)
        self.assertTrue(spider.alive)  # Trapped snapshot preceded extension.
        self.assertEqual(trap.tip, g.cell_at(5, 4))
        g.step(level)
        self.assertFalse(spider.alive)
        self.assertEqual(level.spear_at[g.cell_at(5, 4)], trap.id)

    def test_pause_freezes_every_hazard_deadline_and_restart_restores_all_layers(self):
        level = fixture("Blast reveals trap")
        definition = copy.deepcopy(level.definition)
        advance(level, 60)
        self.assertTrue(any(level.blast_until) and any(i >= 0 for i in level.spear_at))
        level.paused = True
        before = (level.elapsed_ms, [(a.cell, a.tip, a.next_due_ms) for a in level.actors], list(level.blast_until))
        advance(level, 2000, g.SOUTH)
        self.assertEqual((level.elapsed_ms, [(a.cell, a.tip, a.next_due_ms) for a in level.actors], level.blast_until), before)
        fresh = g.create_state(level.definition)
        self.assertEqual(level.definition, definition)
        self.assertEqual((fresh.elapsed_ms, fresh.score, fresh.status), (0, 0, g.PLAYING))
        self.assertTrue(all(a.alive and a.tip == a.cell and a.trap_state == g.IDLE for a in fresh.actors))
        self.assertFalse(any(fresh.pending_explosions) or any(fresh.blast_until) or any(fresh.blast_cells))
        self.assertEqual(fresh.spear_at, [-1] * 192)
        self.assertEqual(bytes(fresh.objects), bytes(definition["objects"]))

if __name__ == "__main__":
    unittest.main()
