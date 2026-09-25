r"""순서가 바뀐 쪽 판정을 실제 파일로 흔들어 보는 측정(명세 2026-09-25-01, ``riffle/reorder.py``).

사람 파일이 필요해 자동 테스트에는 넣지 않는다. 짝짓기·다시 짝짓기 판정을 바꿀 때 바꾸기 전과 후에 돌려 표를 비교한다.

    python tools/check_reorder.py --foreign <다른 강의 PDF> <옛 필기>|<새 PDF> [<옛 필기>|<새 PDF> ...]
    python tools/check_reorder.py --cases [<사례 폴더>]      # 저장할 때 남긴 사례를 다시 채점(기본 %LOCALAPPDATA%\Riffle\cases)

하는 일: 쌍마다 섞기 전 판정을 정답으로 삼고, 새 PDF 의 쪽 순서를 8가지로 일부러 섞어(이웃 두 쪽 바꿈, 한 쪽 3·10·40칸,
3·6쪽 묶음 멀리, 4쪽 안 뒤섞기, 옮긴 자리에 딴 쪽) 판정이 정답을 되찾는지 옛 쪽마다 센다. 따로 "쪽이 빠지고 딴 쪽이
들어온" 경우를 20번 만들어 엉뚱한 후보를 내미는지 센다. 쪽 지문만 섞으므로 PDF 를 새로 쓰지 않는다.

분류: 맞음 · 조용히 틀림(다른 쪽에 얹혔고 카드도 없음 — **하나라도 있으면 실패로 끝난다**) · 틀림(카드) · 후보(짝은
없지만 맞는 쪽이 "같은 쪽일까요?" 로 뜸) · 놓침(옛 쪽째 남음).

2026-09-25 기준값(병리학 1주차(3) 황희성 → 필기본, 2주차(2) 신성하 → 2주차(4-2) 새 판, 딴 쪽은 약리학 1주차(1)):
조용히 틀림 0, 사람에게 넘김 9(그중 맞는 후보 6), 엉뚱한 후보 40번 중 0.
같은 도구·같은 섞기로 잰 개선 전(자신 없는 짝을 다시 보지 않던 판, 커밋 88e3898): 조용히 틀림 0, 넘김 19, 엉뚱한 후보 0.
"""
from __future__ import annotations

import argparse
import random
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from riffle.cases import cases_dir, load_cases, score_case  # noqa: E402
from riffle.page_match import fingerprints, match_fingerprints  # noqa: E402
from riffle.reorder import pair_reordered  # noqa: E402
from riffle.transfer_plan import open_pdf  # noqa: E402

HANDWRITING = (".sdocx", ".notewise", ".goodnotes")


def prints_of(path: Path):
    if path.suffix.lower() == ".sdocx":
        with zipfile.ZipFile(path) as archive:
            data = archive.read(next(n for n in archive.namelist() if n.lower().endswith(".pdf")))
        return fingerprints(open_pdf(data, "옛 필기"))
    if path.suffix.lower() in HANDWRITING:
        raise SystemExit(f"지금은 Samsung Notes(.sdocx) 옛 필기만 읽는다: {path.name}")
    return fingerprints(open_pdf(path, "PDF"))


def judge_run(old, new):
    result = pair_reordered(match_fingerprints(old, new), old, new)
    got, flagged = {}, set()
    for pair in result.match.pairs:
        if pair.matched:
            got[pair.source_index] = pair.target_index
            if not pair.confident:
                flagged.add(pair.source_index)
    return got, flagged, result.candidates


