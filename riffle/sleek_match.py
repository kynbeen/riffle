"""새 파일이 Sleek 필기본일 때의 쪽 짝짓기(명세 2026-09-25-03, 사용자 요청 2026-09-25).

Sleek 필기본은 필기가 길면 같은 강의록 쪽을 이어서 다시 싣는다(**반복 묶음**). 필기본을 다시 만들면 같은 강의록
쪽의 반복 수가 바뀐다. 쪽 하나하나를 짝지으면 남는 옛 반복 쪽이 "새 판에 없는 쪽" 으로 옛 쪽째 남아 옛 필기본 글이
결과에 섞인다(합집합). 그래서 **묶음 단위로** 짝짓는다.

1. 옛·새 파일을 묶음으로 나눈다. 새 파일은 필기본이니 끼운 강의록 쪽 내용이 같은 이웃 쪽이 한 묶음이다. 옛 파일이
   필기본이 아니면 쪽 하나가 한 묶음이다.
2. 묶음의 첫 쪽 지문(강의록 영역만)으로 순서 보존 짝짓기 → 순서가 바뀐 묶음 다시 짝짓기(``reorder``).
3. 두 짝 사이의 같은 틈에 옛·새 묶음이 함께 남으면 **틈 안에서 한 번 더** 짝짓는다. 문턱은 서로 다른 쪽의 실측
   최소 거리(0.78) — "순서 보존 규칙으로 최대한 짝짓는다"(요청 4).
4. 짝지은 묶음 안에서는 옛 쪽마다 새 쪽 하나를 고른다. 필기본끼리면 **상대 위치**(필기 칸 글이 차지하는 흐름에서
   겹치는 몫이 가장 큰 새 쪽, 비슷하면 앞쪽)로, 옛 파일이 필기본이 아니면 묶음의 **첫 쪽**(강의록 쪽이 처음 나오는
   자리)으로.
5. 새 판에 없는 옛 쪽: 손필기가 있으면 옛 쪽째 남기고 사람에게 알린다(원칙 7). 없으면 — 필기본끼리는 **결과에서
   뺀다**(새 판이 정답, 요청 4). 옛 파일이 필기본이 아니면 남긴다(합집합 — 기출 색인 사례, 사용자 결정 2026-09-25).

엔진(``page_match``)은 바꾸지 않는다. Sleek 이 사람 없이 직접 부른다(``tests/test_sleek_engine_contract.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .page_match import (
    _UNCERTAIN_DISTANCE,
    _UNCERTAIN_MARGIN,
    MatchResult,
    PageFingerprint,
    PagePair,
    match_fingerprints,
)
from .reorder import Reorder, pair_reordered
from .sleek_notes import is_notes_document, page_layout, panel_extent

# 틈 안 짝짓기: 짝이 갭 둘보다 싸면 짝짓는다 → 거리 0.78 까지 짝(실측: 서로 다른 쪽은 최소 0.78, page_match).
_GAP_FILL_COST = 0.39
# 상대 위치로 고를 때 겹침이 이만큼(옛 쪽 몫의 비율) 안쪽으로 비슷하면 앞쪽 새 쪽을 고른다.
_TIE_SHARE = 0.05
_MIN_EXTENT = 1.0

NOTES = "notes"              # 필기본 → 필기본
INTO_NOTES = "into_notes"    # 필기본 아닌 파일 → 필기본


@dataclass(frozen=True)
class NotesMatch:
    mode: str
    match: MatchResult                                   # 결과 순서의 쪽 짝(한 새 쪽에 대표 옛 쪽 하나)
    merged: dict[int, tuple[int, ...]]                   # 새 쪽 → 함께 얹는 옛 쪽(대표 말고)
    dropped: tuple[int, ...]                             # 결과에서 뺀 옛 쪽(새 판에 없고 손필기도 없음)
    reorder: Reorder                                     # 순서 바뀐 옛 쪽·후보·가장 닮은 쪽(쪽 번호)
    resized_runs: int = 0                                # 반복 수가 바뀐 묶음 수 — 알림
    runs: tuple[tuple[int, ...], ...] = field(default=(), compare=False)


def notes_mode(source_document, target_document) -> str | None:
    if not is_notes_document(target_document):
        return None
    return NOTES if is_notes_document(source_document) else INTO_NOTES


def page_runs(document, notes: bool) -> list[tuple[int, ...]]:
    """반복 묶음. 필기본이 아니면 쪽 하나가 한 묶음이다. 맨 앞 전용 쪽은 혼자 한 묶음이다."""
    if not notes:
        return [(index,) for index in range(document.page_count)]
    runs: list[list[int]] = []
    previous = None
    for index in range(document.page_count):
        layout = page_layout(document[index], with_key=True)
        key = layout.key if layout is not None else None
        if runs and key is not None and key == previous:
            runs[-1].append(index)
        else:
            runs.append([index])
        previous = key
    return [tuple(run) for run in runs]


def _front(document, run: tuple[int, ...]) -> bool:
    layout = page_layout(document[run[0]])
    return layout is not None and layout.lecture is None


def _extents(document, run: tuple[int, ...]) -> list[float]:
    if len(run) == 1:
        return [1.0]
    values = []
    for index in run:
        layout = page_layout(document[index])
        values.append(max(_MIN_EXTENT, panel_extent(document[index], layout)) if layout else _MIN_EXTENT)
    return values


def spread(source_extents: list[float], target_extents: list[float]) -> list[int]:
    """옛 묶음 쪽마다 새 묶음의 몇 번째 쪽에 얹을지 — 필기 흐름에서 겹치는 몫이 가장 큰 쪽, 비슷하면 앞쪽."""
    def bounds(extents: list[float]) -> list[tuple[float, float]]:
        total = sum(extents) or 1.0
        edges, start = [], 0.0
        for value in extents:
            edges.append((start / total, (start + value) / total))
            start += value
        return edges

    targets = bounds(target_extents)
    chosen = []
    for low, high in bounds(source_extents):
        shares = [max(0.0, min(high, end) - max(low, begin)) for begin, end in targets]
        best = max(shares)
        slack = _TIE_SHARE * (high - low)
        chosen.append(next(index for index, share in enumerate(shares) if share >= best - slack))
    return chosen


def _fill_gaps(match: MatchResult, source: list[PageFingerprint], target: list[PageFingerprint]) -> MatchResult:
    """두 짝 사이 같은 틈에 남은 옛·새 묶음을 틈 안에서 한 번 더 순서대로 짝짓는다."""
    out: list[PagePair] = []
    segment: list[PagePair] = []

    def flush() -> None:
        olds = [pair.source_index for pair in segment if pair.target_index is None]
        news = [pair.target_index for pair in segment if pair.source_index is None]
        if not olds or not news:
            out.extend(segment)
            segment.clear()
            return
        inner = match_fingerprints([source[i] for i in olds], [target[j] for j in news], _GAP_FILL_COST)
        # 틈 안의 결과를 새 쪽 순서로 다시 편다 — 짝 못 지은 옛 쪽은 앞 새 쪽 뒤에 남는다.
        for pair in inner.pairs:
            old = None if pair.source_index is None else olds[pair.source_index]
            new = None if pair.target_index is None else news[pair.target_index]
            out.append(PagePair(old, new, pair.distance, None))
        segment.clear()

    for pair in match.pairs:
        if pair.matched:
            flush()
            out.append(pair)
        else:
            segment.append(pair)
    flush()
    return MatchResult(tuple(out))


def _anchor(match: MatchResult) -> MatchResult:
    """똑같이 생긴 쪽이 떨어진 곳에 또 있어도(복습 슬라이드) **앞뒤 이웃이 바로 붙어 짝지어져** 있으면 순서가 이미
    답을 정했다 — 애매하다고 하지 않는다(요청 4·5 "순서 보존 규칙으로 최대한, 확인 필요를 무책임하게 띄우지 않는다").

    실측(병리 2주차(1) → 필기본): 옛 3·39쪽이 같은 슬라이드인데 둘 다 제자리(거리 0.001)로 짝지어졌고 앞뒤도 이어졌다.
    이웃이 끊겼거나 생김새부터 다르면 그대로 둔다.
    """
    pairs = list(match.pairs)
    matched = [index for index, pair in enumerate(pairs) if pair.matched]

    def steady(pair: PagePair) -> bool:
        return pair.distance is not None and pair.distance <= _UNCERTAIN_DISTANCE

    for order, index in enumerate(matched):
        pair = pairs[index]
        if pair.margin is None or pair.margin >= _UNCERTAIN_MARGIN or not steady(pair):
            continue
        sides = []
        if order > 0:
            before = pairs[matched[order - 1]]
            sides.append(steady(before) and before.source_index == pair.source_index - 1
                         and before.target_index == pair.target_index - 1)
        if order + 1 < len(matched):
            after = pairs[matched[order + 1]]
            sides.append(steady(after) and after.source_index == pair.source_index + 1
                         and after.target_index == pair.target_index + 1)
        if sides and all(sides):
            pairs[index] = PagePair(pair.source_index, pair.target_index, pair.distance, None)
    return MatchResult(tuple(pairs))


def match_notes(
    source_document,
    target_document,
    source_prints: list[PageFingerprint],
    target_prints: list[PageFingerprint],
    inked: set[int],
    mode: str,
) -> NotesMatch:
    source_runs = page_runs(source_document, mode == NOTES)
    target_runs = page_runs(target_document, True)

    # 맨 앞 전용 쪽끼리는 그대로 짝이다. 슬라이드가 없어 지문으로 비교할 것이 없다.
    front_pair = None
    if source_runs and target_runs and _front(target_document, target_runs[0]):
        if mode == NOTES and _front(source_document, source_runs[0]):
            front_pair = (source_runs.pop(0), target_runs.pop(0))

    run_source = [source_prints[run[0]] for run in source_runs]
    run_target = [target_prints[run[0]] for run in target_runs]
    reordered = pair_reordered(match_fingerprints(run_source, run_target), run_source, run_target)
    filled = _anchor(_fill_gaps(reordered.match, run_source, run_target))

    # 묶음 짝 → 쪽 짝. assigned[새 쪽] = [옛 쪽…], distance 는 묶음 짝의 거리.
    assigned: dict[int, list[int]] = {}
    distances: dict[int, float | None] = {}
    margins: dict[int, float | None] = {}
    kept: list[int] = []
    dropped: list[int] = []
    resized = 0

    def attach(sources: tuple[int, ...], targets: tuple[int, ...], distance, margin) -> None:
        if mode == NOTES:
            picks = spread(_extents(source_document, sources), _extents(target_document, targets))
        else:
            picks = [0] * len(sources)
        for old, pick in zip(sources, picks):
            new = targets[pick]
            assigned.setdefault(new, []).append(old)
            distances.setdefault(new, distance)
            margins.setdefault(new, margin)

    if front_pair is not None:
        attach(front_pair[0], front_pair[1], 0.0, None)
        resized += len(front_pair[0]) != len(front_pair[1])
    for pair in filled.pairs:
        if pair.matched:
            sources, targets = source_runs[pair.source_index], target_runs[pair.target_index]
            resized += len(sources) != len(targets)
            attach(sources, targets, pair.distance, pair.margin)
        elif pair.source_index is not None:
            for old in source_runs[pair.source_index]:
                if old in inked or mode == INTO_NOTES:
                    kept.append(old)
                else:
                    dropped.append(old)

    # 결과 순서: 새 쪽 순서 그대로. 남기는 옛 쪽은 바로 앞 옛 쪽이 얹힌 새 쪽 뒤에 둔다.
    host = {old: new for new, olds in assigned.items() for old in olds}
    after: dict[int, list[int]] = {}
    for old in sorted(kept):
        before = max((other for other in host if other < old), default=None)
        after.setdefault(-1 if before is None else host[before], []).append(old)

    pairs: list[PagePair] = [PagePair(old, None) for old in after.get(-1, [])]
    merged: dict[int, tuple[int, ...]] = {}
    for new in range(target_document.page_count):
        olds = sorted(assigned.get(new, []))
        if olds:
            pairs.append(PagePair(olds[0], new, distances.get(new), margins.get(new)))
            if len(olds) > 1:
                merged[new] = tuple(olds[1:])
        else:
            pairs.append(PagePair(None, new))
        pairs.extend(PagePair(old, None) for old in after.get(new, []))

    # 묶음 번호로 낸 순서 바뀜·후보·가장 닮은 쪽을 쪽 번호로.
    moved = tuple(sorted(old for run in reordered.moved for old in source_runs[run]))
    kept_set = set(kept)
    candidates = {old: target_runs[new][0] for run, new in reordered.candidates.items()
                  for old in source_runs[run] if old in kept_set}
    closest = {old: target_runs[new][0] for run, new in reordered.closest.items()
               for old in source_runs[run] if old in kept_set}
    page_reorder = Reorder(MatchResult(tuple(pairs)), moved, candidates, closest, (source_prints, target_prints))
    return NotesMatch(
        mode=mode,
        match=page_reorder.match,
        merged=merged,
        dropped=tuple(sorted(dropped)),
        reorder=page_reorder,
        resized_runs=resized,
        runs=tuple(target_runs),
    )


__all__ = ["INTO_NOTES", "NOTES", "NotesMatch", "match_notes", "notes_mode", "page_runs", "spread"]
