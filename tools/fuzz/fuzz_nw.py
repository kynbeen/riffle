"""같은 퍼징을 Notewise 형식으로. `python tools/fuzz/fuzz_nw.py 0 40`

같은 퍼징을 Notewise 형식으로 — 형식이 달라도 같은 규칙이 지켜지는가."""
import base64
import random
import struct
import sys
import tempfile
import traceback
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).parent))
import pymupdf
import fuzz
from riffle.handwriting_transfer import inspect_transfer, preview_transfer, transfer_handwriting
from riffle.ink_layer import NOTEWISE
from riffle.notewise_ink import read_notewise_strokes
from riffle.notewise_proto import iter_fields
from riffle.page_plan import PagePlan
from riffle.transfer_plan import HandwritingTransferError
from tests.test_notewise_transfer import _field, _number, _page_id, _varint


def make_notewise(path: Path, pdf: Path, ink: dict[int, list[list[tuple[float, float]]]], density_width=1848):
    with pymupdf.open(pdf) as document:
        sizes = [(p.rect.width, p.rect.height) for p in document]
    pdf_id, relation_id = b"pdf-id", b"relation-id"
    page_ids = [_page_id(i) for i in range(len(sizes))]
    payloads = []
    for index, (page_id, (w, h)) in enumerate(zip(page_ids, sizes)):
        canvas = (density_width, round(h * density_width / w))
        page = _field(1, page_id)
        if index:
            page += _number(2, index)
        page += _field(3, _field(1, pdf_id) + _number(2, index))
        for stroke in ink.get(index, []):
            xs = struct.pack(f"<{len(stroke)}f", *[x for x, _ in stroke])
            ys = struct.pack(f"<{len(stroke)}f", *[y for _, y in stroke])
            widths = struct.pack(f"<{len(stroke)}f", *([3.0] * len(stroke)))
            style = _field(1, b"#000000") + _varint((2 << 3) | 5) + struct.pack("<f", 1.0)
            pen = _number(1, 2) + _field(3, style) + _field(4, xs) + _field(5, ys) + _field(6, widths)
            page += _field(4, _field(4, pen))
        page += (_field(6, _field(1, _number(3, canvas[0]) + _number(4, canvas[1])))
                 + _varint((7 << 3) | 1) + struct.pack("<d", 1024.0 * (index + 1)) + _field(11, relation_id))
        payloads.append((page_id.decode(), page))
    meta = _field(1, pdf_id) + _number(4, len(sizes)) + _field(5, pdf.name.encode())
    note = (_field(1, b"note-id") + _field(2, b"source") + b"".join(_field(4, i) for i in page_ids)
            + _field(6, meta) + _field(11, _field(1, relation_id) + _field(2, b"source")))
    with ZipFile(path, "w") as archive:
        archive.writestr("note", base64.b64encode(note))
        for name, payload in payloads:
            archive.writestr(f"page/{name}", base64.b64encode(payload))
        archive.writestr("pdf/pdf-id", pdf.read_bytes())


def saved(path):
    with ZipFile(path) as archive:
        note = base64.b64decode(archive.read("note"))
        ids = [bytes(v).decode() for n, w, v in iter_fields(note) if n == 4 and w == 2]
        return [archive.read(f"page/{i}") for i in ids]


def outside(payload):
    strokes, (width, height) = read_notewise_strokes(payload)
    return [s for s in strokes if not all(-2 <= x <= width + 2 and -2 <= y <= height + 2 for x, y in s.points)]


def run(seed):
    rng = random.Random(seed)
    root = Path(tempfile.mkdtemp())
    count = rng.randint(2, 6)
    old_slides, new_slides = fuzz.derived_slides(rng, root, count)
    old_notes = rng.random() < 0.75
    new_notes = rng.random() < 0.8
    old_pdf = fuzz.make_notes(rng, old_slides, root / "old.pdf", old_notes) or old_slides
    new_pdf = fuzz.make_notes(rng, new_slides, root / "new.pdf", new_notes) or new_slides
    ink = fuzz.random_ink(rng, old_pdf)
    source = root / "old.notewise"
    make_notewise(source, old_pdf, ink)
    label = f"seed {seed}: {'필기본' if old_notes else '일반'}→{'필기본' if new_notes else '일반'}"
    found = []
    try:
        ins = inspect_transfer(source, new_pdf)
    except HandwritingTransferError as exc:
        return label, [f"분석 거절: {exc}"]
    for trial, (rows, note) in enumerate([(None, "기계대로"), fuzz.human_rows(rng, ins)]):
        out = root / f"out{trial}.notewise"
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
            found.append(f"[{note}] 저장 오류: {type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}")
            continue
        pages = saved(out)
        if len(pages) != len(plan.slots):
            found.append(f"[{note}] 쪽 수 {len(plan.slots)} 기대, 저장 {len(pages)}")
        want = sum(len(ink.get(s, [])) for slot in plan.slots for s in slot.sources)
        got = sum(len([b for b in NOTEWISE.boxes(p) if b]) for p in pages)
        if want != got:
            found.append(f"[{note}] 획 수 {want} 기대, 저장 {got}")
        for position, page in enumerate(pages):
            if plan.slots[position].target_index is None:
                continue
            if outside(page):
                found.append(f"[{note}] 결과 {position + 1}쪽 쪽 밖 획 {len(outside(page))}")
        if rows is None:
            for position, slot in enumerate(plan.slots):
                if slot.target_index is None or not any(ink.get(s) for s in slot.sources):
                    continue
                _b, _a, _i, count = preview_transfer(source, new_pdf, slot.target_index, ins,
                                                     source_index_override=slot.sources[0], sources=slot.sources)
                stored = len([b for b in NOTEWISE.boxes(pages[position]) if b])
                if count != stored:
                    found.append(f"미리보기 {count} ≠ 저장 {stored} (새 {slot.target_index + 1}쪽)")
    return label, found


if __name__ == "__main__":
    start, stop = int(sys.argv[1]), int(sys.argv[2])
    failed = 0
    for seed in range(start, stop):
        label, found = run(seed)
        if found:
            failed += 1
            print(label)
            for item in found:
                print("   ", item)
    print(f"끝(Notewise): {stop - start}개 중 문제 {failed}개")
