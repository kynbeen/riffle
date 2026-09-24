"""Sleek 필기본(오른쪽에 필기 칸을 붙인 PDF)으로 필기를 옮길 때의 짝짓기·정렬·경고."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import pymupdf

from noteditor.alignment import estimate_alignment
from noteditor.page_match import match_pages
from noteditor.sdocx_ink import read_ink_strokes
from noteditor.sdocx_page import read_page
from noteditor.sdocx_rebuild import rebuild_handwriting
from noteditor.sdocx_transfer import inspect_transfer
from noteditor.sleek_notes import original_box
from tests.test_page_match import SEEDS, make_document
from tests.test_sdocx_ink import make_stroke_layers
from tests.test_sdocx_rebuild import UUIDS, make_rebuild_source

PANEL = 470.84
PANEL_FILL = (0.992, 0.980, 0.945)
RULE_INK = (0.89, 0.86, 0.79)


def make_sleek_notes(
    source: Path,
    output: Path,
    *,
    notes: dict[int, str] | None = None,
    taller: dict[int, float] | None = None,
    repeats: frozenset[int] = frozenset(),
    front: bool = False,
) -> None:
    """Sleek ``pages.render`` 와 같은 배치로 필기본을 만든다.

    원래 쪽은 왼쪽 위에 배율 1로 끼우고, 오른쪽에 쪽 높이 전체를 덮는 칸을 칠한 뒤 글을 쓴다.
    ``taller`` 쪽은 아래로만 늘어나고(초기판처럼 아래는 비워 둔다), ``repeats`` 쪽은 같은
    슬라이드를 한 번 더 싣는다. ``front`` 면 슬라이드 없는 맨 앞 쪽을 붙인다.
    """
    notes = notes or {}
    taller = taller or {}
    with pymupdf.open(source) as original, pymupdf.open() as document:
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
        for index in range(original.page_count):
            rect = original[index].rect
            copies = 2 if index in repeats else 1
            for part in range(copies):
                height = max(rect.height, taller.get(index, 0.0)) if part == 0 else rect.height
                page = document.new_page(width=rect.width + PANEL, height=height)
                page.show_pdf_page(pymupdf.Rect(0, 0, rect.width, rect.height), original, index)
                text = notes.get(index, f"note for page {index + 1}")
                panel(page, rect.width, text if part == 0 else "continued\n" + text[::-1])
        document.save(output)


class SleekNotesTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.slides = make_document(self.root / "slides.pdf", SEEDS[:6])

    def tearDown(self):
        self.folder.cleanup()

    def test_original_box_is_found_even_on_a_page_that_grew_downward(self):
        notes = self.root / "notes.pdf"
        make_sleek_notes(self.slides, notes, taller={2: 700.0}, front=True)
        with pymupdf.open(self.slides) as slides, pymupdf.open(notes) as document:
            size = slides[0].rect
            self.assertIsNone(original_box(slides[0]))       # 일반 쪽
            self.assertIsNone(original_box(document[0]))     # 슬라이드 없는 맨 앞 쪽
            for index in range(1, document.page_count):
                box = original_box(document[index])
                self.assertIsNotNone(box, index)
                self.assertAlmostEqual(box.x1, size.width, delta=0.5)
                self.assertAlmostEqual(box.y1, size.height, delta=0.5)
            self.assertAlmostEqual(document[3].rect.height, 700.0)

    def test_slides_match_the_first_copy_and_the_panel_is_ignored(self):
        notes = self.root / "notes.pdf"
        long_note = "\n".join(f"long note line {n}" for n in range(20))
        make_sleek_notes(self.slides, notes, notes={1: long_note, 3: long_note},
                         taller={1: 720.0}, repeats=frozenset({3}), front=True)
        with pymupdf.open(self.slides) as source, pymupdf.open(notes) as target:
            result = match_pages(source, target)
            pairs = [(pair.source_index, pair.target_index) for pair in result.matched_pairs]
            self.assertEqual(pairs, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 6), (5, 7)])
            self.assertEqual(result.target_only, (0, 5))    # 맨 앞 쪽, 3쪽의 "이어서" 사본
            self.assertEqual(result.uncertain, ())
            alignment = estimate_alignment(source, target, pairs)
        self.assertAlmostEqual(alignment.scale, 1.0, delta=0.002)
        self.assertLess(abs(alignment.offset_x) + abs(alignment.offset_y), 1.0)
        self.assertFalse(alignment.requires_confirmation)

    def test_an_older_notes_edition_matches_a_newer_one_page_by_page(self):
        old, new = self.root / "old.pdf", self.root / "new.pdf"
        make_sleek_notes(self.slides, old, notes={2: "old wording"}, repeats=frozenset({2}))
        make_sleek_notes(self.slides, new, notes={2: "new wording\n" * 3},
                         repeats=frozenset({2, 4}), taller={4: 650.0})
        with pymupdf.open(old) as source, pymupdf.open(new) as target:
            result = match_pages(source, target)
        # 구판: 1 2 3 3' 4 5 6 / 새 판: 1 2 3 3' 4 5 5' 6 (' 는 같은 슬라이드를 다시 실은 쪽)
        self.assertEqual(result.source_to_target(), {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 7})
        self.assertEqual(result.target_only, (6,))
        self.assertEqual(result.uncertain, ())

    def test_extra_copies_in_the_older_edition_are_the_later_ones(self):
        """손필기는 보통 첫 사본에 있다. 구판에만 있는 사본은 뒤쪽 것이어야 한다."""
        old, new = self.root / "old.pdf", self.root / "new.pdf"
        make_sleek_notes(self.slides, old, repeats=frozenset({2}))
        make_sleek_notes(self.slides, new)
        with pymupdf.open(old) as source, pymupdf.open(new) as target:
            result = match_pages(source, target)
        self.assertEqual(result.source_to_target()[2], 2)
        self.assertEqual(result.source_only, (3,))
        self.assertEqual(result.uncertain, ())

    def test_ink_moves_onto_the_slide_part_of_a_wider_notes_page(self):
        """Samsung Notes 처럼 캔버스 폭은 노트 폭 그대로이고, 필기는 슬라이드 자리에 남는다."""
        slides = self.root / "wide.pdf"
        with pymupdf.open() as document:
            for label in ("A", "B", "C", "D"):
                document.new_page(width=960, height=540).insert_text((60, 80), label, fontsize=40)
            document.save(slides)
        notes = self.root / "notes.pdf"
        make_sleek_notes(slides, notes)
        source = self.root / "source.sdocx"
        make_rebuild_source(source, slides, annotated_layers=make_stroke_layers())
        with pymupdf.open(slides) as origin, pymupdf.open(notes) as target:
            result = match_pages(origin, target)
            wide = target[2].rect.width
        output = self.root / "moved.sdocx"
        rebuild_handwriting(source, notes, output, result)
        with ZipFile(output) as archive:
            blob = archive.read(f"{UUIDS[2]}.page")
        info = read_page(blob)
        _width, _height, strokes = read_ink_strokes(blob)
        self.assertEqual(info.canvas_width, 1848)
        self.assertAlmostEqual(info.canvas_height, round(540 * 1848 / wide), delta=1)
        # 원본 캔버스 x=100(=51.9pt) → 넓은 쪽에서도 51.9pt 자리
        self.assertAlmostEqual(strokes[0].points[0][0], 100 * 960 / wide, delta=0.5)

    def test_handwriting_on_the_notes_panel_asks_for_confirmation(self):
        slides = self.root / "wide.pdf"
        with pymupdf.open() as document:
            for label in ("A", "B", "C", "D"):
                document.new_page(width=960, height=540).insert_text((60, 80), label, fontsize=40)
            document.save(slides)
        notes = self.root / "notes.pdf"
        make_sleek_notes(slides, notes)
        source = self.root / "old-notes.sdocx"
        # 넓은 쪽(1430.84pt)이 1848px 캔버스에 들어가 있다. x=1600px ≈ 1239pt 는 필기 칸 위다.
        make_rebuild_source(source, notes, annotated_layers=make_stroke_layers(
            [(1600.0, 300.0), (1610.0, 305.0), (1606.0, 312.0)]))
        inspection = inspect_transfer(source, notes)
        self.assertEqual(inspection.panel_ink_sources, (2,))
        payload = inspection.as_dict()
        self.assertEqual(payload["panel_ink_sources"], [2])
        slot = next(s for s in payload["plan"]["slots"] if s["source_index"] == 2)
        self.assertFalse(slot["confirmed"])

    def test_handwriting_on_the_slide_part_does_not_warn(self):
        slides = self.root / "wide.pdf"
        with pymupdf.open() as document:
            for label in ("A", "B", "C", "D"):
                document.new_page(width=960, height=540).insert_text((60, 80), label, fontsize=40)
            document.save(slides)
        notes = self.root / "notes.pdf"
        make_sleek_notes(slides, notes)
        source = self.root / "old-notes.sdocx"
        make_rebuild_source(source, notes, annotated_layers=make_stroke_layers())
        self.assertEqual(inspect_transfer(source, notes).panel_ink_sources, ())


if __name__ == "__main__":
    unittest.main()
