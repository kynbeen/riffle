"""PDF 본문 정렬을 편집 가능한 필기 캔버스 좌표로 뒤집는다."""
from __future__ import annotations

from dataclasses import dataclass

from .alignment import Alignment


@dataclass(frozen=True)
class CanvasTransform:
    """원본 필기 캔버스 좌표를 대상 PDF 캔버스 좌표로 옮기는 상사변환."""

    scale_x: float
    scale_y: float
    offset_x: float
    offset_y: float
    target_width: float
    target_height: float

    @property
    def identity(self) -> bool:
        return (
            abs(self.scale_x - 1.0) <= 1e-6
            and abs(self.scale_y - 1.0) <= 1e-6
            and abs(self.offset_x) <= 1e-4
            and abs(self.offset_y) <= 1e-4
        )

    @property
    def width_scale(self) -> float:
        return (abs(self.scale_x) + abs(self.scale_y)) / 2.0

    def point(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.scale_x * float(x) + self.offset_x,
            self.scale_y * float(y) + self.offset_y,
        )

    def rect(self, values) -> tuple[float, float, float, float]:
        left, top = self.point(values[0], values[1])
        right, bottom = self.point(values[2], values[3])
        return min(left, right), min(top, bottom), max(left, right), max(top, bottom)


def canvas_transform(
    source_page,
    target_page,
    source_canvas: tuple[float, float],
    alignment: Alignment | None,
    *,
    target_canvas_width: float | None = None,
) -> CanvasTransform:
    """PDF 점 좌표와 앱 캔버스 좌표 사이에서 정렬의 역변환을 만든다.

    기본은 원본 쪽의 밀도(캔버스 px / PDF pt)를 대상 쪽에도 그대로 쓴다. ``target_canvas_width``
    를 주면 대상 캔버스 폭을 그 값으로 고정하고 밀도를 거기에 맞춘다 — Samsung Notes 는 PDF 쪽
    폭과 무관하게 캔버스 폭을 노트 폭(1848)으로 둔다.
    """
    source_width = max(float(source_page.rect.width), 1e-6)
    source_height = max(float(source_page.rect.height), 1e-6)
    canvas_width = max(float(source_canvas[0]), 1.0)
    canvas_height = max(float(source_canvas[1]), 1.0)
    density_x = canvas_width / source_width
    density_y = canvas_height / source_height
    target_page_width = max(float(target_page.rect.width), 1e-6)
    if target_canvas_width is None:
        target_x, target_y = density_x, density_y
    else:
        target_x = float(target_canvas_width) / target_page_width
        target_y = target_x * density_y / density_x
    target_width = target_page_width * target_x
    target_height = float(target_page.rect.height) * target_y

    # 원본 캔버스 → 원본 PDF pt(÷원본 밀도) → 정렬 역변환 → 대상 캔버스(×대상 밀도)
    scale = 1.0 if alignment is None else max(float(alignment.scale), 1e-9)
    offset_x = 0.0 if alignment is None else float(alignment.offset_x)
    offset_y = 0.0 if alignment is None else float(alignment.offset_y)
    return CanvasTransform(
        scale_x=target_x / (density_x * scale),
        scale_y=target_y / (density_y * scale),
        offset_x=-target_x * offset_x / scale,
        offset_y=-target_y * offset_y / scale,
        target_width=target_width,
        target_height=target_height,
    )


__all__ = ["CanvasTransform", "canvas_transform"]
