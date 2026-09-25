"""필기 이전에 공통으로 쓰는 판단: 오류 부모, 진단 결과, 원본·대상 PDF 짝 맞추기.

Samsung Notes(SDOCX)든 Notewise든 "문서에 들어 있는 PDF를 새 PDF로 갈아 끼운다"는 절차는
같다. 그대로 넣을지(``exact``), 본문 기준으로 다시 앉힐지(``aligned``), 쪽 구성을 다시 짜야
하는지(``rebuild``)를 정하는 판단은 필기 형식과 무관하므로 여기 한곳에 둔다.

오류 메시지에는 형식별 이름이 그대로 드러나야 하므로, 어느 예외를 던질지와 PDF를 뭐라고
부를지는 호출하는 쪽이 ``error``·``source_label``로 넘긴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from collections.abc import Callable, Sequence

from .alignment import Alignment, estimate_alignment, place_page
from .ink_layer import InkCodec
from .ink_transform import CanvasTransform, canvas_transform
from .page_match import MatchResult, fingerprints, match_fingerprints
from .reorder import Reorder, pair_reordered
from .page_plan import PagePlan
from .sleek_match import NOTES, NotesMatch, match_notes, notes_mode


class HandwritingTransferError(RuntimeError):
    """필기 이전 중 사용자에게 그대로 보여줄 수 있는 오류의 공통 부모."""


@dataclass(frozen=True)
class TransferInspection:
    source_name: str
    target_name: str
    page_count: int
    annotated_page_count: int
    stroke_cache_count: int
    embedded_pdf_name: str
    target_size: int
    source_page_count: int | None = None
    mode: str = "exact"
    alignment: Alignment | None = None
    match: MatchResult | None = None
    source_order: tuple[dict, ...] = ()
    # 원본이 Sleek 필기본일 때 오른쪽 필기 칸 위에 손필기가 있는 원본 쪽(0부터)
    panel_ink_sources: tuple[int, ...] = ()
    # 새 판에서 순서가 바뀌어 다시 짝지은 옛 쪽, 닮았지만 애매해 사람에게 보일 옛 쪽 → 새 쪽(reorder.py)
    moved_sources: tuple[int, ...] = ()
    pair_candidates: tuple[tuple[int, int], ...] = ()
    closest_targets: tuple[tuple[int, int], ...] = ()     # 짝도 후보도 없는 옛 쪽 → 가장 닮은 새 쪽
    # 판정에 쓴 옛·새 쪽 지문 — 저장할 때 사례로 남긴다(cases.py). as_dict 에 넣지 않는다(화면 응답이 무거워진다).
    prints: tuple = field(default=(), repr=False, compare=False)
    # 새 파일이 Sleek 필기본일 때(명세 2026-09-25-03): "notes"(필기본 → 필기본) · "into_notes"(그 밖 → 필기본) · ""
    notes_mode: str = ""
    merged: tuple[tuple[int, tuple[int, ...]], ...] = ()     # 새 쪽 → 함께 얹는 옛 쪽
    dropped_sources: tuple[int, ...] = ()                     # 새 판에 없고 손필기도 없어 결과에서 뺀 옛 쪽
    resized_runs: int = 0                                     # 반복 수가 바뀐 강의록 쪽 수
    crowded_targets: tuple[int, ...] = ()                     # 여백이 모자라 칸 손필기가 글과 겹친 새 쪽
    relocated_targets: tuple[int, ...] = ()                   # 칸 손필기를 여백으로 옮긴 새 쪽
    inked_sources: tuple[int, ...] = ()                       # 손필기가 있는 옛 쪽

    def page_plan(self) -> PagePlan | None:
        if self.match is None or self.source_page_count is None:
            return None
        return PagePlan.from_match(
            self.match, self.source_page_count, self.page_count,
            merged=dict(self.merged), excluded_sources=self.dropped_sources,
            trusted=self.notes_mode == NOTES,
        )

    def as_dict(self) -> dict:
        plan = None
        if self.match is not None and self.source_page_count is not None:
            page_plan = self.page_plan()
            if self.alignment is not None and self.alignment.requires_confirmation:
                page_plan = replace(page_plan, slots=tuple(
                    replace(slot, confirmed=False) if slot.kind == "matched" else slot
                    for slot in page_plan.slots
                ))
            if self.panel_ink_sources:
                panel = set(self.panel_ink_sources)
                page_plan = replace(page_plan, slots=tuple(
                    replace(slot, confirmed=False) if slot.source_index in panel else slot
                    for slot in page_plan.slots
                ))
            if self.crowded_targets:
                crowded = set(self.crowded_targets)
                page_plan = replace(page_plan, slots=tuple(
                    replace(slot, confirmed=False) if slot.target_index in crowded else slot
                    for slot in page_plan.slots
                ))
            plan = page_plan.as_dict()
        return {
            "source_name": self.source_name,
            "target_name": self.target_name,
            "page_count": self.page_count,
            "annotated_page_count": self.annotated_page_count,
            "stroke_cache_count": self.stroke_cache_count,
            "embedded_pdf_name": self.embedded_pdf_name,
            "target_size": self.target_size,
            "source_page_count": self.source_page_count,
            "mode": self.mode,
            "alignment": self.alignment.as_dict() if self.alignment else None,
            "match": self.match.as_dict() if self.match else None,
            "plan": plan,
            "source_order": list(self.source_order),
            "panel_ink_sources": list(self.panel_ink_sources),
            "moved_sources": list(self.moved_sources),
            "pair_candidates": [list(pair) for pair in self.pair_candidates],
            "closest_targets": [list(pair) for pair in self.closest_targets],
            "notes_mode": self.notes_mode,
            "merged": [[target, list(sources)] for target, sources in self.merged],
            "dropped_sources": list(self.dropped_sources),
            "resized_runs": self.resized_runs,
            "crowded_targets": list(self.crowded_targets),
            "relocated_targets": list(self.relocated_targets),
            "inked_sources": list(self.inked_sources),
        }


def open_pdf(
    pdf: bytes | Path, label: str, *, error: type[Exception] = HandwritingTransferError
):
    """PDF를 열고 필기 이전에 쓸 수 없는 문서는 그 자리에서 거른다. 호출자가 닫는다."""
    from . import pdf as pymupdf

    try:
        if isinstance(pdf, Path):
            document = pymupdf.open(pdf)
        else:
            document = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception as exc:
        raise error(f"{label}를 읽을 수 없습니다: {exc}") from exc
    try:
        if document.needs_pass:
            raise error(f"암호화된 {label}는 지원하지 않습니다.")
        if document.page_count < 1:
            raise error(f"페이지가 없는 {label}입니다.")
    except Exception:
        document.close()
        raise
    return document


def render_source_background(
    embedded_pdf: bytes, source_index: int, *, max_side: int = 900,
    error: type[Exception] = HandwritingTransferError,
) -> bytes:
    """Render an unmatched source page in its own, unchanged coordinates."""
    from . import pdf as pymupdf

    with open_pdf(embedded_pdf, "원본 배경 PDF", error=error) as document:
        if not 0 <= source_index < document.page_count:
            raise error(f"원본 문서에 없는 쪽 번호입니다: {source_index + 1}")
        page = document[source_index]
        scale = min(max_side / max(page.rect.width, page.rect.height), 3.0)
        return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")


def geometry(document) -> list[tuple[float, float, int]]:
    return [
        (round(float(page.rect.width), 3), round(float(page.rect.height), 3), int(page.rotation))
        for page in document
    ]


def geometry_mismatches(
    source: list[tuple[float, float, int]], target: list[tuple[float, float, int]]
) -> list[int]:
    """크기나 회전이 다른 쪽의 번호(1부터)를 모은다."""
    mismatches = []
    for index, (left, right) in enumerate(zip(source, target), start=1):
        same_size = abs(left[0] - right[0]) <= 0.5 and abs(left[1] - right[1]) <= 0.5
        if not same_size or left[2] != right[2]:
            mismatches.append(index)
    return mismatches


def build_background_pdf(
    source_document,
    target_document,
    mapping: Sequence[int | None],
    alignment: Alignment,
    *,
    reference_index: int = 0,
    error: type[Exception] = HandwritingTransferError,
) -> bytes:
    """대상 PDF를 원본 페이지 좌표계에 다시 앉힌 배경 PDF 바이트를 만든다.

    ``mapping[대상쪽] = 원본쪽`` 이고, 새로 끼어들어 짝이 없는 쪽은 ``None`` 이다. 그런 쪽에는
    기준 좌표계가 없으므로 ``reference_index`` 원본 쪽의 크기를 빌린다.

    필기 좌표는 절대 건드리지 않고 배경만 옮기는 것이 이 프로젝트의 전제다. 그래서 결과
    PDF의 모든 쪽은 원본 캔버스와 같은 크기여야 하고, 아니면 내보내지 않고 거절한다.
    """
    from . import pdf as pymupdf

    source_geometry = geometry(source_document)
    expected = [
        source_geometry[reference_index if index is None else index] for index in mapping
    ]
    with pymupdf.open() as document:
        for target_index, source_index in enumerate(mapping):
            reference = source_document[
                reference_index if source_index is None else source_index
            ]
            place_page(document, reference, target_document, target_index, alignment)
        built = geometry(document)
        payload = document.tobytes(garbage=4, deflate=True)

    mismatches = geometry_mismatches(expected, built)
    if mismatches:
        shown = ", ".join(map(str, mismatches[:8]))
        suffix = "…" if len(mismatches) > 8 else ""
        raise error(
            f"정렬한 배경의 {shown}{suffix}쪽 크기가 원본 캔버스와 달라 저장하지 않았습니다."
        )
    return payload


def build_planned_background_pdf(
    source_document,
    target_document,
    plan: PagePlan,
    alignment: Alignment | None,
    *,
    reference_index: int = 0,
    error: type[Exception] = HandwritingTransferError,
) -> bytes:
    """행 계획 순서로 PDF 쪽을 원래 기하 그대로 담는다.

    대상 쪽은 대상 PDF가 유일한 기준이다. 원본에만 남은 필기 쪽에만 옛 배경을 쓴다.
    ``alignment`` 는 호출 호환을 위해 받지만 배경을 자르는 데 사용하지 않는다.
    """
    from . import pdf as pymupdf

    _ = alignment
    source_geometry = geometry(source_document)
    target_geometry = geometry(target_document)
    expected: list[tuple[float, float, int]] = []
    with pymupdf.open() as document:
        for slot in plan.slots:
            if slot.target_index is None:
                assert slot.source_index is not None
                document.insert_pdf(
                    source_document,
                    from_page=slot.source_index,
                    to_page=slot.source_index,
                )
                expected.append(source_geometry[slot.source_index])
                continue

            expected.append(target_geometry[slot.target_index])
            document.insert_pdf(
                target_document,
                from_page=slot.target_index,
                to_page=slot.target_index,
            )
        built = geometry(document)
        payload = document.tobytes(garbage=4, deflate=True)

    mismatches = geometry_mismatches(expected, built)
    if mismatches:
        shown = ", ".join(map(str, mismatches[:8]))
        suffix = "…" if len(mismatches) > 8 else ""
        raise error(
            f"행 계획으로 만든 배경의 {shown}{suffix}쪽 크기가 원본 캔버스와 달라 저장하지 않았습니다."
        )
    return payload


@dataclass(frozen=True)
class PlannedTransfer:
    mode: str
    alignment: Alignment | None
    page_count: int
    match: MatchResult
    reorder: Reorder
    notes: NotesMatch | None = None


def _alignment_pairs(source_document, target_document, pairs) -> list[tuple[int, int]]:
    """정렬을 잴 짝. 필기본 맨 앞 전용 쪽(강의록 쪽 없음)은 뺀다 — 쪽 전체의 글이 본문으로 잡혀 배율을 흐린다."""
    from .sleek_notes import page_layout

    def front(page) -> bool:
        layout = page_layout(page)
        return layout is not None and layout.lecture is None

    return [(s, t) for s, t in pairs if not front(source_document[s]) and not front(target_document[t])]


def plan_transfer(
    embedded_pdf: bytes,
    target: Path,
    *,
    source_label: str = "내장 PDF",
    error: type[Exception] = HandwritingTransferError,
    progress: Callable[[str], None] | None = None,
    inked: set[int] | None = None,
) -> PlannedTransfer:
    """그대로 넣을지(``exact``), 본문 기준으로 다시 앉힐지(``aligned``) 정한다.

    짝짓기 뒤에 새 판에서 순서가 바뀐 쪽을 다시 짝짓는다(``reorder.py``). 돌려주는 ``match`` 는 그 결과다.
    새 파일이 Sleek 필기본이면 반복 묶음 단위로 짝짓는다(``sleek_match.py``, 명세 2026-09-25-03). ``inked`` 는
    손필기가 있는 옛 쪽 — 새 판에 없는 옛 쪽을 남길지 뺄지 가른다.
    """
    source_document = open_pdf(embedded_pdf, source_label, error=error)
    try:
        target_document = open_pdf(target, "대상 PDF", error=error)
    except Exception:
        source_document.close()
        raise
    notes = None
    try:
        source_geometry = geometry(source_document)
        target_geometry = geometry(target_document)
        if progress:
            progress("matching")
        source_prints, target_prints = fingerprints(source_document), fingerprints(target_document)
        mode_of_notes = notes_mode(source_document, target_document)
        if mode_of_notes is not None:
            notes = match_notes(source_document, target_document, source_prints, target_prints,
                                set(inked or ()), mode_of_notes)
            reorder = notes.reorder
        else:
            reorder = pair_reordered(match_fingerprints(source_prints, target_prints), source_prints, target_prints)
        match = reorder.match
        # 다시 짝지은 쪽이 있으면 쪽 순서가 원본과 엇갈리므로 바이트 그대로 넣을 수 없다.
        # 필기본 → 필기본은 늘 다시 짓는다 — 칸 손필기를 쪽마다 여백으로 옮겨야 한다.
        rebuild = bool(match.source_only or match.target_only or reorder.moved
                       or (notes is not None and (notes.merged or notes.dropped or notes.mode == NOTES)))
        matched_indices = [
            (pair.source_index, pair.target_index) for pair in match.matched_pairs
        ]
        same_geometry = all(
            abs(source_geometry[source][0] - target_geometry[target_index][0]) <= 0.5
            and abs(source_geometry[source][1] - target_geometry[target_index][1]) <= 0.5
            and source_geometry[source][2] == target_geometry[target_index][2]
            for source, target_index in matched_indices
        )
        if progress:
            progress("alignment")
        alignment = estimate_alignment(
            source_document, target_document,
            _alignment_pairs(source_document, target_document, matched_indices),
        )
        if progress:
            progress("preview")
    finally:
        source_document.close()
        target_document.close()

    def result(mode: str, fit: Alignment | None) -> PlannedTransfer:
        return PlannedTransfer(mode, fit, len(target_geometry), match, reorder, notes)

    if alignment is None:
        if not same_geometry:
            raise error(
                "페이지 크기가 다른데 두 문서의 본문 영역을 찾지 못해 정렬 배율을 정할 수 없습니다. "
                "내용이 비어 있거나 스캔 품질이 낮은 문서일 수 있습니다."
            )
        return result("rebuild" if rebuild else "exact", None)
    if same_geometry and not (alignment.improves and alignment.axes_agree):
        # 페이지 크기가 같고 본문 배치도 그대로면 사용자의 PDF를 바이트 그대로 넣는다.
        return result("rebuild" if rebuild else "exact", None)
    return result("rebuild" if rebuild else "aligned", alignment)


# ---------------------------------------------------------------- 형식 공통 분석·쪽 필기(명세 2026-09-25-03)

_PANEL_EDGE_SLACK = 2.0


@dataclass(frozen=True)
class SourceInk:
    """옛 파일의 쪽마다 필기 바이트와 캔버스. 형식이 채우고, 판정·배치는 이 모듈과 ``page_ink`` 가 한다."""

    codec: InkCodec
    pages: dict[int, tuple[bytes, tuple[float, float]]]    # 옛 PDF 쪽 번호 → (필기 바이트, 캔버스 크기)
    fixed_canvas_width: bool = False                        # Samsung Notes: 캔버스 폭이 쪽 폭과 무관하게 고정
    stroke_counts: dict[int, int] = field(default_factory=dict)

    def inked(self) -> set[int]:
        if self.stroke_counts:
            return {index for index, count in self.stroke_counts.items() if count > 0}
        return {index for index, (payload, _canvas) in self.pages.items() if payload}

    def base(self, source_page, target_page, index: int, alignment: Alignment | None) -> CanvasTransform:
        canvas = self.pages[index][1]
        return canvas_transform(
            source_page, target_page, canvas, alignment,
            target_canvas_width=canvas[0] if self.fixed_canvas_width else None,
        )


def compose_slot_ink(
    ink: SourceInk,
    source_document,
    target_document,
    target_index: int,
    sources: Sequence[int],
    alignment: Alignment | None,
    *,
    relocate: bool,
):
    """새 쪽 하나에 얹을 필기 바이트(옛 쪽들을 객체마다 옮겨 합친 것)와 배치. 필기가 없으면 ``(None, None)``.

    저장과 미리보기가 이 함수 하나를 쓴다 — 화면에 보인 자리와 파일 속 자리가 어긋날 수 없다(원칙 5).
    """
    from .page_ink import Contribution, compose_page

    present = [index for index in sources if index in ink.pages]
    if not present:
        return None, None
    target_page = target_document[target_index]
    contributions = []
    payloads = []
    for index in present:
        payload, canvas = ink.pages[index]
        base = ink.base(source_document[index], target_page, index, alignment)
        try:
            boxes = ink.codec.boxes(payload)
        except Exception:
            # 객체를 해석하지 못하는 쪽은 예전처럼 쪽 변환 하나로 옮긴다(좌표를 모르는 것은 건드리지 않는다).
            boxes = None
        contributions.append(Contribution(index, source_document[index], canvas, boxes, base))
        payloads.append(payload)
    return compose_page(ink.codec, target_page, payloads, contributions, relocate=relocate)


def preview_slot(
    ink: SourceInk,
    embedded_pdf: bytes,
    target: Path,
    target_index: int,
    sources: Sequence[int],
    inspection: "TransferInspection",
    render_ink: Callable[[bytes | None, int, int, tuple[float, float]], tuple[bytes, int]],
    *,
    source_label: str,
    error: type[Exception],
    max_side: int = 900,
) -> tuple[bytes, bytes, bytes, int]:
    """새 쪽 하나에 옛 쪽들(``sources`` — 대표가 맨 앞)의 필기를 얹은 모습. 저장과 같은 :func:`compose_slot_ink` 를 쓴다.

    ``render_ink(바이트, 폭, 높이, 새 캔버스 크기)`` 만 형식마다 다르다. 돌려주는 것은 (옛 배경을 새 쪽 틀에 맞춘 것,
    새 쪽, 필기 투명 그림, 그린 획 수).
    """
    from io import BytesIO

    from PIL import Image

    from .alignment import render_comparison
    from . import pdf as pymupdf

    with open_pdf(embedded_pdf, source_label, error=error) as source_document, \
            open_pdf(target, "대상 PDF", error=error) as target_document:
        if not 0 <= target_index < target_document.page_count:
            raise error(f"새 PDF에 없는 쪽 번호입니다: {target_index + 1}")
        if any(not 0 <= index < source_document.page_count for index in sources):
            raise error("원본 문서에 없는 쪽 번호입니다.")
        alignment = inspection.alignment
        machine = {(pair.source_index, pair.target_index) for pair in (inspection.match.matched_pairs
                                                                         if inspection.match else ())}
        if sources and (sources[0], target_index) not in machine:
            # 사람이 고른 짝은 그 짝으로 위치를 다시 잰다(저장도 고친 계획의 짝으로 잰다).
            alignment = alignment_for_pairs(source_document, target_document, [(sources[0], target_index)],
                                            error=error)
        if sources:
            before, after = render_comparison(source_document, target_document, alignment, sources[0],
                                              max_side, target_page_index=target_index)
        else:
            page = target_document[target_index]
            scale = min(max_side / max(page.rect.width, page.rect.height), 3.0)
            after = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
            before = after
        with Image.open(BytesIO(after)) as image:
            width, height = image.size
        payload, _placement = compose_slot_ink(
            ink, source_document, target_document, target_index, sources, alignment,
            relocate=True,
        )
        if payload is None:
            layer, count = render_ink(None, width, height, (1.0, 1.0))
            return before, after, layer, count
        first = next(index for index in sources if index in ink.pages)
        base = ink.base(source_document[first], target_document[target_index], first, alignment)
        layer, count = render_ink(payload, width, height, (base.target_width, base.target_height))
        return before, after, layer, count


def panel_ink_sources(ink: SourceInk, source_document) -> tuple[int, ...]:
    """옛 파일이 Sleek 필기본일 때 오른쪽 필기 칸 위에 손필기가 있는 옛 쪽(0부터). 세 형식이 같은 규칙이다."""
    from .sleek_notes import original_box

    found = []
    for index, (payload, canvas) in sorted(ink.pages.items()):
        if not 0 <= index < source_document.page_count or not payload:
            continue
        page = source_document[index]
        box = original_box(page)
        if box is None:
            continue
        try:
            boxes = ink.codec.boxes(payload)
        except Exception:
            continue
        edge = (box.x1 + _PANEL_EDGE_SLACK) * canvas[0] / page.rect.width
        if any(item is not None and item[2] > edge for item in boxes):
            found.append(index)
    return tuple(found)


def inspect_pdfs(
    *,
    source_name: str,
    target_name: str,
    embedded_pdf: bytes,
    target: Path,
    ink: SourceInk,
    source_label: str,
    error: type[Exception],
    progress: Callable[[str], None] | None,
    annotated_page_count: int,
    stroke_cache_count: int,
    embedded_pdf_name: str,
    source_page_count: int,
    target_size: int,
    source_order: tuple[dict, ...] = (),
) -> TransferInspection:
    """세 형식이 같은 길로 분석한다 — 짝짓기·칸 손필기·필기본 갱신 판정이 형식과 무관하다(요청 6)."""
    inked = ink.inked()
    planned = plan_transfer(embedded_pdf, target, source_label=source_label, error=error,
                            progress=progress, inked=inked)
    notes = planned.notes
    panel: tuple[int, ...] = ()
    crowded: list[int] = []
    relocated: list[int] = []
    source_document = open_pdf(embedded_pdf, source_label, error=error)
    try:
        if notes is None or notes.mode != NOTES:
            panel = panel_ink_sources(ink, source_document)
        else:
            # 필기본 → 필기본: 칸 손필기는 여백으로 옮긴다. 자리가 모자란 새 쪽만 사람에게 보인다.
            with open_pdf(target, "대상 PDF", error=error) as target_document:
                for pair in planned.match.matched_pairs:
                    sources = [pair.source_index, *notes.merged.get(pair.target_index, ())]
                    if not any(ink.pages.get(index, (b"",))[0] for index in sources):
                        continue
                    _payload, placement = compose_slot_ink(
                        ink, source_document, target_document, pair.target_index, sources,
                        planned.alignment, relocate=True,
                    )
                    if placement is not None and placement.crowded:
                        crowded.append(pair.target_index)
                    if placement is not None and placement.moved:
                        relocated.append(pair.target_index)
    finally:
        source_document.close()

    reorder = planned.reorder
    return TransferInspection(
        source_name=source_name,
        target_name=target_name,
        page_count=planned.page_count,
        annotated_page_count=annotated_page_count,
        stroke_cache_count=stroke_cache_count,
        embedded_pdf_name=embedded_pdf_name,
        target_size=target_size,
        source_page_count=source_page_count,
        mode=planned.mode,
        alignment=planned.alignment,
        match=planned.match,
        source_order=source_order,
        panel_ink_sources=panel,
        moved_sources=reorder.moved,
        pair_candidates=tuple(sorted(reorder.candidates.items())),
        closest_targets=tuple(sorted(reorder.closest.items())),
        prints=reorder.prints,
        notes_mode=notes.mode if notes else "",
        merged=tuple(sorted(notes.merged.items())) if notes else (),
        dropped_sources=notes.dropped if notes else (),
        resized_runs=notes.resized_runs if notes else 0,
        crowded_targets=tuple(sorted(crowded)),
        relocated_targets=tuple(sorted(relocated)),
        inked_sources=tuple(sorted(inked)),
    )


def alignment_for_plan(
    embedded_pdf: bytes,
    target: Path,
    plan: PagePlan,
    *,
    source_label: str = "내장 PDF",
    error: type[Exception] = HandwritingTransferError,
) -> Alignment | None:
    """사용자가 고친 행 계획의 실제 쪽 짝으로 정렬을 다시 계산한다."""
    source_document = open_pdf(embedded_pdf, source_label, error=error)
    try:
        target_document = open_pdf(target, "대상 PDF", error=error)
    except Exception:
        source_document.close()
        raise
    with source_document, target_document:
        pairs = [
            (slot.source_index, slot.target_index)
            for slot in plan.slots
            if slot.source_index is not None and slot.target_index is not None
        ]
        return alignment_for_pairs(
            source_document,
            target_document,
            pairs,
            error=error,
        )


def alignment_for_pairs(
    source_document,
    target_document,
    pairs: Sequence[tuple[int, int]],
    *,
    error: type[Exception] = HandwritingTransferError,
) -> Alignment | None:
    """확정된 쪽 짝에 필요한 필기 캔버스 역변환을 검증한다."""
    source_geometry = geometry(source_document)
    target_geometry = geometry(target_document)
    same_geometry = all(
        not geometry_mismatches(
            [source_geometry[source_index]],
            [target_geometry[target_index]],
        )
        for source_index, target_index in pairs
    )
    alignment = estimate_alignment(
        source_document, target_document, _alignment_pairs(source_document, target_document, pairs)
    )
    if alignment is None:
        if not same_geometry:
            raise error(
                "페이지 크기가 다른데 확인한 쪽의 본문 영역을 찾지 못해 필기 좌표를 옮길 수 없습니다."
            )
        return None
    if same_geometry and not (alignment.improves and alignment.axes_agree):
        return None
    return alignment
