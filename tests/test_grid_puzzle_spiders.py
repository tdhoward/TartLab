import unittest

from tests.grid_puzzle_support import ENGINE
from tests.grid_puzzle_spider_checks import CHECKS


class SpiderWallFollowingTests(unittest.TestCase):
    def test_wall_following_scenarios(self):
        for check in CHECKS:
            with self.subTest(scenario=check.__name__):
                check(ENGINE)
