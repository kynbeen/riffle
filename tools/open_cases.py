"""경우마다 Riffle 데스크톱 창을 하나씩 띄운다 — 사람이 모든 경우를 눈으로 확인하게(2026-09-25 사용자 요청).

    python tools/open_cases.py            # 전부
    python tools/open_cases.py 1 3 8      # 고른 번호만
    python tools/open_cases.py --list     # 목록만

실제 파일이 이 PC 에 없으면 그 경우는 건너뛴다. 실제 샘플에 없는 경우(칸 손필기를 여백·강의록 빈칸으로 옮김, 손필기
있는 옛 쪽이 새 판에서 사라짐, 아래로 늘어난 옛 쪽)는 `tmp/케이스/` 에 합성 파일을 만들어 쓴다. 창은 `python -m riffle
<파일들>` 로 열려 놓은 것과 똑같이 시작한다. 원본 파일은 읽기만 한다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES_DIR = ROOT / "tmp" / "케이스"
DOWNLOADS = Path.home() / "Downloads"
SLEEK = Path("C:/dev/sleek")
NOTES = SLEEK / "output" / "병리학"


def _notes(folder: str) -> Path | None:
    return next((NOTES / folder).glob("*필기.pdf"), None) if (NOTES / folder).is_dir() else None


def _sample(tag: str) -> Path | None:
    return next((path for path in (SLEEK / "samples").glob("*.sdocx") if tag in path.name), None)


def make_synthetic(out: Path) -> dict[str, Path]:
    """합성 필기본 두 판과 손필기 파일. 한 쌍에 실제 샘플에 없는 경우를 모두 모은다."""
    import pymupdf

    from tests.test_page_match import SEEDS, make_document
    from tests.test_sleek_notes import PANEL
    from tests.test_sleek_update import CANVAS_WIDTH, notes_pdf, notes_sdocx

    out.mkdir(parents=True, exist_ok=True)
    slides = make_document(out / "강의록.pdf", SEEDS[:6])
    with pymupdf.open(slides) as document, pymupdf.open() as fewer:
        width, height = document[0].rect.width, document[0].rect.height
        fewer.insert_pdf(document, from_page=0, to_page=4)                 # 새 판에서 강의록 6쪽이 빠짐
        fewer.save(out / "강의록-새판.pdf")
    density = CANVAS_WIDTH / (width + PANEL)

    def word(x: float, y: float, tall: float = 40) -> list[tuple[float, float]]:
        a, b = x * density, y * density
        return [(a, b), (a + 20, b + tall), (a + 40, b), (a + 60, b + tall), (a + 80, b)]

    long_text = "\n".join(f"새로 고쳐 쓴 설명 {n}번째 줄입니다" for n in range(9))
    full_text = "\n".join("칸을 가득 채운 새 설명 줄 " * 3 for _ in range(30))
    old_pdf, new_pdf = out / "옛 필기본.pdf", out / "새 필기본.pdf"
    notes_pdf(slides, old_pdf, {1: 3}, heights={(4, 0): height * 1.4})         # 1 2 2' 2'' 3 4 5(늘어남) 6
    notes_pdf(out / "강의록-새판.pdf", new_pdf, {1: 2},                        # 1 2 2' 3(글 바뀜) 4(칸 꽉 참) 5
              texts={(2, 0): long_text, (3, 0): full_text})
    panel = width + 40
    source = out / "옛 필기본-손필기.sdocx"
    notes_sdocx(source, old_pdf, {
        0: [word(80, 60)],                                    # 강의록 영역
        1: [word(100, 100), word(panel, 120)],                # 반복 1 — 강의록 + 칸
        2: [word(140, 140), word(panel, 200)],                # 반복 2
        3: [word(180, 180), word(panel, 260)],                # 반복 3 → 새 판은 반복 2
        4: [word(panel, 70)],                                  # 칸 글이 바뀐 자리 → 여백으로
        5: [word(panel, 100, 70)],                             # 칸이 꽉 참 → 강의록 빈칸으로
        6: [word(60, height * 1.25)],                          # 늘어난 아래 칸 → 새 쪽은 안 늘어남
        7: [word(100, 100)],                                    # 새 판에 없는 강의록 쪽 → 옛 쪽째 남기고 묻기
    })
    return {"source": source, "new_notes": new_pdf, "slides": slides, "slides_new": out / "강의록-새판.pdf"}


def cases() -> list[tuple[str, list[Path | None]]]:
    made = make_synthetic(CASES_DIR)
    check = ROOT / "tmp" / "실기검증"
    return [
        ("합성 · 필기본 → 필기본(모임·칸 필기 여백·강의록 빈칸·늘어난 쪽·사라진 쪽 카드)", [made["source"], made["new_notes"]]),
        ("합성 · 필기본 → 일반 PDF(칸 손필기를 묻는다)", [made["source"], made["slides"]]),
        ("실제 · 필기본 → 필기본 · 반복 수가 바뀌어 모임(병리 1주차(1) 53→50쪽)",
         [_sample("1주차1"), _notes("병리학 1주차(1) Introduction")]),
        ("실제 · 필기본 → 필기본 · 새 판에 없는 빈 쪽 뺌(병리 1주차(4))",
         [_sample("1주차4"), _notes("병리학 1주차(4) Inflammation and repair")]),
        ("실제 · 필기본 → 필기본 · 순서 바뀜(병리 1주차(3))",
         [_sample("1주차3"), _notes("병리학 1주차(3) Inflammation and repair")]),
        ("실제 · 일반 → 필기본 · 확인 카드 2장(병리 2주차(1))",
         [DOWNLOADS / "병리학_2주차(1)_이소민_Hemodynamic disorders_박민웅_260831_224343.sdocx",
          _notes("병리학 2주차(1) Hemodynamic disorders")]),
        ("실제 · 일반 → 필기본 · 새로 생긴 쪽·똑같은 쪽 카드(Chapter3-1)",
         [DOWNLOADS / "Chapter3-1_Inflammation and Repair_SLee_260825_155105.sdocx",
          _notes("병리학 1주차(3) Inflammation and repair")]),
        ("Notewise · 비율 바뀐 새 PDF", [check / "notewise" / "원본.notewise", check / "notewise" / "대상-세로로-늘린.pdf"]),
        ("Goodnotes · 비율 바뀐 새 PDF", [check / "goodnotes" / "원본.goodnotes", check / "goodnotes" / "대상-세로로-늘린.pdf"]),
        ("문서 합치기 · PDF 두 개", [made["slides"], made["slides_new"]]),
    ]


def main() -> int:
    listing = cases()
    if "--list" in sys.argv:
        for number, (title, _files) in enumerate(listing, 1):
            print(f"{number:2d}. {title}")
        return 0
    chosen = {int(arg) for arg in sys.argv[1:] if arg.isdigit()} or set(range(1, len(listing) + 1))
    python = Path(sys.executable).with_name("pythonw.exe")
    for number, (title, files) in enumerate(listing, 1):
        if number not in chosen:
            continue
        if any(path is None or not path.exists() for path in files):
            print(f"{number:2d}. 건너뜀(파일 없음) — {title}")
            continue
        subprocess.Popen([str(python if python.exists() else sys.executable), "-m", "riffle", *map(str, files)], cwd=ROOT)
        print(f"{number:2d}. 열었음 — {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
