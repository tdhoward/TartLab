"""Phase 3 interaction outcomes through the maintained, editable engine."""

import copy
import unittest

from tests.grid_puzzle_support import ENGINE as g, room
from tests.test_grid_puzzle_engine import state, advance


def actor_of(level, kind):
    return next(actor for actor in level.actors if actor.kind == kind)


class TerrainTests(unittest.TestCase):
    def test_every_dirt_and_false_wall_variant_opens_on_entry_and_restarts(self):
        for family in ("d", "F"):
            for variant in range(10):
                level = state({(1, 0): family + str(variant)})
                definition = copy.deepcopy(level.definition)
                g.step(level, g.EAST)
                self.assertEqual((level.player.cell, level.terrain[1], level.variants[1]), (1, g.FLOOR, 0))
                self.assertTrue(level.events[1] & g.TERRAIN_CHANGED)
                advance(level, 110, g.WEST)
                self.assertEqual(level.terrain[1], g.FLOOR)
                self.assertEqual(level.definition, definition)
                fresh = g.create_state(definition)
                self.assertEqual((fresh.terrain[1], fresh.variants[1]),
                                 (g.DIRT if family == "d" else g.FALSE_WALL, variant))

    def test_failed_push_does_not_clear_terrain_or_trigger_message(self):
        for token in ("d3", "F7"):
            level = state({(1, 0): "O.", (2, 0): token},
                          messages=[{"loc_x": 2, "loc_y": 0, "text": "Hidden hint"}])
            original = bytes(level.terrain)
            g.step(level, g.EAST)
            self.assertEqual(bytes(level.terrain), original)
            self.assertFalse(any(level.message_seen))
            self.assertEqual(level.player.cell, 0)


class TeleporterTests(unittest.TestCase):
    def test_bidirectional_single_hop_preserves_heading_and_deadline(self):
        level = state({(1, 0): "T4", (8, 4): "T4"})
        g.step(level, g.EAST)
        self.assertEqual((level.player.cell, level.player.heading, level.player.next_due_ms), (72, g.EAST, 120))
        self.assertTrue(level.events[1] & g.TELEPORTED)
        self.assertTrue(level.events[72] & g.TELEPORTED)
        advance(level, 500)
        self.assertEqual(level.player.cell, 72)
        advance(level, 10, g.EAST)
        advance(level, 110, g.WEST)
        self.assertEqual((level.player.cell, level.player.heading), (1, g.WEST))
        self.assertEqual(sum(a != -1 for a in level.actor_at), 1)

    def test_adjacent_twins_do_not_loop_or_retry_after_a_failed_move(self):
        level = state({(1, 0): "T0", (2, 0): "T0", (3, 0): "#0"})
        advance(level, 1000, g.EAST)
        self.assertEqual(level.player.cell, 2)
        self.assertEqual(level.status, g.PLAYING)

    def test_stopped_spear_blocks_arrival_until_leave_and_reenter(self):
        level = state({(1, 0): "T0", (8, 4): "T0", (5, 5): "RE"})
        emitter = actor_of(level, g.EMITTER)
        emitter.trap_state = g.STOPPED
        level.spear_at[72] = emitter.id
        g.step(level, g.EAST)
        self.assertEqual(level.player.cell, 1)
        self.assertFalse(level.step_events & g.DIED)
        level.spear_at[72] = -1
        advance(level, 500)
        self.assertEqual(level.player.cell, 1)
        advance(level, 10, g.WEST)
        advance(level, 110, g.EAST)
        self.assertEqual(level.player.cell, 72)

    def test_player_arrival_contacts_snake_spider_and_growing_spear(self):
        for token, kind in (("S.", g.SNAKE), ("Xn", g.SPIDER), ("RE", g.EMITTER)):
            level = state({(1, 0): "T0", (8, 4): "T0", (10, 5): token})
            enemy = actor_of(level, kind)
            if kind == g.EMITTER:
                enemy.trap_state = g.EXTENDING
                level.spear_at[72] = enemy.id
            else:
                g.place_actor(level, enemy, 72)
            g.step(level, g.EAST)
            self.assertEqual((level.player.cell, level.status, level.player.alive), (72, g.DEAD, False))
            self.assertTrue(level.step_events & g.DIED)
            elapsed = level.elapsed_ms
            g.step(level, g.EAST)
            self.assertEqual((level.step_events, level.elapsed_ms), (0, elapsed))

    def test_contact_at_source_pad_cannot_escape_by_teleporting(self):
        level = state({(1, 0): "T0", (8, 4): "T0", (10, 5): "Xe"})
        g.place_actor(level, actor_of(level, g.SPIDER), 1)
        g.step(level, g.EAST)
        self.assertEqual((level.player.cell, level.status), (1, g.DEAD))

    def test_arrival_snake_ray_is_immediate_and_cover_precedes_player(self):
        for cover in (None, "#0", "F0", "d0", "K.", "D.", "O.", "RE", "Xe"):
            cells = {(1, 0): "T0", (8, 4): "T0", (10, 4): "S."}
            if cover:
                cells[(9, 4)] = cover
            level = state(cells)
            g.step(level, g.EAST)
            self.assertEqual(level.status, g.PLAYING if cover else g.DEAD)

    def test_spider_preview_and_commit_agree_without_mutating_direction_or_timer(self):
        for blocked in (False, True):
            level = state({(1, 0): "T0", (8, 4): "T0", (4, 4): "XE", (12, 5): "Xn"})
            spider = actor_of(level, g.SPIDER)
            if blocked:
                other = [a for a in level.actors if a.kind == g.SPIDER and a != spider][0]
                g.place_actor(level, other, 72)
            before = (list(level.actor_at), spider.cell, spider.heading, spider.next_due_ms)
            preview = g.teleport_destination(level, spider, 1)
            self.assertEqual((level.actor_at, spider.cell, spider.heading, spider.next_due_ms), before)
            g.place_actor(level, spider, 1)
            g.teleport_actor(level, spider)
            self.assertEqual(spider.cell, preview)
            self.assertEqual((spider.heading, spider.next_due_ms), before[2:])
            self.assertEqual(preview, 1 if blocked else 72)

    def test_spider_arrival_on_player_is_lethal_but_other_enemies_block(self):
        level = state({(1, 0): "T0", (8, 4): "T0", (4, 4): "Xe"})
        spider = actor_of(level, g.SPIDER)
        g.place_actor(level, level.player, 72)
        g.place_actor(level, spider, 1)
        self.assertTrue(g.teleport_actor(level, spider))
        self.assertEqual((spider.cell, level.status), (72, g.DEAD))

    def test_spider_can_return_to_own_vacated_cell_and_never_land_on_spear(self):
        level = state({(1, 0): "T0", (8, 4): "T0", (4, 4): "Xe", (12, 5): "RE"})
        spider, emitter = actor_of(level, g.SPIDER), actor_of(level, g.EMITTER)
        g.place_actor(level, spider, 72)
        self.assertEqual(g.teleport_destination(level, spider, 1), 72)
        for mode in (g.EXTENDING, g.STOPPED):
            level.spear_at[72], emitter.trap_state = emitter.id, mode
            self.assertEqual(g.teleport_destination(level, spider, 1), 1)
        self.assertEqual(g.teleport_destination(level, spider, -1), -1)


