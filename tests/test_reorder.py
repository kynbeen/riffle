"""새 판에서 순서가 바뀐 쪽 다시 짝짓기(riffle/reorder.py)."""
from __future__ import annotations

import unittest

from riffle.page_match import MatchResult, PageFingerprint, PagePair, distance, match_fingerprints
from riffle.reorder import pair_reordered


def page(index: int, *pattern: float) -> PageFingerprint:
    """16칸짜리 생김새. 같은 무늬면 거리 0."""
    cells = tuple(pattern) * (16 // len(pattern))
    return PageFingerprint(index=index, cells=cells, aspect=1.0)


A, B, C, D, E = (page(0, 1, -1), page(0, 1, 1, -1, -1), page(0, 1, -1, -1, 1),
                 page(0, 1, 1, 1, -1), page(0, -1, -1, -1, 1))


class ReorderTests(unittest.TestCase):
    def test_a_swapped_page_is_paired_where_the_new_edition_put_it(self):
        # 옛: A B C D  →  새: A C D B (B 가 뒤로 갔다). 순서를 지키는 짝짓기는 B 를 짝짓지 못한다.
        old, new = [A, B, C, D], [A, C, D, B]
        match = match_fingerprints(old, new)
        self.assertIn(1, match.source_only)
        result = pair_reordered(match, old, new)
        self.assertEqual(result.moved, (1,))
        self.assertEqual(result.match.source_to_target(), {0: 0, 1: 3, 2: 1, 3: 2})
        self.assertEqual([pair.target_index for pair in result.match.pairs], [0, 1, 2, 3])  # 새 쪽 순서는 그대로
        self.assertTrue(all(pair.confident for pair in result.match.pairs))

    def test_two_equally_close_new_pages_are_left_to_the_person(self):
        # 옛 B 와 똑같은 새 쪽이 둘 — 어느 쪽인지 확신이 없으니 짝짓지 않고 후보만 준다.
        match = MatchResult((PagePair(0, 0, 0.0), PagePair(1, None), PagePair(None, 1), PagePair(None, 2)))
        result = pair_reordered(match, [A, B], [A, B, B])
        self.assertEqual(result.moved, ())
        self.assertEqual(result.match, match)
        self.assertEqual(result.candidates, {1: 1})

    def test_unlike_pages_stay_apart_but_the_closest_page_is_named(self):
        # 새 판에서 빠진 쪽(E)과 새로 생긴 쪽(C)은 닮지 않았다 — 그대로 둔다. `다른 쪽` 띠는 가장 닮은 쪽에서 시작한다.
        match = MatchResult((PagePair(0, 0, 0.0), PagePair(1, None), PagePair(None, 1)))
        result = pair_reordered(match, [A, E], [A, C])
        self.assertEqual((result.moved, result.candidates, result.match), ((), {}, match))
        self.assertEqual(result.closest, {1: 1 if distance(E, C) < distance(E, A) else 0})

    def test_a_doubtful_pair_blocking_the_right_one_is_undone(self):
        # 엔진이 옛 B 를 새 E 에 자신 없이(0.54) 짝지어, 옛 B↔새 B 와 옛 E↔새 E 가 둘 다 짝을 못 지은 모양(실측 1주차(3)).
        match = MatchResult((PagePair(0, 0, 0.0), PagePair(1, 1, 0.54, 0.0), PagePair(2, None), PagePair(None, 2)))
        result = pair_reordered(match, [A, B, E], [A, E, B])
        self.assertEqual(result.moved, (1, 2))
        self.assertEqual(result.match.source_to_target(), {0: 0, 1: 2, 2: 1})
        self.assertEqual([pair.target_index for pair in result.match.pairs], [0, 1, 2])
        self.assertTrue(all(pair.confident for pair in result.match.pairs))

    def test_a_confident_pair_is_never_touched(self):
        match = MatchResult((PagePair(0, 0, 0.0), PagePair(1, 1, 0.1, 0.5), PagePair(2, None)))
        result = pair_reordered(match, [A, B, B], [A, B])
        self.assertEqual(result.match, match)


if __name__ == "__main__":
    unittest.main()
