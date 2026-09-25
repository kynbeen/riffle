"""새 쪽 하나에 얹을 손필기의 **객체마다 변환**을 정한다(명세 2026-09-25-03). 형식과 무관하다.

기본은 쪽 변환 하나(강의록 영역 기준 — :mod:`ink_transform`)다. Sleek 필기본 → Sleek 필기본이면 더해서:

- **강의록 영역 안의 획**은 쪽 변환 그대로 — 같은 강의록 쪽의 같은 자리에 간다.
- **강의록 영역 밖의 획**(오른쪽 필기 칸, 쪽이 늘어나 생긴 왼쪽 아래)은 가까운 것끼리 한 **덩이**로 묶어 새 쪽의
  **여백**으로 옮긴다. 여백 = 강의록 영역 밖에서 Sleek 글과 먼저 자리 잡은 덩이가 없는 곳.
  - 덩이 밑의 글이 옛·새 쪽에서 **같으면** 제자리에 둔다 — 그 글에 친 밑줄·동그라미다.
  - 아니면 원래 자리에 가장 가까운 빈자리로, 모양·크기 그대로. 칸에 있던 덩이는 칸 안에서 먼저 찾는다.
  - 여백에 자리가 모자라면(90%·80% 로 줄여도) **강의록 영역의 빈칸**으로 옮긴다(사용자 결정 2026-09-25). 빈칸은 쪽을
    그려 바탕색과 다른 칸(글·그림·도형)을 피하고, 이 쪽에 얹히는 강의록 손필기도 피한다. 그래도 없으면 여백·강의록 빈칸을
    50% 까지 줄여 찾고, 끝내 없으면 겹침이 가장 적은 자리에 두고 ``crowded`` 로 알린다(사람을 부르는 경우).

같은 입력이면 늘 같은 답이다 — 미리보기와 저장이 이 함수 하나를 쓴다(원칙 5).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from .ink_layer import Box, InkCodec
from .ink_transform import CanvasTransform
from .sleek_notes import NotesPage, page_layout, panel_text_boxes

_EDGE_SLACK = 2.0          # 강의록 영역 경계 너머 이만큼(pt)은 강의록 획으로 본다
_CLUSTER_GAP = 12.0        # 이보다 가까운 칸 획은 한 덩이(pt)
_TEXT_PAD = 2.0            # 글 줄 둘레로 비워 둘 폭(pt)
_PLACED_PAD = 3.0          # 먼저 자리 잡은 덩이 둘레(pt)
_CELL = 3.0                # 빈자리 찾기 격자(pt)
_SCALES = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)


@dataclass(frozen=True)
class Contribution:
    """새 쪽에 손필기를 얹는 옛 쪽 하나."""

    source_index: int
    source_page: object                 # 옛 PDF 쪽
    canvas: tuple[float, float]         # 옛 쪽 필기 캔버스 크기
    boxes: Sequence[Box | None] | None  # 객체마다 상자(옛 캔버스 좌표). 객체를 해석하지 못하면 None — 쪽 변환 하나
    base: CanvasTransform               # 옛 캔버스 → 새 캔버스(강의록 영역 기준)


@dataclass(frozen=True)
class Placement:
    per_source: list[list[CanvasTransform] | None]
    crowded: bool = False                               # 여백이 모자라 글과 겹친 덩이가 있다
    moved: int = 0                                      # 여백으로 옮긴 덩이 수
    placed: list[Box] = field(default_factory=list)     # 옮긴 덩이의 새 자리(새 쪽 pt)


def _union(boxes: list[Box]) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _clusters(boxes: list[tuple[int, Box]]) -> list[list[int]]:
    """가까운 상자끼리 묶는다(서로 ``_CLUSTER_GAP`` 안이면 한 덩이). 덩이는 위→아래, 왼→오 순."""
    parent = list(range(len(boxes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    half = _CLUSTER_GAP / 2
    for i, (_a, a) in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j][1]
            if (a[0] - half <= b[2] + half and b[0] - half <= a[2] + half
                    and a[1] - half <= b[3] + half and b[1] - half <= a[3] + half):
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(boxes)):
        groups.setdefault(find(i), []).append(i)
    ordered = sorted(groups.values(), key=lambda group: (_union([boxes[i][1] for i in group])[1],
                                                         _union([boxes[i][1] for i in group])[0]))
    return [[boxes[i][0] for i in group] for group in ordered]


_WORD_REACH = 6.0          # 덩이 둘레 이만큼(pt) 안에 걸친 낱말을 "밑의 글" 로 본다 — 글 아래 밑줄도 잡히게


def _words(page, rect: Box) -> list[str]:
    """덩이에 걸친 Sleek 글 낱말(읽는 순서). 옛·새 쪽에서 같으면 그 글에 친 표시다."""
    x0, y0, x1, y1 = (rect[0] - _WORD_REACH, rect[1] - _WORD_REACH, rect[2] + _WORD_REACH, rect[3] + _WORD_REACH)
    try:
        words = page.get_text("words")
    except Exception:
        return []
    return [word[4] for word in words if word[0] < x1 and x0 < word[2] and word[1] < y1 and y0 < word[3]]


class _Grid:
    """새 쪽 위의 막힌 칸(여백 밖·글·먼저 놓은 덩이). 사각형 합으로 빈자리를 바로 잰다."""

    def __init__(self, width: float, height: float, regions: list[Box], blocked: list[Box]):
        self.cols = max(1, math.floor(width / _CELL))
        self.rows = max(1, math.floor(height / _CELL))
        cells = [[1] * self.cols for _ in range(self.rows)]
        for rect in regions:
            c0, r0, c1, r1 = self._inner(rect)
            for row in range(r0, r1):
                line = cells[row]
                for column in range(c0, c1):
                    line[column] = 0
        for rect in blocked:
            c0, r0, c1, r1 = self._outer(rect)
            for row in range(r0, r1):
                line = cells[row]
                for column in range(c0, c1):
                    line[column] = 1
        self.sums = [[0] * (self.cols + 1) for _ in range(self.rows + 1)]
        for row in range(self.rows):
            running = 0
            above, here = self.sums[row], self.sums[row + 1]
            line = cells[row]
            for column in range(self.cols):
                running += line[column]
                here[column + 1] = above[column + 1] + running

    def _inner(self, rect: Box) -> tuple[int, int, int, int]:
        return (max(0, math.ceil(rect[0] / _CELL)), max(0, math.ceil(rect[1] / _CELL)),
                min(self.cols, math.floor(rect[2] / _CELL)), min(self.rows, math.floor(rect[3] / _CELL)))

    def _outer(self, rect: Box) -> tuple[int, int, int, int]:
        return (max(0, math.floor(rect[0] / _CELL)), max(0, math.floor(rect[1] / _CELL)),
                min(self.cols, math.ceil(rect[2] / _CELL)), min(self.rows, math.ceil(rect[3] / _CELL)))

    def _blocked(self, column: int, row: int, width: int, height: int) -> int:
        s = self.sums
        return s[row + height][column + width] - s[row][column + width] - s[row + height][column] + s[row][column]

    def find(self, width: float, height: float, want: tuple[float, float], *, overlap: bool = False):
        """``want``(왼쪽 위, pt)에 가장 가까운 빈자리의 왼쪽 위. ``overlap`` 이면 겹침이 가장 적은 자리."""
        w, h = max(1, math.ceil(width / _CELL)), max(1, math.ceil(height / _CELL))
        if w > self.cols or h > self.rows:
            return None
        wc = min(max(0, round(want[0] / _CELL)), self.cols - w)
        wr = min(max(0, round(want[1] / _CELL)), self.rows - h)
        best = None
        if not overlap:
            # 원하는 자리에서 바깥으로 고리를 넓혀 가며 찾고, 더 가까운 답이 나올 수 없으면 멈춘다.
            limit = max(self.cols, self.rows)
            for radius in range(limit + 1):
                if best is not None and radius * radius > best[0]:
                    break
                for row in range(wr - radius, wr + radius + 1):
                    if row < 0 or row > self.rows - h:
                        continue
                    edge = row in (wr - radius, wr + radius)
                    columns = range(wc - radius, wc + radius + 1) if edge else (wc - radius, wc + radius)
                    for column in columns:
                        if column < 0 or column > self.cols - w:
                            continue
                        if self._blocked(column, row, w, h) == 0:
                            score = (column - wc) ** 2 + (row - wr) ** 2
                            if best is None or score < best[0]:
                                best = (score, column, row)
            return None if best is None else (best[1] * _CELL, best[2] * _CELL)
        for row in range(self.rows - h + 1):
            for column in range(self.cols - w + 1):
                score = (self._blocked(column, row, w, h), (column - wc) ** 2 + (row - wr) ** 2)
                if best is None or score < best[0]:
                    best = (score, column, row)
        return None if best is None else (best[1] * _CELL, best[2] * _CELL)


def _regions(layout: NotesPage, width: float, height: float) -> tuple[list[Box], list[Box]]:
    """(칸만, 칸 + 늘어난 왼쪽 아래) 여백 영역."""
    panel = [(layout.panel_left + 1.0, 0.0, width, height)]
    if layout.lecture is None:
        return panel, [(0.0, 0.0, width, height)]
    below = []
    if height > layout.lecture.y1 + 4.0:
        below = [(0.0, layout.lecture.y1 + 1.0, layout.panel_left - 1.0, height)]
    return panel, panel + below


_PAINT_TOLERANCE = 14      # 바탕색과 이만큼 넘게 다르면 무언가 그려진 칸


def _painted(page, box) -> list[Box]:
    """강의록 영역에서 그림·글·도형이 있는 칸(쪽 좌표). 쪽을 격자 한 칸에 두 픽셀로 그려, 바탕색(가장 흔한 밝기)과
    다른 픽셀이 하나라도 있는 칸을 막는다. 글 줄만 보면 슬라이드의 그림 위에 손필기를 얹게 된다."""
    from . import pdf as pymupdf

    scale = 2.0 / _CELL
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=box, colorspace=pymupdf.csGRAY, alpha=False)
    width, height, samples = pixmap.width, pixmap.height, pixmap.samples
    if width < 2 or height < 2:
        return [tuple(box)]
    counts = [0] * 256
    for value in samples:
        counts[value] += 1
    background = max(range(256), key=counts.__getitem__)
    ink = bytes(1 if abs(value - background) > _PAINT_TOLERANCE else 0 for value in range(256))
    marked = samples.translate(ink)
    cols, rows = (width + 1) // 2, (height + 1) // 2
    rects: list[Box] = []
    for row in range(rows):
        lines = [marked[y * width:(y + 1) * width] for y in (2 * row, 2 * row + 1) if y < height]
        start = None
        for column in range(cols + 1):
            busy = column < cols and any(line[2 * column:2 * column + 2].find(1) >= 0 for line in lines)
            if busy and start is None:
                start = column
            elif not busy and start is not None:
                rects.append((box.x0 + start * _CELL, box.y0 + row * _CELL,
                              box.x0 + column * _CELL, box.y0 + (row + 1) * _CELL))
                start = None
    return rects


def _free(rect: Box, regions: list[Box], blocked: list[Box]) -> bool:
    """``rect`` 가 여백 조각 하나 안에 들어가고 막힌 곳과 겹치지 않는가 — 격자 없이 정확히."""
    inside = any(r[0] <= rect[0] and r[1] <= rect[1] and rect[2] <= r[2] and rect[3] <= r[3] for r in regions)
    return inside and not any(
        b[0] < rect[2] and rect[0] < b[2] and b[1] < rect[3] and rect[1] < b[3] for b in blocked
    )


_INSIDE_SLACK = 2.0         # 새 캔버스 px. 이만큼은 쪽 밖으로 나가도 둔다(펜 굵기·반올림)
_INSIDE_MARGIN = 6.0        # 쪽 안으로 밀어 넣을 때 가장자리에서 띄울 폭(새 캔버스 px)


def _keep_inside(per_source: list, contributions: Sequence[Contribution]) -> int:
    """쪽 밖으로 나가는 객체를 쪽 안으로 최소한만 밀어 넣는다(쪽보다 크면 줄여서). 옮긴 객체 수를 돌려준다.

    가운데가 강의록 영역 안이라 강의록 획으로 옮긴 큰 획이 칸이나 늘어난 아래로 삐져나가 있으면, 칸이 없거나 더 짧은 새 쪽에서
    그 부분이 쪽 밖에 놓였다 — 보이지도 편집되지도 않는다(퍼징 2026-09-26, 원칙 7). 여백 찾기의 모든 결과에도 마지막으로 건다.
    """
    moved = 0
    for transforms, contribution in zip(per_source, contributions):
        if transforms is None:
            continue
        for index, box in enumerate(contribution.boxes):
            if box is None:
                continue
            transform = transforms[index]
            width, height = transform.target_width, transform.target_height
            x0, y0, x1, y1 = transform.rect(box)
            if x0 >= -_INSIDE_SLACK and y0 >= -_INSIDE_SLACK and x1 <= width + _INSIDE_SLACK and y1 <= height + _INSIDE_SLACK:
                continue
            # 가장자리에서 조금 안쪽을 겨눈다 — Samsung Notes 는 점 간격을 1/32px 로 반올림해 적어, 점이 많은 획을 줄이면
            # 반올림이 쌓여 끝이 몇 px 밀린다(퍼징: 딱 맞춰 넣은 획이 3px 삐져나감).
            room_x, room_y = width - 2 * _INSIDE_MARGIN, height - 2 * _INSIDE_MARGIN
            span_x, span_y = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
            scale = min(1.0, room_x / span_x, room_y / span_y)
            new_x = min(max(x0, _INSIDE_MARGIN), width - _INSIDE_MARGIN - span_x * scale)
            new_y = min(max(y0, _INSIDE_MARGIN), height - _INSIDE_MARGIN - span_y * scale)
            transforms[index] = _compose(transform, scale, (x0, y0), (new_x, new_y))
            moved += 1
    return moved


def _compose(base: CanvasTransform, scale: float, old: tuple[float, float], new: tuple[float, float]) -> CanvasTransform:
    """``base`` 뒤에 (``old`` 를 ``new`` 로 옮기며 ``scale`` 배) 를 잇는다 — 새 캔버스 좌표."""
    return CanvasTransform(
        scale_x=scale * base.scale_x,
        scale_y=scale * base.scale_y,
        offset_x=scale * (base.offset_x - old[0]) + new[0],
        offset_y=scale * (base.offset_y - old[1]) + new[1],
        target_width=base.target_width,
        target_height=base.target_height,
    )


def place_ink(target_page, contributions: Sequence[Contribution], *, relocate: bool) -> Placement:
    per_source = [None if c.boxes is None else [c.base] * len(c.boxes) for c in contributions]
    if not relocate or not any(c.boxes is not None and page_layout(c.source_page) is not None for c in contributions):
        # 옛 쪽이 필기본이 아니면 칸 손필기가 없다 — 쪽 변환 하나. 그래도 쪽 밖으로 나가는 획은 쪽 안으로.
        return Placement(per_source, moved=_keep_inside(per_source, contributions))
    target = page_layout(target_page)
    width, height = float(target_page.rect.width), float(target_page.rect.height)
    if target is None:
        # 새 쪽에 필기 칸이 없다(필기본 → 일반 PDF). 칸 손필기를 그대로 옮기면 쪽 밖에 놓여 보이지도 편집되지도 않는다
        # (2026-09-26 사용자 발견). 쪽 전체를 강의록 영역으로 보고 그 빈자리로 옮긴다 — 사람에게는 칸 손필기 카드로 묻는다.
        from . import pdf as pymupdf

        target = NotesPage(pymupdf.Rect(0, 0, width, height), width)
        panel_only, anywhere, text = [], [], []
    else:
        panel_only, anywhere = _regions(target, width, height)
        text = [(x0 - _TEXT_PAD, y0 - _TEXT_PAD, x1 + _TEXT_PAD, y1 + _TEXT_PAD)
                for x0, y0, x1, y1 in panel_text_boxes(target_page, target)]
    placed: list[Box] = []
    crowded = False
    moved = 0

    # 첫 걸음 — 옛 쪽마다 획을 강의록 영역 것과 칸 것으로 가른다. 강의록 영역 획은 새 쪽 어디에 얹히는지도 적어 둔다:
    # 칸 획을 강의록 영역의 빈칸으로 옮길 때 그 위를 덮지 않게.
    sorted_out = []
    lecture_ink: list[Box] = []
    for number, contribution in enumerate(contributions):
        source = page_layout(contribution.source_page)
        if source is None or contribution.boxes is None:
            continue
        page_w = max(float(contribution.source_page.rect.width), 1e-6)
        page_h = max(float(contribution.source_page.rect.height), 1e-6)
        sx, sy = contribution.canvas[0] / page_w, contribution.canvas[1] / page_h
        base = contribution.base
        tx, ty = base.target_width / width, base.target_height / height
        margin: list[tuple[int, Box]] = []
        for index, box in enumerate(contribution.boxes):
            if box is None:
                continue
            points = (box[0] / sx, box[1] / sy, box[2] / sx, box[3] / sy)
            cx, cy = (points[0] + points[2]) / 2, (points[1] + points[3]) / 2
            lecture = source.lecture
            if lecture is None or cx > lecture.x1 + _EDGE_SLACK or cy > lecture.y1 + _EDGE_SLACK:
                margin.append((index, points))
            else:
                x0, y0, x1, y1 = base.rect(box)
                lecture_ink.append((x0 / tx, y0 / ty, x1 / tx, y1 / ty))
        sorted_out.append((number, contribution, source, tx, ty, margin))

    lecture_blank: list[Box] | None = None      # 강의록 영역에서 그림·글이 있는 칸 — 필요할 때 한 번만 그린다

    for number, contribution, source, tx, ty, margin in sorted_out:
        base = contribution.base
        for group in _clusters(margin):
            old_pts = _union([pt for index, pt in margin if index in group])
            canvas_box = _union([contribution.boxes[index] for index in group])
            left, top, right, bottom = base.rect(canvas_box)
            here = (left / tx, top / ty, right / tx, bottom / ty)
            size = (here[2] - here[0], here[3] - here[1])
            said = _words(contribution.source_page, old_pts)
            if said and said == _words(target_page, here):
                placed.append(here)          # 같은 글에 친 밑줄·동그라미 — 제자리
                continue
            in_panel = (old_pts[0] + old_pts[2]) / 2 >= source.panel_left - _EDGE_SLACK
            blocked = text + [(b[0] - _PLACED_PAD, b[1] - _PLACED_PAD, b[2] + _PLACED_PAD, b[3] + _PLACED_PAD)
                              for b in placed]
            if _free(here, panel_only if in_panel else anywhere, blocked):
                placed.append(here)          # 원래 자리가 이미 비어 있다 — 격자로 반올림하지 않고 제자리
                continue
            # 찾는 차례(사용자 결정 2026-09-25): 여백(칸 먼저) 크기 그대로·조금 줄여서 → 강의록 영역의 빈칸 크기 그대로·조금
            # 줄여서 → 둘 다 50% 까지. 크게 줄이기보다 강의록 빈칸이 낫다 — 손필기는 읽혀야 한다.
            margins = [regions for regions in ([panel_only, anywhere] if in_panel else [anywhere]) if regions]
            spot, scale = None, 1.0
            for kind, scales in (("margin", _SCALES[:3]), ("lecture", _SCALES[:3]),
                                 ("margin", _SCALES[3:]), ("lecture", _SCALES[3:])):
                if kind == "lecture":
                    if target.lecture is None:
                        continue
                    if lecture_blank is None:
                        lecture_blank = _painted(target_page, target.lecture)
                    inset = (target.lecture.x0 + _TEXT_PAD, target.lecture.y0 + _TEXT_PAD,
                             target.lecture.x1 - _TEXT_PAD, target.lecture.y1 - _TEXT_PAD)
                    ink = [(b[0] - _PLACED_PAD, b[1] - _PLACED_PAD, b[2] + _PLACED_PAD, b[3] + _PLACED_PAD)
                           for b in lecture_ink]
                    grids = [_Grid(width, height, [inset], blocked + lecture_blank + ink)]
                else:
                    grids = [_Grid(width, height, regions, blocked) for regions in margins]
                for grid in grids:
                    for scale in scales:
                        spot = grid.find(size[0] * scale, size[1] * scale, (here[0], here[1]))
                        if spot is not None:
                            break
                    if spot is not None:
                        break
                if spot is not None:
                    break
            if spot is None:
                crowded = True
                scale = _SCALES[-1]
                last_resort = anywhere or [(0.0, 0.0, width, height)]      # 칸 없는 쪽이면 쪽 전체에서
                spot = _Grid(width, height, last_resort, blocked).find(
                    size[0] * scale, size[1] * scale, (here[0], here[1]), overlap=True) or (here[0], here[1])
            new_box = (spot[0], spot[1], spot[0] + size[0] * scale, spot[1] + size[1] * scale)
            placed.append(new_box)
            if abs(spot[0] - here[0]) < 0.01 and abs(spot[1] - here[1]) < 0.01 and scale == 1.0:
                continue
            moved += 1
            relocation = _compose(base, scale, (left, top), (spot[0] * tx, spot[1] * ty))
            for index in group:
                per_source[number][index] = relocation
    moved += _keep_inside(per_source, contributions)
    return Placement(per_source, crowded, moved, placed)


def compose_page(
    codec: InkCodec,
    target_page,
    payloads: Sequence[bytes],
    contributions: Sequence[Contribution],
    *,
    relocate: bool,
) -> tuple[bytes, Placement]:
    """옛 쪽들의 필기 바이트를 객체마다 옮기고 하나로 합친다. 첫 옛 쪽이 바탕(쪽 머리·ID)이다."""
    placement = place_ink(target_page, contributions, relocate=relocate)
    if len(payloads) > 1 and any(item is None for item in placement.per_source):
        raise ValueError("해석하지 못한 필기가 있어 여러 쪽을 한 쪽에 합칠 수 없습니다.")
    parts = [
        codec.transform(payload, contribution.base, transforms)
        for payload, contribution, transforms in zip(payloads, contributions, placement.per_source)
    ]
    return codec.merge(parts[0], parts[1:]), placement


__all__ = ["Contribution", "Placement", "compose_page", "place_ink"]