class MessageTests(unittest.TestCase):
    def test_start_message_freezes_simulation_and_restarts(self):
        level = state(messages=[{"loc_x": 0, "loc_y": 0, "text": "Welcome"}])
        advance(level, 1000, g.EAST)
        self.assertEqual((level.elapsed_ms, level.bonus, level.player.cell), (0, 500, 0))
        self.assertTrue(g.dismiss_message(level))
        g.step(level, g.EAST)
        self.assertEqual(level.player.cell, 1)
        self.assertFalse(g.dismiss_message(level))
        fresh = g.create_state(level.definition)
        self.assertEqual((fresh.active_message, fresh.paused), (0, True))

    def test_entry_once_and_both_pad_messages_queued_in_travel_order(self):
        level = state({(1, 0): "T0", (8, 4): "T0"}, messages=[
            {"loc_x": 8, "loc_y": 4, "text": "Arrival"},
            {"loc_x": 1, "loc_y": 0, "text": "Departure"}])
        g.step(level, g.EAST)
        self.assertEqual((level.active_message, level.pending_messages), (1, [0]))
        advance(level, 1000, g.EAST)
        self.assertEqual((level.elapsed_ms, level.player.cell), (10, 72))
        g.dismiss_message(level)
        self.assertEqual((level.active_message, level.paused), (0, True))
        g.dismiss_message(level)
        advance(level, 110, g.EAST)
        advance(level, 110, g.WEST)
        self.assertEqual((level.player.cell, level.active_message, level.paused), (1, -1, False))

    def test_message_cannot_protect_player_from_arrival_ray(self):
        level = state({(1, 0): "T0", (8, 4): "T0", (10, 4): "S."},
                      messages=[{"loc_x": 8, "loc_y": 4, "text": "Too late"}])
        g.step(level, g.EAST)
        self.assertEqual((level.status, level.paused, level.active_message), (g.DEAD, False, -1))

    def test_long_messages_show_every_word_before_resuming(self):
        text = " ".join("word%s" % i for i in range(500)) + " " + "z" * 90
        session = g.Session({"levels": [g.validate_level(room(messages=[
            {"loc_x": 0, "loc_y": 0, "text": text}]))]})
        for dimensions in ((480, 222), (512, 520), (256, 328)):
            session.restart()
            layout = g.choose_layout(*dimensions)
            lines, count = g.message_content(session.state, layout)
            self.assertEqual("".join(lines).replace(" ", ""), text.replace(" ", ""))
            pages = (len(lines) + count - 1) // count
            for page in range(pages):
                self.assertTrue(session.state.paused)
                self.assertEqual(session.message_page, page)
                g.acknowledge_message(session, layout)
            self.assertFalse(session.state.paused)


if __name__ == "__main__":
    unittest.main()
