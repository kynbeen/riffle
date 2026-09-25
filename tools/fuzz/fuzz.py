"""퍼징(일부러 이상한 입력을 대량으로 넣어 보는 시험) — Samsung Notes. 2026-09-26 사용자 요청으로 만듦.

    python tools/fuzz/fuzz.py 0 80        # 씨앗 0~79

이상한 입력 퍼징: 무작위 필기본·일반 PDF 쌍과 무작위 손필기·사람 수정으로 규칙이 깨지는지 본다.

규칙(깨지면 문제로 적는다):
  1. 분석·저장이 알 수 없는 오류로 죽지 않는다(사람 말 오류로 거절하는 것은 따로 센다).
  2. 결과에 들어간 옛 쪽의 획은 한 획도 줄거나 늘지 않는다(뺀 쪽 제외). 기계가 뺀 옛 쪽에는 손필기가 없어야 한다.
  3. 모든 획은 자기 쪽 캔버스 안에 있다(2px 여유).
  4. 저장 결과의 쪽 수 = 계획의 줄 수.
  5. 미리보기의 획 수 = 저장된 그 쪽의 획 수.
"""
import random
import sys
import tempfile
import traceback
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pymupdf
from riffle.handwriting_transfer import inspect_transfer, preview_transfer, transfer_handwriting
from riffle.page_plan import PagePlan
from riffle.sdocx_ink import read_ink_strokes
from riffle.sdocx_note import read_page_order
from riffle.sdocx_page import read_page
from riffle.transfer_plan import HandwritingTransferError
from tests.test_page_match import SEEDS, make_document
from tests.test_sleek_update import CANVAS_WIDTH, notes_pdf, notes_sdocx

TEXTS = ["짧은 설명", "\n".join(f"설명 줄 {n}" for n in range(6)),
         "\n".join("칸을 가득 채운 설명 " * 3 for _ in range(30)), ""]


def w_stroke(x, y, w, h, d):
    """W 모양 획. 실제 펜처럼 점을 촘촘히(캔버스 12px 마다) 찍는다."""
    corners = [(x, y), (x + w / 4, y + h), (x + w / 2, y), (x + 3 * w / 4, y + h), (x + w, y)]
    points = []
    for (ax, ay), (bx, by) in zip(corners, corners[1:]):
        steps = max(1, int(max(abs(bx - ax), abs(by - ay)) * d / 12))
        points += [((ax + (bx - ax) * i / steps) * d, (ay + (by - ay) * i / steps) * d) for i in range(steps)]
    points.append((corners[-1][0] * d, corners[-1][1] * d))
    return points


def make_notes(rng, slides_path, out, notes):
    with pymupdf.open(slides_path) as doc:
        count, size = doc.page_count, doc[0].rect
    if not notes:
        return None
    copies = {i: rng.choice([1, 1, 1, 2, 3]) for i in range(count)}
    texts = {(i, p): rng.choice(TEXTS) for i in range(count) for p in range(copies[i])}
    heights = {(i, 0): size.height * rng.choice([1.2, 1.5]) for i in range(count) if rng.random() < 0.15}
    notes_pdf(slides_path, out, copies, texts=texts, front=rng.random() < 0.25, heights=heights)
    return out


def derived_slides(rng, root, count):
    base = make_document(root / "base.pdf", SEEDS[:count])
    order = list(range(count))
    if count > 2 and rng.random() < 0.3:
        order.remove(rng.randrange(count))               # 새 판에서 한 쪽 빠짐
    if len(order) > 3 and rng.random() < 0.3:
        i = rng.randrange(len(order) - 1)
        order[i], order[i + 1] = order[i + 1], order[i]  # 순서 바뀜
    if rng.random() < 0.2:
        order.insert(rng.randrange(len(order) + 1), None)  # 새로 생긴 쪽(빈 쪽)
    with pymupdf.open(base) as src, pymupdf.open() as out:
        for index in order:
            if index is None:
                out.new_page(width=src[0].rect.width, height=src[0].rect.height).insert_text((60, 80), "NEW", fontsize=40)
            else:
                out.insert_pdf(src, from_page=index, to_page=index)
        out.save(root / "new-slides.pdf")
    return base, root / "new-slides.pdf"


def random_ink(rng, pdf_path):
    ink = {}
    with pymupdf.open(pdf_path) as doc:
        for index, page in enumerate(doc):
            if rng.random() < 0.45:
                continue
            d = CANVAS_WIDTH / page.rect.width
            W, H = page.rect.width, page.rect.height
            strokes = []
            for _ in range(rng.randint(1, 3)):
                kind = rng.random()
                w, h = rng.choice([(40, 20), (80, 30), (200, 120), (400, 300)]) if kind < 0.9 else (W * 0.9, H * 0.9)
                x = rng.uniform(0, max(1, W - w))
                y = rng.uniform(0, max(1, H - h))
                if rng.random() < 0.15:
                    x, y = W - w - 0.5, H - h - 0.5               # 쪽 오른쪽 아래 모서리에 딱 붙음(쪽 안)
                strokes.append(w_stroke(x, y, w, h, d))
            ink[index] = strokes
    return ink


def saved(path):
    with ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("pageIdInfo.dat"))
        root = PurePosixPath(name).parent
        pages = [archive.read(str(root / f"{e.uuid}.page")) for e in read_page_order(archive.read(name)).entries]
    return [p for p in pages if read_page(p).pdf is not None]


def inside(page_blob):
    width, height, strokes = read_ink_strokes(page_blob)
    return [st for st in strokes if not all(-2 <= x <= width + 2 and -2 <= y <= height + 2 for x, y in st.points)]


