"""앱 아이콘 — Sleek 과 같은 틀(사용자 요청 2026-09-25, 명세 2026-09-25-03).

Sleek 아이콘(`sleek/pipeline/gui/branding.icon_svg`)의 틀을 그대로 쓴다: 뷰박스 256 안에 x·y 12, 한 변 232, 모서리
반지름 54 인 **흰 둥근 사각형**, 옅은 회색(#e3e3e8) 테두리 3, 가운데에 **굵은 검은 선 그림** 하나. 두 앱을 오가는 사람이
같은 식구로 알아보게 한다(UX 철학 원칙 8).

그림은 **나란히 겹쳐 왼쪽 아래로 내려오는 종이 세 장** — riffle(책장을 훌훌 넘긴다). 쪽을 다루는 앱임을 말한다.
맨 앞 장에는 글줄 셋. (처음 판은 부채꼴로 기울인 종이였다 — 사용자 요청으로 평행하게 바꿈, 2026-09-25)
큰 캔버스에 그린 뒤 줄여, 작업 표시줄의 작은 크기에서도 선이 매끈하다. 선 굵기는 모든 크기가 같다(Sleek 과 같은 원칙).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

_RENDER = 2048
_INK = (17, 17, 19, 255)
_PAPER = (255, 255, 255, 255)
_RIM = (227, 227, 232, 255)


def _page(size: int, box: tuple[float, float, float, float], stroke: int, lines: bool) -> Image.Image:
    """종이 한 장(흰 바탕 + 검은 테두리). ``lines`` 면 글줄 셋."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    left, top, right, bottom = box
    radius = round((right - left) * 0.09)
    draw.rounded_rectangle(box, radius=radius, fill=_PAPER, outline=_INK, width=stroke)
    if lines:
        inner = right - left
        for number, share in enumerate((0.62, 0.62, 0.38)):
            y = top + (bottom - top) * (0.34 + number * 0.17)
            x0 = left + inner * 0.2
            draw.rounded_rectangle((x0, y - stroke / 2, x0 + inner * share, y + stroke / 2),
                                   radius=stroke / 2, fill=_INK)
    return layer


def _render_icon() -> Image.Image:
    size = _RENDER
    unit = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12 * unit, 12 * unit, 244 * unit, 244 * unit), radius=round(54 * unit),
                           fill=_PAPER, outline=_RIM, width=round(3 * unit))

    stroke = round(9 * unit)
    # 종이 세 장이 기울지 않고 나란히, 왼쪽 아래로 한 칸씩 내려오며 겹친다(사용자 요청 2026-09-25). 맨 앞(왼쪽 아래) 장에 글줄.
    width, height, step = 88 * unit, 118 * unit, 18 * unit
    left, top = 60 * unit, 40 * unit
    mark = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for back, lines in ((2, False), (1, False), (0, True)):
        x0, y0 = left + back * step, top + (2 - back) * step       # 뒤 장일수록 오른쪽 위
        mark.alpha_composite(_page(size, (x0, y0, x0 + width, y0 + height), stroke, lines))
    # 그림을 틀 가운데로 옮긴다.
    x0, y0, x1, y1 = mark.getbbox()
    centered = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    centered.paste(mark, (round(size / 2 - (x0 + x1) / 2), round(size / 2 - (y0 + y1) / 2)), mark)
    image.alpha_composite(centered)
    return image


def build_icon(output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = _render_icon().resize((256, 256), Image.Resampling.LANCZOS)
    image.save(
        output_path,
        format="ICO",
        sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)],
    )


def build_pwa_icons(output_dir: Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    image = _render_icon()
    for size in (180, 192, 512):
        resized = image.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(output_dir / f"icon-{size}.png", format="PNG", optimize=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    build_icon(root / "assets" / "icon.ico")
    # 웹 앱 아이콘은 화면 소스에 둔다 — `web` 에서 `npm run build` 하면 riffle/ui/icons 로 들어간다.
    build_pwa_icons(root / "web" / "public" / "icons")


if __name__ == "__main__":
    main()
