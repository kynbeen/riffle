"""극단적인 입력 여덟 가지(같은 파일·전혀 다른 강의록·한 쪽짜리·필기 없음·흰 쪽·세로 쪽·돌린 쪽). `python tools/fuzz/edges.py`

극단적인 입력 — 분석·저장이 사람 말로 끝나고(죽지 않고), 손필기를 잃지 않는가."""
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).parent))
import pymupdf
import fuzz
from riffle.handwriting_transfer import inspect_transfer, transfer_handwriting
from riffle.review import review
from riffle.sdocx_ink import read_ink_strokes
from riffle.transfer_plan import HandwritingTransferError
from tests.test_page_match import SEEDS, make_document
from tests.test_sleek_update import CANVAS_WIDTH, notes_pdf, notes_sdocx

root = Path(tempfile.mkdtemp())
slides = make_document(root / "slides.pdf", SEEDS[:5])
other = make_document(root / "other.pdf", SEEDS[7:11])            # 전혀 다른 강의록
one = make_document(root / "one.pdf", SEEDS[:1])
notes = root / "notes.pdf"
notes_pdf(slides, notes, {1: 3}, front=True)
with pymupdf.open() as blank:
    blank.new_page(width=640, height=480)
    blank.new_page(width=640, height=480)
    blank.save(root / "blank.pdf")                                   # 글자 없는 흰 쪽만
with pymupdf.open() as tall:
    tall.new_page(width=300, height=1200).insert_text((40, 80), "TALL", fontsize=40)
    tall.save(root / "tall.pdf")                                     # 비율이 전혀 다른 세로 긴 쪽
with pymupdf.open(slides) as src, pymupdf.open() as rotated:
    rotated.insert_pdf(src)
    for page in rotated:
        page.set_rotation(90)
    rotated.save(root / "rotated.pdf")                               # 돌려 놓은 쪽


def w(x, y, d, size=60):
    return fuzz.w_stroke(x, y, size, size / 2, d)


def source_from(pdf, name, inked=True):
    with pymupdf.open(pdf) as doc:
        ink = {i: [w(30, 30, CANVAS_WIDTH / p.rect.width), w(p.rect.width - 120, p.rect.height - 60,
                                                              CANVAS_WIDTH / p.rect.width)]
               for i, p in enumerate(doc)} if inked else {}
    path = root / name
    notes_sdocx(path, pdf, ink)
    return path, sum(len(v) for v in ink.values())


CASES = [
    ("필기본 → 같은 필기본", source_from(notes, "a.sdocx"), notes),
    ("필기본 → 전혀 다른 강의록", source_from(notes, "b.sdocx"), other),
    ("일반 → 한 쪽짜리", source_from(slides, "c.sdocx"), one),
    ("필기 없는 파일 → 필기본", source_from(slides, "d.sdocx", inked=False), notes),
    ("필기본 → 흰 쪽뿐인 PDF", source_from(notes, "e.sdocx"), root / "blank.pdf"),
    ("일반 → 비율이 전혀 다른 세로 쪽", source_from(slides, "f.sdocx"), root / "tall.pdf"),
    ("일반 → 90도 돌린 같은 강의록", source_from(slides, "g.sdocx"), root / "rotated.pdf"),
    ("한 쪽짜리 → 필기본", source_from(one, "h.sdocx"), notes),
]

for title, (source, strokes), target in CASES:
    try:
        ins = inspect_transfer(source, target)
        items = review(ins.as_dict())["items"]
        out = root / (source.stem + "-out.sdocx")
        result = transfer_handwriting(source, target, out)
        pages = fuzz.saved(out)
        got = sum(len(read_ink_strokes(p)[2]) for p in pages)
        bad = sum(len(fuzz.inside(p)) for p in pages)
        verdict = "OK" if got == strokes and bad == 0 else "문제"
        print(f"{verdict} {title}: 결과 {len(pages)}쪽, 획 {strokes}→{got}, 쪽 밖 {bad}, 카드 {len(items)}"
              f" ({', '.join(sorted({i['reason'] for i in items}))}) 판정 {ins.notes_mode or '-'}/{ins.mode}")
    except HandwritingTransferError as exc:
        print(f"거절 {title}: {exc}")
    except Exception as exc:
        print(f"오류 {title}: {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
