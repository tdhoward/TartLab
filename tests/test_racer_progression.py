import unittest

from tests.test_racer_entities import RACER
from tests.test_racer_sprites import PixelCanvas, load_art, renderer


class RacerProgressionTests(unittest.TestCase):
    def test_intro_has_only_coin_and_distant_hazard(self):
        game = RACER.create_race(320, 480)
        self.assertEqual(len(game.entities), 2)
        self.assertEqual({e.kind.name for e in game.entities}, {"cow", "coin"})
        coin = next(e for e in game.entities if e.kind.name == "coin")
        self.assertEqual(coin.x, game.player_x)
        self.assertLess(coin.y, game.player_y - 70)
        self.assertIsNone(game.spawn_entity())

    def test_long_race_caps_population_and_unlocks_animals_in_order(self):
        game = RACER.create_race(320, 480)
        game._choice = lambda values: values[-1]
        game._randint = lambda low, high: (low + high) // 2
        game.player_x = -1000  # Survive without influencing the spawner.
        seen = {}
        populations = {}
        for unused in range(2600):
            game.begin_frame()
            game.step(50)
            self.assertLessEqual(len(game.entities), game.max_entities)
            self.assertLessEqual(len(game.entities), RACER.MAX_ROAD_ENTITIES)
            populations[game.level] = max(populations.get(game.level, 0), len(game.entities))
            for entity in game.entities:
                if isinstance(entity, RACER.CrossingAnimal):
                    seen.setdefault(entity.kind.name, game.elapsed_ms)
            for name in ("capybara", "chicken"):
                self.assertLessEqual(sum(e.kind.name == name for e in game.entities), 1)
        self.assertGreaterEqual(seen["capybara"], RACER.RODENT_START_MS)
        self.assertLess(seen["capybara"], RACER.RODENT_START_MS + 6000)
        self.assertGreaterEqual(seen["chicken"], RACER.CHICKEN_START_MS)
        self.assertLess(seen["chicken"], RACER.CHICKEN_START_MS + 6000)
        self.assertEqual(populations[0], 2)
        self.assertEqual(populations[4], RACER.MAX_ROAD_ENTITIES)
        game.crashed = True
        elapsed = game.elapsed_ms
        game.step(5000)
        self.assertEqual(game.elapsed_ms, elapsed)
        fresh = RACER.create_race(320, 480)
        self.assertEqual((fresh.level, fresh.elapsed_ms, fresh.max_entities), (0, 0, 2))

    def test_capybara_crosses_once_at_constant_speed_in_both_directions(self):
        game = RACER.create_race(320, 480)
        for direction in (-1, 1):
            start = game.road_left + 17 if direction > 0 else game.road_right - 18
            animal = RACER.CrossingAnimal(game.animal_kinds["capybara"],
                                           start, 68, direction)
            previous = animal.x_milli
            for unused in range(100):
                animal.advance(50, 4, game.road_left, game.road_right)
                self.assertEqual(animal.x_milli - previous, direction * RACER.RODENT_SPEED * 50)
                previous = animal.x_milli
                if not animal.active:
                    break
            self.assertFalse(animal.active)
            self.assertLess(animal.y, game.track_bottom)

    def test_chicken_varies_speed_and_direction_without_frame_rate_randomness(self):
        game = RACER.create_race(320, 480)
        decisions = iter((0, 4, 1, 0, 3, 2, 0, 4))
        def random_value(low, high):
            return next(decisions) if (low, high) == (0, 4) else low
        chicken = RACER.CrossingAnimal(game.animal_kinds["chicken"], 140, 68, 1,
                                      random_value)
        velocities = set()
        for unused in range(24):
            chicken.advance(50, 4, game.road_left, game.road_right)
            velocities.add(chicken.horizontal_velocity)
        self.assertTrue(any(v < 0 for v in velocities))
        self.assertTrue(any(v > 0 for v in velocities))
        self.assertIn(0, velocities)
        self.assertTrue(chicken.active)
        for elapsed in (200, 50):
            bird = RACER.CrossingAnimal(game.animal_kinds["chicken"], 140, 68, 1,
                                       lambda low, high: high)
            for unused in range(1000 // elapsed):
                bird.advance(elapsed, 0, game.road_left, game.road_right)
            if elapsed == 200:
                expected = bird.x_milli
            else:
                self.assertEqual(bird.x_milli, expected)

    def test_capybara_paces_vary_and_survive_entire_player_pass(self):
        for width, height in ((240, 320), (320, 480), (480, 800)):
            for direction in (-1, 1):
                for road_speed in (64, 80, 96, 112, 128):
                    paces = []
                    for fraction in (40, 55, 70):
                        game = RACER.ProgressiveRace(width, height)
                        game.road = RACER.RoadState(((0, road_speed),), 4, 48)
                        game.elapsed_ms = RACER.RODENT_START_MS
                        game._choice = lambda values: direction
                        game._randint = lambda low, high: fraction
                        animal = game.spawn_entity()
                        self.assertEqual(animal.kind.name, "capybara")
                        speed = animal.horizontal_velocity
                        paces.append(abs(speed))
                        pass_y = game.player_y + game.player_radius + animal.kind.collision.radius
                        while animal.y <= pass_y:
                            animal.advance(50, game.road.advance(50), game.road_left, game.road_right)
                            self.assertTrue(animal.active, (width, height, road_speed, fraction))
                            self.assertEqual(animal.horizontal_velocity, speed)
                        self.assertGreater(animal.x, game.road_left + animal.kind.visual_radius)
                        self.assertLess(animal.x, game.road_right - animal.kind.visual_radius)
                    self.assertLess(paces[0], paces[1])
                    self.assertLess(paces[1], paces[2])

    def test_chicken_stays_on_road_through_pass_then_is_culled(self):
        for choose in (lambda low, high: low, lambda low, high: high):
            game = RACER.create_race(320, 480)
            game.entities.clear()
            game.next_spawn_distance = 100000
            game.road = RACER.RoadState(((0, 128),), 4, 48)
            animal = game.add_entity(RACER.CrossingAnimal(
                game.animal_kinds["chicken"], game.road_right - 18, 68, -1, choose))
            player_y = game.player_y
            game.player_x = -1000
            passed = False
            for unused in range(120):
                game.begin_frame()
                game.step(50)
                if not animal.active:
                    break
                self.assertGreaterEqual(animal.x, game.road_left + 16)
                self.assertLessEqual(animal.x, game.road_right - 17)
                if animal.y >= player_y + 24:
                    passed = True
            self.assertTrue(passed)
            self.assertFalse(animal.active)
            self.assertNotIn(animal, game.entities)

    def test_road_accelerates_through_five_bounded_speeds(self):
        road = RACER.RoadState()
        speeds = {road.speed_per_second}
        previous = road.speed_per_second
        for unused in range(2500):
            delta = road.advance(100)
            speeds.add(road.speed_per_second)
            self.assertGreaterEqual(road.speed_per_second, previous)
            self.assertLessEqual(delta, RACER.maximum_scroll_delta())
            previous = road.speed_per_second
        self.assertEqual(speeds, {64, 80, 96, 112, 128})

    def test_crossing_sprites_match_full_redraw_in_both_animators(self):
        art = load_art()
        for scanout in (False, True):
            game = RACER.create_race(240, 320)
            game.entities.clear()
            game.next_spawn_distance = 10000
            game.player_x = 170
            game.add_entity(RACER.CrossingAnimal(game.animal_kinds["capybara"], 70, 55, 1))
            game.add_entity(RACER.CrossingAnimal(game.animal_kinds["chicken"], 140, 150, -1,
                                                 lambda low, high: low))
            canvas = PixelCanvas(240, 320)
            road_renderer = renderer(canvas, game, art)
            road_renderer.rebuild((0, 48, 240, 272))
            if scanout:
                bands = RACER.RoadBandCache(canvas, road_renderer, 4, 12, PixelCanvas)
                animator = RACER.ScanoutAnimator(game, road_renderer, bands)
            else:
                animator = RACER.DirtyRegionAnimator(game, road_renderer)
            for frame in range(32):
                animator.begin_frame()
                game.begin_frame()
                animator.record_step(game.step(50))
                animator.present()
                reference = PixelCanvas(240, 320)
                renderer(reference, game, art).rebuild((0, 48, 240, 272))
                self.assertEqual(canvas.pixels, reference.pixels, (scanout, frame))

    def test_turn_in_place_redraws_and_pause_keeps_facing(self):
        art = load_art()
        for scanout in (False, True):
            game = RACER.create_race(240, 320)
            game.entities.clear()
            bird = game.add_entity(RACER.CrossingAnimal(
                game.animal_kinds["chicken"], 100, 120, 1))
            canvas = PixelCanvas(240, 320)
            road_renderer = renderer(canvas, game, art)
            road_renderer.rebuild((0, 48, 240, 272))
            if scanout:
                bands = RACER.RoadBandCache(canvas, road_renderer, 4, 16, PixelCanvas)
                animator = RACER.ScanoutAnimator(game, road_renderer, bands)
            else:
                animator = RACER.DirtyRegionAnimator(game, road_renderer)
            animator.begin_frame()
            game.begin_frame()
            bird.direction = -1
            bird.horizontal_velocity = 0
            bird.decision_ms = 500
            animator.record_step(0)
            animator.present()
            reference = PixelCanvas(240, 320)
            renderer(reference, game, art).rebuild((0, 48, 240, 272))
            self.assertEqual(canvas.pixels, reference.pixels)
            bird.advance(50, 0, game.road_left, game.road_right)
            self.assertEqual(bird.direction, -1)


if __name__ == "__main__":
    unittest.main()
