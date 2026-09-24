"""PDF 엔진 접근점.

모든 모듈은 ``pymupdf`` 를 직접 부르지 않고 이 모듈을 거친다. 한때 Android 용 호환 계층을 갈아 끼우던
자리였고(2026-09-24 Android 를 걷었다), 지금은 회전된 쪽을 안전하게 배치하는 도우미를 한곳에 둔다.
"""
from __future__ import annotations

import pymupdf as _backend

open = _backend.open
Rect = _backend.Rect
Matrix = _backend.Matrix
FileDataError = _backend.FileDataError
csGRAY = _backend.csGRAY
csRGB = _backend.csRGB
Point = _backend.Point


def show_pdf_page(page, destination, source, page_index: int) -> None:
    """Place the displayed page without changing the caller's source document."""
    rotation = source[page_index].rotation
    if not rotation:
        page.show_pdf_page(destination, source, page_index, keep_proportion=True, clip=None)
        return
    # MuPDF's placement coordinates exclude /Rotate. Copy one page and apply
    # its display rotation explicitly, preserving the original crop box.
    with open() as unrotated:
        unrotated.insert_pdf(source, from_page=page_index, to_page=page_index)
        unrotated[0].set_rotation(0)
        page.show_pdf_page(destination, unrotated, 0, keep_proportion=True, rotate=-rotation)


def __getattr__(name: str):
    """지정되지 않은 모든 pymupdf 속성을 그대로 전달한다."""
    return getattr(_backend, name)


__all__ = ["open", "Rect", "Matrix", "Point", "FileDataError", "csGRAY", "csRGB", "show_pdf_page"]