def scenarios(n, rng, foreign_count):
    base = list(range(n))
    for _ in range(15):
        i = rng.randrange(5, n - 6)
        order = base[:]
        order[i], order[i + 1] = order[i + 1], order[i]
        yield "이웃 두 쪽 바꿈", order
    for k in (3, 10, 40):
        for _ in range(8):
            i = rng.randrange(5, n - k - 5)
            order = base[:]
            order.insert(i + k, order.pop(i))
            yield f"한 쪽 {k}칸 뒤로", order
    for b in (3, 6):
        for _ in range(8):
            i = rng.randrange(5, n // 2 - b)
            order = base[:]
            block = order[i:i + b]
            del order[i:i + b]
            j = rng.randrange(n // 2, len(order))
            order[j:j] = block
            yield f"{b}쪽 묶음 멀리", order
    for _ in range(8):
        order = base[:]
        for start in range(0, n - 4, 4):
            if rng.random() < 0.3:
                window = order[start:start + 4]
                rng.shuffle(window)
                order[start:start + 4] = window
        yield "4쪽 안 뒤섞기", order
    for _ in range(12):
        i = rng.randrange(5, n - 30)
        order = base[:]
        order.insert(i + 20, order.pop(i))
        order.insert(i, f"F{rng.randrange(foreign_count)}")
        yield "옮긴 자리에 딴 쪽", order


def apply(order, new, foreign):
    pages = [foreign[int(o[1:])] if isinstance(o, str) else new[o] for o in order]
    ids = [None if isinstance(o, str) else o for o in order]
    return pages, ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--foreign", type=Path, help="끼워 넣을 다른 강의 PDF(쌍을 줄 때 필요)")
    parser.add_argument("--cases", nargs="?", const="", help="저장할 때 남긴 사례 폴더(값 없이 쓰면 기본 폴더)")
    parser.add_argument("pairs", nargs="*", help="<옛 필기>|<새 PDF>")
    args = parser.parse_args()
    if not args.pairs and args.cases is None:
        parser.error("쌍이나 --cases 중 하나는 있어야 한다")
    if args.pairs and args.foreign is None:
        parser.error("쌍을 섞으려면 --foreign 이 필요하다")
    foreign = prints_of(args.foreign) if args.pairs else []
    silent_total = handed_total = false_total = 0
    for spec in args.pairs:
        source, target = (Path(part) for part in spec.split("|"))
        old, new = prints_of(source), prints_of(target)
        truth, _, _ = judge_run(old, new)
        rng = random.Random(7)
        rows: dict[str, Counter] = {}
        for name, order in scenarios(len(new), rng, len(foreign)):
            pages, ids = apply(order, new, foreign)
            got, flagged, candidates = judge_run(old, pages)
            tally = rows.setdefault(name, Counter())
            for s, t in truth.items():
                if s in got and ids[got[s]] == t:
                    tally["맞음"] += 1
                elif s in got:
                    tally["틀림(카드)" if s in flagged else "조용히 틀림"] += 1
                elif s in candidates and ids[candidates[s]] == t:
                    tally["후보"] += 1
                else:
                    tally["놓침"] += 1
        false_candidates = 0
        inverse = {t: s for s, t in truth.items()}
        rng = random.Random(11)
        for _ in range(20):
            i = rng.randrange(5, len(new) - 6)
            order = list(range(len(new)))
            order.pop(i)
            order.insert(i + rng.randrange(0, 3), f"F{rng.randrange(len(foreign))}")
            pages, ids = apply(order, new, foreign)
            got, flagged, candidates = judge_run(old, pages)
            lost = inverse.get(i)
            false_candidates += lost in candidates
            if lost in got and lost not in flagged:
                rows.setdefault("쪽 빠지고 딴 쪽", Counter())["조용히 틀림"] += 1
        print(f"== {source.name} → {target.name} (옛 {len(old)}쪽, 정답 짝 {len(truth)}쌍)")
        for name, tally in rows.items():
            others = {key: value for key, value in tally.items() if key != "맞음"}
            print(f"  {name:12} 맞음 {tally['맞음']:5}  그 밖: {others or '-'}")
            silent_total += tally["조용히 틀림"]
            handed_total += sum(value for key, value in tally.items() if key not in ("맞음", "조용히 틀림"))
        print(f"  엉뚱한 후보: 20번 중 {false_candidates}")
        false_total += false_candidates
    if args.cases is not None:
        # 사람이 확정해 저장한 짝이 정답이다. 섞지 않고 그대로 다시 돌린다.
        folder = Path(args.cases) if args.cases else cases_dir()
        loaded = load_cases(folder) if folder.is_dir() else []
        total: Counter = Counter()
        print(f"== 저장된 사례 {len(loaded)}개 ({folder})")
        for path, case in loaded:
            tally = score_case(case, pair_reordered)
            total.update(tally)
            others = {key: value for key, value in tally.items() if key != "맞음"}
            if others:
                print(f"  {path.name}: 맞음 {tally['맞음']}  그 밖: {others}")
        print(f"  사례 합계 맞음 {total['맞음']}  그 밖: {({k: v for k, v in total.items() if k != '맞음'}) or '-'}")
        silent_total += total["조용히 틀림"]
        handed_total += sum(value for key, value in total.items() if key not in ("맞음", "조용히 틀림"))
    print(f"합계 — 조용히 틀림 {silent_total} · 사람에게 넘김 {handed_total} · 엉뚱한 후보 {false_total}")
    return 1 if silent_total else 0


if __name__ == "__main__":
    sys.exit(main())
