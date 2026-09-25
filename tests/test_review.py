"""확인할 쪽 고르기(riffle/review.py) — 기계가 자신 없는 쪽만, 이유는 하나씩."""
from __future__ import annotations

import unittest

from riffle.review import review


def slot(source, target, *, distance=0.02, margin=0.9, confirmed=True):
    return {"source_index": source, "target_index": target, "distance": distance,
            "margin": margin, "confirmed": confirmed}


def inspection(slots, *, blank=(), panel=(), doubtful=False, moved=(), candidates=(), closest=()):
    return {
        "closest_targets": [list(pair) for pair in closest],
        "moved_sources": list(moved),
        "pair_candidates": [list(pair) for pair in candidates],
        "plan": {"slots": slots},
        "source_order": [{"source_index": index, "blank": index in blank} for index in range(20)],
        "panel_ink_sources": list(panel),
        "alignment": {"requires_confirmation": doubtful} if doubtful else None,
    }


class ReviewTests(unittest.TestCase):
    def test_confident_pages_are_not_shown(self):
        result = review(inspection([slot(0, 0), slot(1, 1), slot(2, 2)]))
        self.assertEqual(result["items"], [])
        self.assertEqual(result["summary"]["automatic"], 3)
        self.assertEqual(result["summary"]["result_pages"], 3)

    def test_each_doubt_gets_one_reason(self):
        result = review(inspection([
            slot(0, 0),
            slot(1, 1, distance=0.6, confirmed=False),          # 생김새가 다르다
            slot(2, 3, margin=0.01, confirmed=False),           # 똑같은 쪽이 또 있다
            slot(3, None),                                      # 새 PDF 에 없는 옛 쪽 + 필기
            slot(None, 2),                                      # 새로 생긴 쪽 — 부르지 않는다
            slot(4, None),                                      # 필기 없는 옛 쪽 — 묻지 않고 남긴다
        ], blank={4}))
        self.assertEqual([(item["slot"], item["reason"]) for item in result["items"]],
                         [(1, "different"), (2, "duplicate"), (3, "old_only")])
        summary = result["summary"]
        self.assertEqual((summary["matched"], summary["automatic"], summary["new_pages"],
                          summary["kept_old"], summary["kept_blank"]), (3, 1, 1, 2, 1))
        # 합집합 — 새 PDF 에 없는 옛 쪽은 필기가 없어도 결과에 남는다(명세 2026-09-25-01)
        self.assertEqual(summary["result_pages"], 6)
        self.assertEqual(result["blank_sources"], [4])

    def test_reordered_pages_are_counted_not_shown_and_doubtful_ones_carry_a_candidate(self):
        result = review(inspection([
            slot(0, 0), slot(2, 1), slot(1, 2),                 # 옛 1쪽이 순서가 바뀌어 새 3쪽에 짝지어짐
            slot(3, None), slot(None, 3),                       # 닮았지만 애매 — 후보로 함께 보낸다
            slot(4, None),                                      # 닮은 쪽이 없다 — 가장 닮은 쪽만 알린다
        ], moved={1}, candidates={(3, 3)}, closest={(4, 0)}))
        self.assertEqual(result["summary"]["moved"], 1)
        self.assertEqual(result["moved_sources"], [1])
        self.assertEqual(result["summary"]["automatic"], 3)
        self.assertEqual(result["items"], [
            {"slot": 3, "source_index": 3, "target_index": None, "reason": "old_only", "candidate": 3},
            {"slot": 5, "source_index": 4, "target_index": None, "reason": "old_only", "closest": 0},
        ])

    def test_panel_ink_wins_over_other_reasons(self):
        result = review(inspection([slot(0, 0, distance=0.9)], panel={0}))
        self.assertEqual(result["items"][0]["reason"], "panel_ink")

    def test_a_doubtful_alignment_asks_about_every_paired_page(self):
        result = review(inspection([slot(0, 0, confirmed=False), slot(1, 1, confirmed=False),
                                    slot(None, 2)], doubtful=True))
        self.assertEqual([item["reason"] for item in result["items"]], ["alignment", "alignment"])


if __name__ == "__main__":
    unittest.main()
