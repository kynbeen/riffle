"""새 화면의 `다른 쪽`(짝 바꾸기)으로 만든 대응을 저장하면 — 새 쪽 순서는 그대로, 옛 필기는 고른 새 쪽에."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import pymupdf

from riffle.page_plan import PagePlan
from riffle.sdocx_note import read_page_order
from riffle.sdocx_page import read_page
from riffle.sdocx_transfer import inspect_transfer, transfer_handwriting
from tests.test_sdocx_ink import make_stroke_layers
from tests.test_sdocx_rebuild import UUIDS, make_rebuild_source
from tests.test_sdocx_transfer import make_pdf


class ReassignedPlanTests(unittest.TestCase):
    def test_handwriting_lands_on_the_chosen_page_and_new_pages_keep_their_order(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_pdf, target_pdf = root / "old.pdf", root / "new.pdf"
            make_pdf(source_pdf, ["A", "B", "C", "D"])
            make_pdf(target_pdf, ["A", "B", "C", "D"])
            source = root / "old.sdocx"
            make_rebuild_source(source, source_pdf, annotated_layers=make_stroke_layers())  # 옛 3쪽(2)에만 필기
            inspection = inspect_transfer(source, target_pdf)

            # web/src/plan.ts 의 reassign(slots, 2, 3) 결과와 화면의 plan() 이 보내는 것 그대로:
            # 옛 3쪽 → 새 4쪽, 떠난 새 3쪽은 필기 없는 새 쪽, 밀려난 옛 4쪽(필기 없음)은 뺀다.
            payload = [
                {"source_index": 0, "target_index": 0, "confirmed": True, "excluded": False},
                {"source_index": 1, "target_index": 1, "confirmed": True, "excluded": False},
                {"source_index": None, "target_index": 2, "confirmed": True, "excluded": False},
                {"source_index": 2, "target_index": 3, "confirmed": True, "excluded": False},
                {"source_index": 3, "target_index": None, "confirmed": True, "excluded": True},
            ]
            plan = PagePlan.from_payload(4, 4, payload, inspection.match)
            self.assertEqual(plan.unconfirmed, ())
            output = root / "moved.sdocx"
            transfer_handwriting(source, target_pdf, output, plan_override=plan)

            with ZipFile(output) as archive:
                order = read_page_order(archive.read("pageIdInfo.dat"))
                pages = {entry.uuid: read_page(archive.read(f"{entry.uuid}.page")) for entry in order.entries}
                embedded = archive.read("media/0@source.pdf")
            with pymupdf.open(stream=embedded, filetype="pdf") as document:
                labels = [document[index].get_text().strip() for index in range(document.page_count)]
            self.assertEqual(labels, ["A", "B", "C", "D"])                  # 새 쪽 순서 그대로
            self.assertEqual(pages[UUIDS[2]].pdf.page_index, 3)             # 옛 3쪽의 필기는 새 4쪽에
            self.assertNotIn(UUIDS[3], pages)                               # 밀려난 빈 옛 쪽은 빠졌다


if __name__ == "__main__":
    unittest.main()
