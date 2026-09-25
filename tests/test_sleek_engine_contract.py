"""Sleek 이 사람 없이 부르는 Riffle 엔진의 입구 — 이것이 사라지면 Sleek 이 조용히 멈춘다.

Sleek 은 Riffle 의 화면이 아니라 **엔진 함수를 직접** 쓴다. Riffle 체크아웃의 venv 파이썬으로
Sleek 의 드라이버(`sleek/pipeline/riffle_merge_driver.py`·`riffle_analysis_driver.py`)를 돌리고,
드라이버가 아래 이름들을 import 한다. 합친 결과의 **바이트가 Riffle 과 같아야** 해시 비교가 성립해서,
Sleek 이 같은 일을 따로 구현하지 않는다.

쓰는 자리(2026-09-24 확인): 자료 재합치기·재현 확인(`import_merge`·`merge_sessions`), 족첵 범위 찾기
(`exam_scope`), 원본 자동 갱신(`auto_refresh`), 필기 쪽 맞추기(`notes_study/alignment`), 원본 기록
(`source_records`). Sleek 은 이 저장소를 `riffle` 명령(PATH)·`C:\\dev\\riffle`·`Riffle.lnk` 로 찾고
`riffle/engine.py` 가 있는지로 확인한다.

**여기를 바꾸려면 Sleek 드라이버를 함께 고친다.** 2026-09-24 이름 변경 때 이 입구가 한 번 끊겼다.
"""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]


class SleekEngineContractTests(unittest.TestCase):
    def test_sleek_finds_the_checkout_by_these_files(self):
        self.assertTrue((ROOT / "riffle" / "engine.py").is_file())
        self.assertTrue((ROOT / "riffle.cmd").is_file())

    def test_merge_driver_entrances_exist_and_behave(self):
        from riffle import __version__
        from riffle.engine import ComposerSession
        from riffle.ranges import parse_page_ranges

        self.assertTrue(__version__)
        self.assertEqual(parse_page_ranges("1-2", 3), [0, 1])
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "a.pdf"
            with pymupdf.open() as document:
                for _ in range(3):
                    document.new_page()
                document.save(source)
            session = ComposerSession()
            try:
                added = session.add_files([str(source)])
                self.assertEqual(added[0]["page_count"], 3)          # 드라이버가 읽는 키
                order = [{"document_id": added[0]["id"], "page_index": index} for index in (0, 2)]
                result = session.build_pdf(order, Path(folder) / "out.pdf")
            finally:
                session.close()
        self.assertEqual(result["page_count"], 2)

    def test_analysis_driver_entrances_exist(self):
        from riffle import pdf
        from riffle.page_match import MatchResult, match_pages

        self.assertTrue(callable(pdf.open))
        self.assertEqual(list(inspect.signature(match_pages).parameters)[:2],
                         ["source_document", "target_document"])
        # 드라이버가 쓰는 결과 모양
        for name in ("as_dict", "source_only", "target_only", "uncertain"):
            self.assertTrue(hasattr(MatchResult, name), name)


if __name__ == "__main__":
    unittest.main()
