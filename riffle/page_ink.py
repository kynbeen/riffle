"""새 쪽 하나에 얹을 손필기의 **객체마다 변환**을 정한다(명세 2026-09-25-03). 형식과 무관하다.

기본은 쪽 변환 하나(강의록 영역 기준 — :mod:`ink_transform`)다. Sleek 필기본 → Sleek 필기본이면 더해서:

- **강의록 영역 안의 획**은 쪽 변환 그대로 — 같은 강의록 쪽의 같은 자리에 간다.
- **강의록 영역 밖의 획**(오른쪽 필기 칸, 쪽이 늘어나 생긴 왼쪽 아래)은 가까운 것끼리 한 **덩이**로 묶어 새 쪽의
  **여백**으로 옮긴다. 여백 = 강의록 영역 밖에서 Sleek 글과 먼저 자리 잡은 덩이가 없는 곳.
  - 덩이 밑의 글이 옛·새 쪽에서 **같으면** 제자리에 둔다 — 그 글에 친 밑줄·동그라미다.
  - 아니면 원래 자리에 가장 가까운 빈자리로, 모양·크기 그대로. 칸에 있던 덩이는 칸 안에서 먼저 찾는다.
  - 크기 그대로 들어갈 곳이 없으면 90%부터 50%까지 줄여 본다. 그래도 없으면 겹침이 가장 적은 자리에 두고
    ``crowded`` 로 알린다 — 화면이 사람에게 보인다(사람을 부르는 경우).

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
        self.cols = max(1, math.ceil(width / _CELL))
        self.rows = max(1, math.ceil(height / _CELL))
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


def _free(rect: Box, regions: list[Box], blocked: list[Box]) -> bool:
    """``rect`` 가 여백 조각 하나 안에 들어가고 막힌 곳과 겹치지 않는가 — 격자 없이 정확히."""
    inside = any(r[0] <= rect[0] and r[1] <= rect[1] and rect[2] <= r[2] and rect[3] <= r[3] for r in regions)
    return inside and not any(
        b[0] < rect[2] and rect[0] < b[2] and b[1] < rect[3] and rect[1] < b[3] for b in blocked
    )


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
    target = page_layout(target_page) if relocate else None
    if target is None:
        return Placement(per_source)

    width, height = float(target_page.rect.width), float(target_page.rect.height)
    panel_only, anywhere = _regions(target, width, height)
    text = [(x0 - _TEXT_PAD, y0 - _TEXT_PAD, x1 + _TEXT_PAD, y1 + _TEXT_PAD)
            for x0, y0, x1, y1 in panel_text_boxes(target_page, target)]
    placed: list[Box] = []
    crowded = False
    moved = 0

    for number, contribution in enumerate(contributions):
        source = page_layout(contribution.source_page)
        if source is None or contribution.boxes is None:
            continue
        page_w = max(float(contribution.source_page.rect.width), 1e-6)
        page_h = max(float(contribution.source_page.rect.height), 1e-6)
        sx, sy = contribution.canvas[0] / page_w, contribution.canvas[1] / page_h
        base = contribution.base
        tx = base.target_width / width
        ty = base.target_height / height
        margin: list[tuple[int, Box]] = []
        for index, box in enumerate(contribution.boxes):
            if box is None:
                continue
            points = (box[0] / sx, box[1] / sy, box[2] / sx, box[3] / sy)
            cx, cy = (points[0] + points[2]) / 2, (points[1] + points[3]) / 2
            lecture = source.lecture
            if lecture is None or cx > lecture.x1 + _EDGE_SLACK or cy > lecture.y1 + _EDGE_SLACK:
                margin.append((index, points))
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
            spot, scale = None, 1.0
            for regions in ([panel_only, anywhere] if in_panel else [anywhere]):
                grid = _Grid(width, height, regions, blocked)
                for scale in _SCALES:
                    spot = grid.find(size[0] * scale, size[1] * scale, (here[0], here[1]))
                    if spot is not None:
                        break
                if spot is not None:
                    break
            if spot is None:
                crowded = True
                scale = _SCALES[-1]
                spot = _Grid(width, height, anywhere, blocked).find(
                    size[0] * scale, size[1] * scale, (here[0], here[1]), overlap=True) or (here[0], here[1])
            new_box = (spot[0], spot[1], spot[0] + size[0] * scale, spot[1] + size[1] * scale)
            placed.append(new_box)
            if abs(spot[0] - here[0]) < 0.01 and abs(spot[1] - here[1]) < 0.01 and scale == 1.0:
                continue
            moved += 1
            relocation = _compose(base, scale, (left, top), (spot[0] * tx, spot[1] * ty))
            for index in group:
                per_source[number][index] = relocation
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
