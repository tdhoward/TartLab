import importlib.util
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
def load_module(name, path):
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


motion = load_module("racer_test_motion", ROOT / "src/lib/tartlabutils/motion.py")
timing = load_module("racer_test_timing", ROOT / "src/lib/tartlabutils/timing.py")
damage = load_module("racer_test_damage", ROOT / "src/lib/tartlabutils/damage.py")
package = types.ModuleType("tartlabutils")
package.__path__ = []

module_names = (
    "tartlabutils", "tartlabutils.damage", "tartlabutils.motion",
    "tartlabutils.timing")
previous_modules = {name: sys.modules.get(name) for name in module_names}
try:
    sys.modules["tartlabutils"] = package
    sys.modules["tartlabutils.damage"] = damage
    sys.modules["tartlabutils.motion"] = motion
    sys.modules["tartlabutils.timing"] = timing
    RACER = load_module("racer_help", ROOT / "src/files/help/racer.py")
finally:
    for name, previous in previous_modules.items():
        if previous is None:
            del sys.modules[name]
        else:
            sys.modules[name] = previous


def kind(name="plain", radius=2, handler=None):
    return RACER.EntityKind(name, 123, radius, radius, handler)


def state(entity_kinds=(), speed=100, spawn_gap=1000,
          randint_source=lambda low, high: low,
          choice_source=lambda values: values[0]):
    road = RACER.RoadState(((0, speed),), 1, 48)
    return RACER.GameState(
        road, 0, 100, 0, 100, 50, 80, 3,
        entity_kinds, spawn_gap, randint_source, choice_source)


class RacerEntityTests(unittest.TestCase):
    def test_road_relative_and_screen_relative_motion_are_independent(self):
        game = state()
        moving = game.add_entity(RACER.Entity(
            kind(), 20, 20, horizontal_velocity=20,
            road_relative=True, boundary_policy=None))
        fixed = game.add_entity(RACER.Entity(
            kind(), 40, 20, horizontal_velocity=-20,
            road_relative=False, boundary_policy=None))

        game.step(50)

        self.assertEqual((moving.x, moving.y), (21, 25))
        self.assertEqual((fixed.x, fixed.y), (39, 20))
        self.assertEqual(moving.previous_bounds, (18, 18, 5, 5))
        self.assertEqual(moving.current_bounds, (19, 23, 5, 5))

    def test_bounce_policy_reflects_position_and_velocity(self):
        entity = RACER.Entity(
            kind(radius=2), 96, 20, horizontal_velocity=100,
            road_relative=False,
            boundary_policy=RACER.bounce_at_road_edge)
        game = state()
        game.add_entity(entity)

        game.step(50)

        self.assertEqual(entity.x, 93)
        self.assertEqual(entity.horizontal_velocity, -100)

    def test_wrap_policy_moves_entity_to_opposite_edge(self):
        entity = RACER.Entity(
            kind(radius=2), 96, 20, horizontal_velocity=100,
            road_relative=False,
            boundary_policy=RACER.wrap_at_road_edge)
        game = state()
        game.add_entity(entity)

        game.step(50)

        self.assertEqual(entity.x, 6)
        self.assertEqual(entity.horizontal_velocity, 100)

    def test_deactivate_policy_and_compaction_preserve_list_identity(self):
        entity = RACER.Entity(
            kind(radius=2), 96, 20, horizontal_velocity=100,
            road_relative=False,
            boundary_policy=RACER.deactivate_at_road_edge)
        game = state()
        entities = game.entities
        game.add_entity(entity)

        game.step(50)

        self.assertIs(game.entities, entities)
        self.assertEqual(game.entities, [])
        self.assertEqual(game.removed_entities, [entity])

    def test_collectible_contact_scores_and_fires_once(self):
        coin_kind = kind("coin", 2, RACER.collect_on_contact)
        game = state()
        coin = game.add_entity(RACER.Entity(
            coin_kind, 50, 80, road_relative=False))

        game.begin_frame()
        game.step(0)
        game.step(0)

        self.assertEqual(game.score, 1)
        self.assertFalse(coin.active)
        self.assertEqual(game.removed_entities, [coin])
        self.assertEqual(len(game.interactions), 1)
        self.assertEqual(game.interactions[0].event_type, "collectible")
        self.assertIs(game.interactions[0].entity, coin)

    def test_hazard_contact_crashes_and_fires_once_while_active(self):
        hazard_kind = kind("hazard", 2, RACER.crash_on_contact)
        game = state()
        hazard = game.add_entity(RACER.Entity(
            hazard_kind, 50, 80, road_relative=False))

        game.begin_frame()
        game.step(0)
        game.step(0)

        self.assertTrue(game.crashed)
        self.assertTrue(hazard.active)
        self.assertEqual(
            [event.event_type for event in game.interactions], ["hazard"])

    def test_offscreen_entity_is_removed(self):
        game = state()
        entity = game.add_entity(RACER.Entity(kind(radius=1), 50, 99))

        game.step(50)

        self.assertFalse(entity.active)
        self.assertEqual(game.entities, [])

    def test_distance_spawn_uses_injected_sources_and_starts_unmoved(self):
        coin_kind = kind("coin", 3, RACER.collect_on_contact)
        calls = []

        def choose(values):
            calls.append(tuple(values))
            return values[0]

        game = state(
            (coin_kind,), speed=100, spawn_gap=5,
            randint_source=lambda low, high: high,
            choice_source=choose)

        delta = game.step(50)

        self.assertEqual(delta, 5)
        self.assertEqual(len(game.entities), 1)
        spawned = game.entities[0]
        self.assertEqual(spawned.y, game.track_top + 3)
        self.assertEqual(spawned.x, game.road_right - 3 - 4)
        self.assertEqual(spawned.previous_bounds, spawned.current_bounds)
        self.assertEqual(game.spawned_entities, [spawned])
        self.assertEqual(calls, [(coin_kind,)])


if __name__ == "__main__":
    unittest.main()