def human_rows(rng, ins):
    rows = [{"source_index": s["source_index"], "target_index": s["target_index"], "confirmed": True, "excluded": False,
             **({"merged": s["merged"]} if s.get("merged") else {})} for s in ins.as_dict()["plan"]["slots"]]
    for s in ins.dropped_sources:
        rows.append({"source_index": s, "target_index": None, "confirmed": True, "excluded": True})
    inked = [r for r in rows if r["source_index"] in ins.inked_sources and r["target_index"] is not None and not r.get("merged")]
    note = ""
    if inked and rng.random() < 0.6:
        row = rng.choice(inked)
        s = row["source_index"]
        t = rng.randrange(ins.page_count)
        row["source_index"] = None
        dest = next(r for r in rows if r["target_index"] == t)
        if dest["source_index"] is None:
            dest["source_index"] = s
        else:
            dest.setdefault("merged", []).append(s)
            dest["merged"].sort()
        note = f"옛 {s + 1}→새 {t + 1}"
    if rng.random() < 0.3:
        candidates = [r for r in rows if r["source_index"] is not None and not r["excluded"]]
        if candidates:
            victim = rng.choice(candidates)
            victim["excluded"] = True
            note += f" 뺌 옛 {victim['source_index'] + 1}"
    rows = [r for r in rows if r["source_index"] is not None or r["target_index"] is not None or r.get("merged")]
    for r in rows:
        if r["source_index"] is None and r.get("merged"):
            r["source_index"] = r["merged"].pop(0)
    return rows, note


def run(seed):
    rng = random.Random(seed)
    root = Path(tempfile.mkdtemp())
    count = rng.randint(2, 6)
    old_slides, new_slides = derived_slides(rng, root, count)
    old_notes = rng.random() < 0.75
    new_notes = rng.random() < 0.8
    old_pdf = make_notes(rng, old_slides, root / "old.pdf", old_notes) or old_slides
    new_pdf = make_notes(rng, new_slides, root / "new.pdf", new_notes) or new_slides
    ink = random_ink(rng, old_pdf)
    source = root / "old.sdocx"
    notes_sdocx(source, old_pdf, ink)
    label = f"seed {seed}: {'필기본' if old_notes else '일반'}→{'필기본' if new_notes else '일반'} 강의록 {count}쪽"
    found = []
    try:
        ins = inspect_transfer(source, new_pdf)
    except HandwritingTransferError as exc:
        return label, [f"분석 거절: {exc}"], True
    for s in ins.dropped_sources:
        if ink.get(s):
            found.append(f"손필기 있는 옛 {s + 1}쪽을 기계가 뺐다")
    for trial, (rows, note) in enumerate([(None, "기계대로"), human_rows(rng, ins)]):
        out = root / f"out{trial}.sdocx"
        try:
            if rows is None:
                plan = ins.page_plan()
                transfer_handwriting(source, new_pdf, out)
            else:
                plan = PagePlan.from_payload(ins.source_page_count, ins.page_count, rows, ins.match)
                transfer_handwriting(source, new_pdf, out, plan_override=plan)
        except HandwritingTransferError as exc:
            found.append(f"[{note}] 저장 거절: {exc}")
            continue
        except Exception as exc:
            found.append(f"[{note}] 저장 오류: {type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}")
            continue
        pages = saved(out)
        with ZipFile(out) as archive:
            embedded = next(n for n in archive.namelist() if n.lower().endswith(".pdf"))
            with pymupdf.open(stream=archive.read(embedded), filetype="pdf") as inner:
                if inner.page_count != len(pages):
                    found.append(f"[{note}] 파일 안 PDF {inner.page_count}쪽 ≠ 노트 쪽 {len(pages)}")
        if len(pages) != len(plan.slots):
            found.append(f"[{note}] 쪽 수 {len(plan.slots)} 기대, 저장 {len(pages)}")
        want = sum(len(ink.get(s, [])) for slot in plan.slots for s in slot.sources)
        got = sum(len(read_ink_strokes(p)[2]) for p in pages)
        if want != got:
            found.append(f"[{note}] 획 수 {want} 기대, 저장 {got}")
        for position, page in enumerate(pages):
            if position < len(plan.slots) and plan.slots[position].target_index is None:
                continue                   # 옛 쪽째 남긴 쪽 — 획을 옮기지 않는다(입력 그대로)
            bad = inside(page)
            if bad:
                found.append(f"[{note}] 결과 {position + 1}쪽 쪽 밖 획 {len(bad)}")
        if rows is None:
            for position, slot in enumerate(plan.slots):
                if slot.target_index is None or not slot.sources:
                    continue
                if not any(ink.get(s) for s in slot.sources):
                    continue
                try:
                    _b, _a, _i, count_preview = preview_transfer(source, new_pdf, slot.target_index, ins,
                                                                 source_index_override=slot.sources[0], sources=slot.sources)
                except Exception as exc:
                    found.append(f"미리보기 오류 새 {slot.target_index + 1}쪽: {exc}")
                    continue
                stored = len(read_ink_strokes(pages[position])[2])
                if count_preview != stored:
                    found.append(f"미리보기 {count_preview}획 ≠ 저장 {stored}획 (새 {slot.target_index + 1}쪽)")
    return label, found, False


if __name__ == "__main__":
    start, stop = int(sys.argv[1]), int(sys.argv[2])
    failed = 0
    for seed in range(start, stop):
        label, found, refused = run(seed)
        if found:
            failed += 1
            print(label)
            for item in found:
                print("   ", item)
    print(f"끝: {stop - start}개 중 문제 {failed}개")
