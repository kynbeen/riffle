"""다시 돌려 볼 사례 남기기(riffle/cases.py) — 명세 2026-09-25-01 단위 4b."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from riffle.cases import build_case, load_cases, record_case, score_case
from riffle.page_match import MatchResult, PageFingerprint, PagePair
from riffle.reorder import pair_reordered


def page(*pattern: float) -> PageFingerprint:
    return PageFingerprint(index=0, cells=tuple(pattern) * (16 // len(pattern)), aspect=1.0)


A, B, C = page(1, -1), page(1, 1, -1, -1), page(1, -1, -1, 1)


def inspection(**extra):
    base = dict(
        source_name="병리학_1주차_황희성.sdocx", target_name="병리학 1주차 필기.pdf",
        prints=([A, B, C], [A, B, C]),
        match=MatchResult((PagePair(0, 0, 0.0), PagePair(1, 1, 0.0), PagePair(2, 2, 0.0))),
        moved_sources=(), pair_candidates=(),
    )
    base.update(extra)
    return SimpleNamespace(**base)


def rows(*pairs, excluded=()):
    return [{"source_index": s, "target_index": t, "confirmed": True, "excluded": s in excluded} for s, t in pairs]


class CaseTests(unittest.TestCase):
    def test_a_case_keeps_prints_and_pairs_but_no_file_names(self):
        with tempfile.TemporaryDirectory() as folder:
            path = record_case(inspection(), rows((0, 0), (1, 1), (2, 2)), ".sdocx", Path(folder))
            text = path.read_text(encoding="utf-8")
        self.assertNotIn("황희성", text)
        self.assertNotIn("필기.pdf", text)
        case = json.loads(text)
        self.assertEqual(len(case["source"]["cells"]), 3)
        self.assertEqual(len(case["source"]["cells"][0]), 16)
        self.assertEqual(case["machine"], [[0, 0], [1, 1], [2, 2]])
        self.assertEqual(case["final"][0], {"source": 0, "target": 0, "excluded": False, "confirmed": True})

    def test_recording_never_breaks_saving(self):
        with tempfile.TemporaryDirectory() as folder:
            blocker = Path(folder) / "file"
            blocker.write_text("x")
            with self.assertLogs("riffle.cases", level="ERROR"):
                self.assertIsNone(record_case(inspection(), rows((0, 0)), ".sdocx", blocker))   # 폴더 자리에 파일
        self.assertIsNone(record_case(inspection(prints=()), rows((0, 0)), ".sdocx"))         # 지문 없는 옛 분석

    def test_a_case_replays_against_what_the_person_saved(self):
        agreed = build_case(inspection(), rows((0, 0), (1, 1), (2, 2)), ".sdocx")
        self.assertEqual(score_case(agreed, pair_reordered), {"맞음": 3})
        # 사람이 옛 1쪽 필기를 새 2쪽에 얹고 옛 2쪽은 옛 쪽째 남겼다 — 지금 판정은 자신 있게 다르게 낸다.
        fixed = build_case(inspection(), rows((0, 0), (None, 1), (1, 2), (2, None)), ".sdocx")
        self.assertEqual(score_case(fixed, pair_reordered), {"맞음": 1, "조용히 틀림": 2})

    def test_excluded_pages_are_not_scored(self):
        case = build_case(inspection(), rows((0, 0), (1, 1), (2, 2), excluded={2}), ".sdocx")
        self.assertEqual(score_case(case, pair_reordered), {"맞음": 2})

    def test_cases_are_read_back_from_the_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            record_case(inspection(), rows((0, 0), (1, 1), (2, 2)), ".sdocx", Path(folder))
            (Path(folder) / "broken.json").write_text("{", encoding="utf-8")
            self.assertEqual(len(load_cases(Path(folder))), 1)


if __name__ == "__main__":
    unittest.main()
