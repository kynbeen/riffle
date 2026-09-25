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
from dataclasses import dataclass

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


# ---------------------------------------------------------------- 필기본 파일 전체(명세 2026-09-25-03)

@dataclass(frozen=True)
class NotesPage:
    """필기본 쪽 하나의 배치. ``lecture`` 는 끼운 강의록 쪽 상자 — 맨 앞 전용 쪽이면 ``None``.

    ``panel_left`` 부터 쪽 오른쪽 끝까지가 필기 칸이다. 강의록 영역 밖(칸과, 쪽이 늘어나 생긴 왼쪽 아래)이
    손필기를 옮길 **여백**의 후보다.
    """

    lecture: object | None
    panel_left: float
    key: str | None = None


def page_layout(page, *, with_key: bool = False) -> NotesPage | None:
    """필기본 쪽이면 배치, 아니면 ``None``. 맨 앞 전용 쪽(「강의를 시작하며」)은 칸만 있고 강의록 쪽이 없다.

    ``with_key`` 면 끼운 강의록 쪽의 내용 열쇠(:func:`lecture_key`)도 붙인다.
    """
    box = original_box(page)
    if box is not None:
        return NotesPage(box, box.x1, lecture_key(page) if with_key else None)
    try:
        if page.rotation or _placed_forms(page):
            return None
        lefts = [left for left in _panel_lefts(page) if page.rect.width * _MIN_ORIGINAL_SHARE < left]
    except Exception:
        return None
    return NotesPage(None, min(lefts)) if lefts else None


def is_notes_document(document) -> bool:
    """쪽의 절반 이상이 필기본 쪽이면 필기본 파일이다. 스위치를 두지 않는다(원칙 4)."""
    count = document.page_count
    if count < 1:
        return False
    found = sum(page_layout(document[index]) is not None for index in range(count))
    return found * 2 >= count


_REFERENCE = re.compile(r"(\d+) 0 R")
_KEY_OBJECT_LIMIT = 4000


def lecture_key(page) -> str | None:
    """끼운 강의록 쪽의 **내용** 열쇠 — 끼운 틀이 가리키는 객체를 모두 따라가 바이트째 해시한다.

    Sleek 은 필기가 길면 같은 강의록 쪽을 이어서 다시 싣는다. 그 사본들은 그림으로 비교하면 렌더 흔들림 때문에
    다르게 나오지만(실측 병리학 1주차(1): 그림 해시로 0묶음), 내용 바이트는 같다(12묶음 모두 잡힘). 객체 번호는
    파일마다 달라 지우고 모양과 스트림만 본다.
    """
    import hashlib

    document = page.parent
    forms = [xref for xref, _name, invoker, bbox in page.get_xobjects()
             if invoker == 0 and abs(bbox[0]) <= _TOLERANCE]
    if not forms:
        return None
    digest = hashlib.sha1()
    seen: set[int] = set()
    stack = [forms[0]]
    while stack and len(seen) < _KEY_OBJECT_LIMIT:
        xref = stack.pop()
        if xref in seen or xref <= 0:
            continue
        seen.add(xref)
        try:
            body = document.xref_object(xref, compressed=True)
            digest.update(_REFERENCE.sub("R", body).encode("latin-1", "replace"))
            if document.xref_is_stream(xref):
                digest.update(document.xref_stream_raw(xref) or b"")
        except Exception:
            return None
        stack.extend(reversed([int(number) for number in _REFERENCE.findall(body)]))
    return digest.hexdigest()


def panel_text_boxes(page, layout: NotesPage) -> list[tuple[float, float, float, float]]:
    """강의록 영역 밖에 있는 Sleek 글 줄 상자(쪽 좌표). 여백을 찾을 때 비켜야 할 곳이다."""
    boxes = []
    lecture = layout.lecture
    for x0, y0, x1, y1, *_rest in page.get_text("words"):
        if lecture is not None and x1 <= lecture.x1 + _TOLERANCE and y1 <= lecture.y1 + _TOLERANCE:
            continue
        boxes.append((x0, y0, x1, y1))
    return boxes


def panel_extent(page, layout: NotesPage) -> float:
    """필기 칸의 글이 실제로 끝나는 높이(쪽 좌표). 반복 묶음 안에서 필기 흐름의 **상대 위치**를 잴 때 쓴다."""
    bottoms = [y1 for x0, _y0, _x1, y1 in panel_text_boxes(page, layout) if x0 >= layout.panel_left]
    return max(bottoms, default=0.0)


__all__ = [
    "NotesPage", "content_rect", "is_notes_document", "lecture_key", "original_box",
    "page_layout", "panel_extent", "panel_text_boxes",
]
