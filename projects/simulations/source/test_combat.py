import unittest
from combat_roller import hits, hit_chance, wound_needed


class CombatRulesTests(unittest.TestCase):
    def test_equal_stats_symmetry(self):
        self.assertEqual(hit_chance(3, 3, True), .525)
        self.assertEqual(hit_chance(3, 3, False), .475)

    def test_extreme_advantages(self):
        self.assertEqual(hit_chance(20, 0), 1)
        self.assertEqual(hit_chance(0, 20), 0)

    def test_tie_setting_changes_only_equal_totals(self):
        for a in range(1, 21):
            for d in range(1, 21):
                self.assertEqual(hits(a, d, 4, 2, True) != hits(a, d, 4, 2, False), a + 4 == d + 2)

    def test_wound_boundaries(self):
        self.assertEqual([wound_needed(s, 4) for s in range(1, 9)], [6, 5, 5, 4, 3, 3, 2, 2])


if __name__ == '__main__':
    unittest.main()
