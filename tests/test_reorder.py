"""새 판에서 순서가 바뀐 쪽 다시 짝짓기(riffle/reorder.py)."""
from __future__ import annotations

import unittest

from riffle.page_match import MatchResult, PageFingerprint, PagePair, match_fingerprints
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

    def test_unlike_pages_stay_apart(self):
        # 새 판에서 빠진 쪽(E)과 새로 생긴 쪽(C)은 닮지 않았다 — 그대로 둔다.
        match = MatchResult((PagePair(0, 0, 0.0), PagePair(1, None), PagePair(None, 1)))
        result = pair_reordered(match, [A, E], [A, C])
        self.assertEqual((result.moved, result.candidates, result.match), ((), {}, match))


if __name__ == "__main__":
    unittest.main()
