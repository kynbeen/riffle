"""새 판에서 쪽 순서가 바뀌어 짝을 못 지은 쪽을 다시 짝짓는다(명세 2026-09-25-01, 사용자 결정 2026-09-25).

쪽 짝짓기(``page_match``)는 순서를 지키며 짝짓는다. 새 판에서 슬라이드 몇 장의 순서가 바뀌면 엇갈린 쪽은
짝을 못 짓고 "새 PDF 에 없는 옛 쪽" 과 "새로 생긴 쪽" 으로 따로 남는다. 실측(병리학 1주차(3) → 필기본):
옛 33쪽과 새 35쪽의 거리 0.018, 옛 24쪽과 새 25쪽 0.153 — 보통 짝(중앙 0.001)과 같은 수준인데 짝이 없었다.

그런 둘이 **보통 짝만큼 닮았고**(``_UNCERTAIN_DISTANCE`` 이하) **다른 후보보다 뚜렷이 가까우면**
(``_UNCERTAIN_MARGIN`` 이상) 짝짓는다 — 엔진이 보통 짝을 "자신 있다" 고 보는 기준과 같다(원칙 0).
새 쪽 순서는 그대로 두고, 옛 쪽이 어느 새 쪽에 얹힐지만 정한다. 닮았지만 애매하면 짝짓지 않고 **후보**로만
돌려준다 — 화면이 두 쪽을 나란히 보여 사람이 정한다.

엔진은 바꾸지 않는다. Sleek 이 ``match_pages`` 를 사람 없이 직접 부르므로(``tests/test_sleek_engine_contract.py``)
그 결과는 그대로이고, 이 단계는 필기 옮기기의 분석에서만 덧붙는다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .page_match import (
    _UNCERTAIN_DISTANCE,
    _UNCERTAIN_MARGIN,
    MatchResult,
    PageFingerprint,
    PagePair,
    distance,
)


@dataclass(frozen=True)
class Reorder:
    match: MatchResult
    moved: tuple[int, ...] = ()                         # 다시 짝지은 옛 쪽(0부터)
    candidates: dict[int, int] = field(default_factory=dict)   # 애매한 옛 쪽 → 가장 닮은 새 쪽


def pair_reordered(
    match: MatchResult, source: list[PageFingerprint], target: list[PageFingerprint]
) -> Reorder:
    olds = [pair.source_index for pair in match.pairs if pair.target_index is None]
    news = [pair.target_index for pair in match.pairs if pair.source_index is None]
    if not olds or not news:
        return Reorder(match)
    near = {(old, new): distance(source[old], target[new]) for old in olds for new in news}

    def runner_up(old: int, new: int) -> float:
        others = [near[old, other] for other in news if other != new]
        others += [near[other, new] for other in olds if other != old]
        return min(others, default=math.inf)

    chosen: dict[int, PagePair] = {}
    candidates: dict[int, int] = {}
    for old in olds:
        new = min(news, key=lambda other: (near[old, other], other))
        best = near[old, new]
        if best > _UNCERTAIN_DISTANCE:
            continue
        margin = runner_up(old, new) - best
        if margin >= _UNCERTAIN_MARGIN:
            # 두 옛 쪽이 같은 새 쪽을 고를 수는 없다 — 둘 다 뚜렷이 가까울 수는 없으므로.
            chosen[new] = PagePair(old, new, best, None if math.isinf(margin) else margin)
        else:
            candidates[old] = new
    if not chosen:
        return Reorder(match, (), candidates)

    moved = {pair.source_index for pair in chosen.values()}
    pairs = []
    for pair in match.pairs:
        if pair.target_index is None and pair.source_index in moved:
            continue                                    # 옛 자리에서 빼고
        if pair.source_index is None and pair.target_index in chosen:
            pairs.append(chosen[pair.target_index])     # 새 쪽 자리에 얹는다
            continue
        pairs.append(pair)
    return Reorder(MatchResult(tuple(pairs)), tuple(sorted(moved)), candidates)


__all__ = ["Reorder", "pair_reordered"]
