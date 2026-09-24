"""Sleek 필기본 쪽에서 원래 강의록 쪽이 놓인 상자를 찾는다.

Sleek 필기본(``<강의> 필기.pdf``)은 강의록 쪽을 왼쪽 위 ``(0, 0, 원래 폭, 원래 높이)`` 에 배율 1로
끼워 넣고(Form XObject), 오른쪽에 쪽 높이 전체를 덮는 필기 칸을 칠한다. 필기가 길면 쪽이 아래로만
늘어나고 원래 쪽 자리는 그대로다. 2026-09-16 첫 판부터 이 배치는 같다.

쪽 짝짓기·정렬이 필기 칸의 글까지 본문으로 보면 족첵 쪽과 전혀 달라 보인다(실측: 67쪽 중 25쪽만
짝지음). 그래서 두 흔적 — 왼쪽 위에 붙은 끼운 쪽, 그 오른쪽 끝에서 쪽 오른쪽 끝까지 쪽 높이 전체를
채운 사각형 — 이 모두 있을 때만 필기본 쪽으로 보고 원래 쪽 상자로 좁힌다. 둘 중 하나라도 없으면
일반 쪽이다.
"""
from __future__ import annotations

import re

_TOLERANCE = 1.0
_MIN_ORIGINAL_SHARE = 0.3
_RECT = re.compile(rb"(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+re\b")


def _placed_forms(page) -> list[tuple[float, float]]:
    """왼쪽 위에 붙은 끼운 쪽들의 (오른쪽 끝, 아래 끝) — 쪽 좌표(위가 0)."""
    rect = page.rect
    found = []
    for _xref, _name, invoker, bbox in page.get_xobjects():
        if invoker != 0:
            continue
        x0, y0, x1, y1 = bbox
        top, bottom = rect.height - y1, rect.height - y0
        if (abs(x0) <= _TOLERANCE and abs(top) <= _TOLERANCE
                and rect.width * _MIN_ORIGINAL_SHARE < x1 < rect.width - _TOLERANCE
                and bottom > _TOLERANCE):
            found.append((x1, bottom))
    return found


def _panel_lefts(page) -> list[float]:
    """쪽 오른쪽 끝까지, 쪽 높이 전체를 채운 사각형의 왼쪽 끝."""
    rect = page.rect
    lefts = []
    for match in _RECT.finditer(page.read_contents()):
        x, y, width, height = map(float, match.groups())
        if (abs(x + width - rect.width) <= _TOLERANCE and abs(y) <= _TOLERANCE
                and abs(height - rect.height) <= _TOLERANCE and width > 0):
            lefts.append(x)
    return lefts


def original_box(page):
    """Sleek 필기본 쪽이면 원래 쪽 상자(``Rect``), 아니면 ``None``."""
    try:
        if page.rotation:
            return None
        forms = _placed_forms(page)
        if not forms:
            return None
        lefts = _panel_lefts(page)
    except Exception:
        return None
    for right, bottom in forms:
        if any(abs(left - right) <= _TOLERANCE for left in lefts):
            from . import pdf as pymupdf

            return pymupdf.Rect(0, 0, right, bottom)
    return None


def content_rect(page):
    """본문 비교에 쓸 영역: 필기본 쪽이면 원래 쪽 상자, 아니면 쪽 전체."""
    return original_box(page) or page.rect


__all__ = ["content_rect", "original_box"]
