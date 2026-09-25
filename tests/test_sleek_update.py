"""Sleek 필기본 → 개정된 Sleek 필기본(명세 2026-09-25-03). 반복 수가 바뀌어도 결과는 새 판 쪽 구조 그대로이고,
손필기는 한 획도 빠지지 않으며, 칸 손필기는 새 쪽의 여백으로 간다.
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

import pymupdf

from riffle.goodnotes_ink import element_boxes, journal_elements
from riffle.ink_layer import GOODNOTES, NOTEWISE, SAMSUNG_NOTES
from riffle.ink_transform import CanvasTransform
from riffle.page_plan import PagePlan
from riffle.review import review
from riffle.sdocx_ink import object_boxes, read_ink_strokes
from riffle.sdocx_note import PageOrder, PageOrderEntry, read_page_order
from riffle.sdocx_page import page_hash, read_page
from riffle.sdocx_transfer import inspect_transfer, preview_transfer, transfer_handwriting
from riffle.sleek_match import spread
from riffle.sleek_notes import is_notes_document, lecture_key, page_layout
from tests.test_page_match import SEEDS, make_document
from tests.test_sdocx_ink import _delta
from tests.test_sdocx_note import make_note
from tests.test_sdocx_page import make_page
from tests.test_sdocx_transfer import SPEN_FOOTER, make_media_info
from tests.test_sleek_notes import PANEL, PANEL_FILL, RULE_INK

CANVAS_WIDTH = 1848


def notes_pdf(slides: Path, output: Path, copies: dict[int, int], texts: dict[tuple[int, int], str] | None = None,
              front: bool = False, heights: dict[tuple[int, int], float] | None = None) -> list[int]:
    """Sleek 배치의 필기본. ``copies[i]`` 번 같은 강의록 쪽을 이어 싣는다. ``heights`` 쪽은 아래로 늘어난다(Sleek 처럼
    강의록 쪽 자리는 그대로). 돌려주는 것: 쪽마다 강의록 쪽 번호."""
    texts = texts or {}
    heights = heights or {}
    origins = []
    with pymupdf.open(slides) as original, pymupdf.open() as document:
        def panel(page, left: float, text: str) -> None:
            shape = page.new_shape()
            shape.draw_rect(pymupdf.Rect(left, 0, page.rect.width, page.rect.height))
            shape.finish(fill=PANEL_FILL, color=None, width=0)
            shape.draw_line(pymupdf.Point(left + 0.5, 0), pymupdf.Point(left + 0.5, page.rect.height))
            shape.finish(color=RULE_INK, width=1)
            shape.commit()
            for line, y in zip(text.split("\n"), range(40, 10_000, 18)):
                page.insert_text((left + 28, y), line, fontsize=12, color=(0.11, 0.18, 0.37))

        first = original[0].rect
        if front:
            page = document.new_page(width=first.width + PANEL, height=first.height)
            page.insert_text((first.width / 3, first.height / 2), "START", fontsize=18)
            panel(page, first.width, "loose notes")
            origins.append(-1)
        for index in range(original.page_count):
            rect = original[index].rect
            for part in range(copies.get(index, 1)):
                page = document.new_page(width=rect.width + PANEL, height=heights.get((index, part), rect.height))
                page.show_pdf_page(pymupdf.Rect(0, 0, rect.width, rect.height), original, index)
                panel(page, rect.width, texts.get((index, part), f"note {index + 1} part {part + 1}\nsecond line"))
                origins.append(index)
        document.save(output)
    return origins


def stroke_object(points: list[tuple[float, float]]) -> bytes:
    geometry = bytearray(struct.pack("<dd", *points[0]))
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        geometry += struct.pack("<HH", _delta(right_x - left_x), _delta(right_y - left_y))
    steps = len(points) - 1
    geometry += struct.pack(f"<f{steps}H", 1.0, *([0] * steps))            # 압력: 첫 값 + 점마다 차이
    geometry += struct.pack(f"<i{steps}H", 0, *([1] * steps))              # 시각: 첫 값 + 점마다 차이
    geometry += struct.pack("<H", 0)
    prefix_size = 6 + 4 + 1 + 1 + 1 + 2
    subrecord_size = prefix_size + len(geometry)
    subrecord = (struct.pack("<IH", subrecord_size, 1) + struct.pack("<I", subrecord_size) + b"\x01\x01"
                 + b"\x00" + struct.pack("<H", len(points)) + geometry)
    return b"\x01" + struct.pack("<HI", 0, len(subrecord) + 32) + subrecord + bytes(32)


def layers(*strokes: list[tuple[float, float]]) -> bytes:
    header = bytearray(16)
    struct.pack_into("<I", header, 0, len(header))
    return (struct.pack("<HH", 1, 0) + header + struct.pack("<I", len(strokes))
            + b"".join(stroke_object(points) for points in strokes) + bytes(32))


def notes_sdocx(path: Path, pdf: Path, ink: dict[int, list[list[tuple[float, float]]]]) -> None:
    """``pdf`` 쪽마다 ``.page`` 하나. ``ink[쪽]`` 은 획들(캔버스 px 좌표)."""
    pages, uuids = [], []
    with pymupdf.open(pdf) as document:
        for index, page in enumerate(document):
            uuid = f"{index + 1:08d}-0000-0000-0000-000000000000"
            height = round(page.rect.height * CANVAS_WIDTH / page.rect.width)
            pages.append(make_page(uuid=uuid, canvas=(CANVAS_WIDTH, height), pdf_page_index=index,
                                   strokes=layers(*ink.get(index, [])), hash_block=bytes([index + 1]) * 32))
            uuids.append(uuid)
    order = PageOrder(b"F" * 32, tuple(PageOrderEntry(u, page_hash(b)) for u, b in zip(uuids, pages)))
    pdf_bytes = pdf.read_bytes()
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("note.note", make_note(height=99999))
        archive.writestr("pageIdInfo.dat", order.to_bytes())
        for uuid, blob in zip(uuids, pages):
            archive.writestr(f"{uuid}.page", blob)
        archive.writestr("media/0@source.pdf", pdf_bytes)
        archive.writestr("media/mediaInfo.dat", make_media_info("0@source.pdf", pdf_bytes))
        archive.writestr("end_tag.bin", SPEN_FOOTER)
    with path.open("ab") as handle:
        handle.write(SPEN_FOOTER)


def saved_pages(path: Path) -> list[bytes]:
    with ZipFile(path) as archive:
        order = read_page_order(archive.read("pageIdInfo.dat"))
        return [archive.read(f"{entry.uuid}.page") for entry in order.entries]


def stroke(x: float, y: float) -> list[tuple[float, float]]:
    return [(x, y), (x + 20, y + 4), (x + 40, y)]


class SleekUpdateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.slides = make_document(self.root / "slides.pdf", SEEDS[:4])
        with pymupdf.open(self.slides) as slides:
            self.width = slides[0].rect.width
        self.density = CANVAS_WIDTH / (self.width + PANEL)

    def tearDown(self):
        self.folder.cleanup()

    def px(self, x_pt: float, y_pt: float) -> tuple[float, float]:
        return x_pt * self.density, y_pt * self.density

    def test_repeats_and_front_page_are_recognized(self):
        notes = self.root / "notes.pdf"
        notes_pdf(self.slides, notes, {1: 3}, front=True)
        with pymupdf.open(notes) as document, pymupdf.open(self.slides) as slides:
            self.assertTrue(is_notes_document(document))
            self.assertFalse(is_notes_document(slides))
            self.assertIsNone(page_layout(document[0]).lecture)           # 맨 앞 전용 쪽
            keys = [lecture_key(document[index]) for index in range(1, document.page_count)]
        self.assertEqual(keys[1], keys[2])
        self.assertEqual(keys[2], keys[3])
        self.assertNotEqual(keys[0], keys[1])

    def test_spread_follows_the_share_of_the_notes_flow(self):
        self.assertEqual(spread([1, 1, 1], [1, 1]), [0, 0, 1])            # 사용자 예: 3번 → 2번
        self.assertEqual(spread([1], [1, 1, 1]), [0])                      # 한 쪽 → 여러 쪽이면 첫 쪽
        self.assertEqual(spread([1, 1], [1, 1]), [0, 1])
        self.assertEqual(spread([10, 10, 2], [10, 10]), [0, 1, 1])        # 마지막이 조금 찬 쪽

    def test_fewer_repeats_merge_old_handwriting_and_keep_the_new_structure(self):
        old_pdf, new_pdf = self.root / "old.pdf", self.root / "new.pdf"
        old_origins = notes_pdf(self.slides, old_pdf, {1: 3})           # 1 2 2' 2'' 3 4
        new_origins = notes_pdf(self.slides, new_pdf, {1: 2})           # 1 2 2' 3 4
        self.assertEqual(old_origins, [0, 1, 1, 1, 2, 3])
        source = self.root / "old.sdocx"
        notes_sdocx(source, old_pdf, {
            1: [stroke(*self.px(40, 100))],
            2: [stroke(*self.px(60, 120))],
            3: [stroke(*self.px(80, 140)), stroke(*self.px(80, 180))],
            5: [stroke(*self.px(50, 50))],
        })
        inspection = inspect_transfer(source, new_pdf)
        self.assertEqual(inspection.notes_mode, "notes")
        self.assertEqual(inspection.page_count, 5)
        self.assertEqual(dict(inspection.merged), {1: (2,)})                # 옛 2·3쪽 → 새 2쪽, 옛 4쪽 → 새 3쪽
        plan = inspection.as_dict()["plan"]
        self.assertEqual([(s["source_index"], s["target_index"]) for s in plan["slots"]],
                         [(0, 0), (1, 1), (3, 2), (4, 3), (5, 4)])
        self.assertEqual(review(inspection.as_dict())["items"], [])          # 사람을 부르지 않는다

        output = self.root / "result.sdocx"
        result = transfer_handwriting(source, new_pdf, output)
        self.assertEqual(result["page_count"], 5)
        pages = saved_pages(output)
        self.assertEqual([read_page(blob).pdf.page_index for blob in pages], [0, 1, 2, 3, 4])
        counts = [len(read_ink_strokes(blob)[2]) for blob in pages]
        self.assertEqual(counts, [0, 2, 2, 0, 1])                           # 5획 그대로
        # 강의록 영역 획은 같은 강의록 자리에 — 옛 3쪽 획이 새 2쪽 그 자리에 있다.
        points = [stroke.points[0] for stroke in read_ink_strokes(pages[1])[2]]
        for want in (self.px(40, 100), self.px(60, 120)):
            self.assertTrue(any(abs(x - want[0]) < 1 and abs(y - want[1]) < 1 for x, y in points), (want, points))
        with ZipFile(output) as archive, pymupdf.open(stream=archive.read("media/0@source.pdf"), filetype="pdf") as pdf:
            self.assertEqual(pdf.page_count, 5)

    def test_extra_blank_repeat_is_dropped_and_inked_orphan_is_kept(self):
        old_pdf, new_pdf = self.root / "old.pdf", self.root / "new.pdf"
        notes_pdf(self.slides, old_pdf, {})                                 # 1 2 3 4
        with pymupdf.open(self.slides) as slides, pymupdf.open() as fewer:
            fewer.insert_pdf(slides, from_page=0, to_page=1)                # 새 판에서 강의록 3·4쪽이 사라짐
            fewer.save(self.root / "fewer.pdf")
        notes_pdf(self.root / "fewer.pdf", new_pdf, {})
        source = self.root / "old.sdocx"
        notes_sdocx(source, old_pdf, {3: [stroke(*self.px(40, 100))]})     # 4쪽에만 손필기
        inspection = inspect_transfer(source, new_pdf)
        self.assertEqual(inspection.dropped_sources, (2,))                  # 빈 옛 3쪽은 뺀다
        items = review(inspection.as_dict())["items"]
        self.assertEqual([(item["reason"], item["source_index"]) for item in items], [("old_only", 3)])

    def test_panel_handwriting_moves_to_blank_panel_space_when_the_notes_changed(self):
        old_pdf, new_pdf = self.root / "old.pdf", self.root / "new.pdf"
        notes_pdf(self.slides, old_pdf, {})
        long_text = "\n".join(f"brand new explanation line {n}" for n in range(12))
        notes_pdf(self.slides, new_pdf, {}, texts={(2, 0): long_text})
        # 옛 3쪽 칸의 둘째 줄 바로 아래(y≈60pt)에 쓴 손필기 — 새 판에서는 그 자리에 긴 글이 있다.
        left = self.width + 60
        source = self.root / "old.sdocx"
        notes_sdocx(source, old_pdf, {2: [stroke(*self.px(left, 62)), stroke(*self.px(left, 70))]})
        inspection = inspect_transfer(source, new_pdf)
        self.assertEqual(inspection.relocated_targets, (2,))
        self.assertEqual(inspection.crowded_targets, ())
        output = self.root / "result.sdocx"
        transfer_handwriting(source, new_pdf, output)
        strokes = read_ink_strokes(saved_pages(output)[2])[2]
        points = [(x / self.density, y / self.density) for s in strokes for x, y in s.points]
        box = (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points))
        with pymupdf.open(new_pdf) as document:
            words = document[2].get_text("words")
        self.assertGreater(box[0], self.width)                             # 여전히 칸 안
        for x0, y0, x1, y1, *_rest in words:
            self.assertFalse(x0 < box[2] and box[0] < x1 and y0 < box[3] and box[1] < y1, (box, (x0, y0, x1, y1)))
        # 미리보기도 같은 길 — 저장한 것과 같은 필기를 그린다.
        _before, _after, _ink, count = preview_transfer(source, new_pdf, 2, inspection)
        self.assertEqual(count, 2)

    def test_full_panel_sends_handwriting_to_blank_lecture_space(self):
        """칸이 새 글로 꽉 차면 강의록 영역의 빈칸으로 옮긴다 — 그림·글·다른 손필기 위는 피한다(사용자 결정 2026-09-25)."""
        old_pdf, new_pdf = self.root / "old.pdf", self.root / "new.pdf"
        notes_pdf(self.slides, old_pdf, {})
        full = "\n".join("filled panel line with many words to the edge " * 2 for _ in range(40))
        notes_pdf(self.slides, new_pdf, {}, texts={(2, 0): full})
        source = self.root / "old.sdocx"
        left = self.width + 60
        x, y = self.px(left, 62)
        # 두 줄 높이(약 40pt)의 손글씨 — 칸 위쪽 여백(27pt)에도, 글 줄 사이에도 들어가지 않는다.
        word = [(x, y), (x + 20, y + 70), (x + 40, y), (x + 60, y + 70)]
        notes_sdocx(source, old_pdf, {2: [word, stroke(*self.px(40, 40))]})
        inspection = inspect_transfer(source, new_pdf)
        self.assertEqual(inspection.crowded_targets, ())                    # 사람을 부르지 않는다
        self.assertEqual(inspection.relocated_targets, (2,))
        output = self.root / "result.sdocx"
        transfer_handwriting(source, new_pdf, output)
        strokes = read_ink_strokes(saved_pages(output)[2])[2]
        moved = [s for s in strokes if s.points[0] != self.px(40, 40)]
        self.assertEqual(len(moved), 1)
        points = [(x / self.density, y / self.density) for x, y in moved[0].points]
        box = (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points))
        with pymupdf.open(new_pdf) as document:
            lecture = page_layout(document[2]).lecture
            self.assertLessEqual(box[2], lecture.x1)                        # 강의록 영역 안으로
            clip = pymupdf.Rect(*box)
            pixels = document[2].get_pixmap(clip=clip, colorspace=pymupdf.csGRAY, dpi=72)
        self.assertGreater(min(pixels.samples), 240)                        # 그 자리는 비어 있었다
        near = self.px(40, 40)
        self.assertFalse(box[0] < near[0] / self.density + 40 and near[0] / self.density < box[2]
                         and box[1] < near[1] / self.density + 4 and near[1] / self.density < box[3])

    def test_handwriting_below_a_grown_page_stays_on_a_page_that_did_not_grow(self):
        """필기가 길어 쪽이 아래로 늘어난 옛 필기본(질문 2026-09-25): 늘어난 아래 칸에 쓴 손필기는, 새 판에서 쪽이
        늘어나지 않았으면 새 쪽의 여백으로 간다 — 쪽 밖으로 떨어지지 않는다."""
        old_pdf, new_pdf = self.root / "old.pdf", self.root / "new.pdf"
        with pymupdf.open(self.slides) as slides:
            tall = slides[0].rect.height * 1.4
        notes_pdf(self.slides, old_pdf, {}, heights={(1, 0): tall})
        notes_pdf(self.slides, new_pdf, {})
        with pymupdf.open(old_pdf) as document:
            self.assertIsNotNone(page_layout(document[1]).lecture)          # 늘어나도 필기본 쪽으로 안다
            below = document[1].rect.height - 30
        source = self.root / "old.sdocx"
        notes_sdocx(source, old_pdf, {1: [stroke(*self.px(40, below))]})
        inspection = inspect_transfer(source, new_pdf)
        self.assertEqual(inspection.page_count, 4)
        self.assertEqual(inspection.relocated_targets, (1,))
        output = self.root / "result.sdocx"
        transfer_handwriting(source, new_pdf, output)
        page = saved_pages(output)[1]
        _width, canvas_height, strokes = read_ink_strokes(page)
        self.assertEqual(len(strokes), 1)
        self.assertTrue(all(0 <= y <= canvas_height for _x, y in strokes[0].points))

    def test_panel_handwriting_stays_when_the_notes_are_the_same(self):
        notes = self.root / "notes.pdf"
        notes_pdf(self.slides, notes, {})
        source = self.root / "old.sdocx"
        underline = [self.px(self.width + 28, 44), self.px(self.width + 120, 44)]
        notes_sdocx(source, notes, {1: [underline]})
        inspection = inspect_transfer(source, notes)
        self.assertEqual(inspection.relocated_targets, ())
        output = self.root / "result.sdocx"
        transfer_handwriting(source, notes, output)
        first = read_ink_strokes(saved_pages(output)[1])[2][0].points[0]
        self.assertAlmostEqual(first[0], underline[0][0], delta=0.5)
        self.assertAlmostEqual(first[1], underline[0][1], delta=0.5)


class EveryPageInkedTests(unittest.TestCase):
    """모든 쪽에 필기가 있는 노트에서 사람이 짝을 바꿔 새 쪽이 비면, 본뜰 빈 쪽이 없다(2026-09-26 진단에서 찾음).
    필기 쪽을 본떠 빈 쪽을 만들어 저장한다 — 전에는 「빈 PDF 페이지 템플릿이 없습니다」로 저장이 멈췄다."""

    def test_moving_a_page_saves_when_no_blank_page_exists(self):
        from tests.test_page_match import make_document as slides_pdf

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            slides = slides_pdf(root / "slides.pdf", SEEDS[:3])
            source = root / "old.sdocx"
            notes_sdocx(source, slides, {0: [stroke(100, 100)], 1: [stroke(200, 200)], 2: [stroke(300, 300)]})
            inspection = inspect_transfer(source, slides)
            # 사람이 옛 1쪽 필기를 새 2쪽으로 — 새 1쪽은 빈 쪽이 되고, 새 2쪽에 있던 옛 2쪽은 옛 쪽째 남는다.
            rows = [
                {"source_index": None, "target_index": 0, "confirmed": True, "excluded": False},
                {"source_index": 0, "target_index": 1, "confirmed": True, "excluded": False},
                {"source_index": 1, "target_index": None, "confirmed": True, "excluded": False},
                {"source_index": 2, "target_index": 2, "confirmed": True, "excluded": False},
            ]
            plan = PagePlan.from_payload(3, 3, rows, inspection.match)
            output = root / "moved.sdocx"
            transfer_handwriting(source, slides, output, plan_override=plan)
            pages = saved_pages(output)
        counts = [len(read_ink_strokes(blob)[2]) for blob in pages]
        self.assertEqual(counts, [0, 1, 1, 1])
        self.assertEqual(read_page(pages[0]).property_mask & 0x401, 0)          # 그린 범위·펜 캐시 참조 없음
        self.assertEqual(read_ink_strokes(pages[1])[2][0].points[0], (100.0, 100.0))


class NotewiseSleekUpdateTests(unittest.TestCase):
    """Samsung Notes 와 같은 계획을 Notewise 도 그대로 저장한다(요청 6)."""

    def test_fewer_repeats_merge_in_notewise_too(self):
        from riffle.notewise_transfer import inspect_notewise_transfer, transfer_notewise_handwriting
        from tests.test_notewise_transfer import _make_notewise

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            slides = make_document(root / "slides.pdf", SEEDS[:4])
            old_pdf, new_pdf = root / "old.pdf", root / "new.pdf"
            notes_pdf(slides, old_pdf, {1: 3})
            notes_pdf(slides, new_pdf, {1: 2})
            source = root / "old.notewise"
            with pymupdf.open(old_pdf) as document:
                size = (round(document[0].rect.width), round(document[0].rect.height))
            _make_notewise(source, old_pdf, pages=6, canvas=size)            # 쪽마다 한 획
            inspection = inspect_notewise_transfer(source, new_pdf)
            self.assertEqual(inspection.notes_mode, "notes")
            self.assertEqual(dict(inspection.merged), {1: (2,)})
            result = transfer_notewise_handwriting(source, new_pdf, root / "out.notewise")
            self.assertEqual(result["page_count"], 5)
            with ZipFile(root / "out.notewise") as archive:
                pages = [archive.read(name) for name in archive.namelist() if name.startswith("page/")]
            counts = sorted(len(NOTEWISE.boxes(page)) for page in pages)
            self.assertEqual(counts, [1, 1, 1, 1, 2])                        # 6획 그대로, 새 2쪽에 둘


class CommonLayerTests(unittest.TestCase):
    """세 형식이 같은 세 동작(상자·객체마다 변환·합치기)을 한다(요청 6)."""

    def test_samsung_notes_objects_move_one_by_one_and_merge(self):
        page = make_page(strokes=layers(stroke(100, 100), stroke(500, 300)))
        other = make_page(strokes=layers(stroke(900, 50)))
        self.assertEqual(len(SAMSUNG_NOTES.boxes(page)), 2)
        shift = CanvasTransform(1, 1, 10, 20, 1848, 1039)
        still = CanvasTransform(1, 1, 0, 0, 1848, 1039)
        moved = SAMSUNG_NOTES.transform(page, still, [still, shift])
        boxes = object_boxes(moved)
        self.assertAlmostEqual(boxes[0][0], 100)
        self.assertAlmostEqual(boxes[1][0], 510)
        self.assertAlmostEqual(boxes[1][1], 320)
        merged = SAMSUNG_NOTES.merge(moved, [other])
        self.assertEqual(len(read_ink_strokes(merged)[2]), 3)
        self.assertEqual(read_page(merged).uuid, read_page(page).uuid)

    def test_goodnotes_and_notewise_follow_the_same_contract(self):
        fixture = Path(__file__).with_name("fixtures") / "goodnotes" / "gn-mac-mixed-pens.goodnotes"
        with ZipFile(fixture) as archive:
            journal = archive.read(next(n for n in archive.namelist() if n.startswith("notes/")))
        elements = journal_elements(journal)
        boxes = GOODNOTES.boxes(journal)
        self.assertEqual(len(elements), len(boxes))
        still = CanvasTransform(1, 1, 0, 0, 100, 100)
        shift = CanvasTransform(1, 1, 5, 7, 100, 100)
        index = next(i for i, box in enumerate(boxes) if box is not None)
        per = [shift if i == index else still for i in range(len(boxes))]
        moved = element_boxes(GOODNOTES.transform(journal, still, per))
        self.assertAlmostEqual(moved[index][0], boxes[index][0] + 5, places=2)
        self.assertAlmostEqual(moved[index][1], boxes[index][1] + 7, places=2)
        merged = GOODNOTES.merge(journal, [journal])
        self.assertEqual(len(journal_elements(merged)), 2 * len(elements))

        from tests.test_notewise_transfer import _make_notewise, _make_pdf

        with tempfile.TemporaryDirectory() as folder:
            pdf, notewise = Path(folder) / "a.pdf", Path(folder) / "a.notewise"
            _make_pdf(pdf, "A")
            _make_notewise(notewise, pdf)
            with ZipFile(notewise) as archive:
                page = archive.read(next(n for n in archive.namelist() if n.startswith("page/")))
        count = len(NOTEWISE.boxes(page))
        self.assertGreater(count, 0)
        moved = NOTEWISE.boxes(NOTEWISE.transform(page, still, [shift] * count))
        first = next(box for box in NOTEWISE.boxes(page) if box is not None)
        after = next(box for box in moved if box is not None)
        self.assertAlmostEqual(after[0], first[0] + 5, places=3)
        self.assertEqual(len(NOTEWISE.boxes(NOTEWISE.merge(page, [page]))), 2 * count)


class PlanMergedRowsTests(unittest.TestCase):
    def test_merged_sources_count_once_and_round_trip(self):
        plan = PagePlan.from_payload(3, 2, [
            {"source_index": 0, "target_index": 0, "confirmed": True, "excluded": False, "merged": [1]},
            {"source_index": 2, "target_index": 1, "confirmed": True, "excluded": False},
        ])
        self.assertEqual(plan.slots[0].sources, (0, 1))
        self.assertEqual(plan.as_dict()["slots"][0]["merged"], [1])
        with self.assertRaises(Exception):
            PagePlan.from_payload(3, 2, [
                {"source_index": 0, "target_index": 0, "confirmed": True, "merged": [1]},
                {"source_index": 1, "target_index": 1, "confirmed": True},      # 1이 두 번
                {"source_index": 2, "target_index": None, "confirmed": True},
            ])


if __name__ == "__main__":
    unittest.main()
