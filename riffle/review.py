"""분석 결과에서 **사람이 볼 쪽**과 그 이유를 고른다(명세 2026-09-24-01 「필기 옮기기 — 확인할 쪽만」).

원칙 0: 기계가 자신 있게 맞춘 쪽은 기계가 처리하고, 사람에게는 자신 없는 쪽만 보인다. 여기서는
이유의 **종류**만 정하고, 사람이 읽을 문장은 화면 한 곳(web/src/review.ts)에 둔다.

이유 종류 — 한 쪽에 여러 까닭이 겹치면 위에 있는 것 하나만 댄다(사람이 먼저 알아야 할 순서):

- ``panel_ink``  — 옛 필기본의 오른쪽 필기 칸 위에 손필기가 있다. 칸의 글이 바뀌었을 수 있다.
- ``old_only``   — 새 PDF 에 짝이 없는 옛 쪽인데 필기가 있다. 필기를 잃지 않게 옛 쪽째 남긴다.
                   닮았지만 애매한 새 쪽이 있으면 ``candidate`` 로 함께 보낸다(화면이 나란히 보인다, reorder.py).
- ``different``  — 짝은 지었지만 생김새가 꽤 다르다.
- ``duplicate``  — 똑같이 생긴 쪽이 떨어진 곳에 또 있어 어느 쪽인지 확신이 없다.
- ``alignment``  — 쪽 안 내용의 자리가 많이 달라져 필기 위치를 확인해야 한다(문서 전체 판정).

사람을 부르지 않는 것: 새로 생긴 쪽(필기가 없으니 잃을 것이 없다 — 요약에서 숫자로만 알린다),
새 PDF 에 없는 필기 없는 옛 쪽(묻지 않고 제자리에 남긴다 — 합집합, 명세 2026-09-25-01), 자신 있게 맞춘 쪽.
"""
from __future__ import annotations

from .page_match import _UNCERTAIN_DISTANCE, _UNCERTAIN_MARGIN

REASONS = ("panel_ink", "old_only", "different", "duplicate", "alignment")


def _reason(slot: dict, panel: set[int], blank: set[int], alignment_doubtful: bool) -> str | None:
    source, target = slot.get("source_index"), slot.get("target_index")
    if source is not None and source in panel:
        return "panel_ink"
    if target is None:
        return None if source in blank else "old_only"
    if source is None:
        return None
    distance, margin = slot.get("distance"), slot.get("margin")
    if distance is not None and distance > _UNCERTAIN_DISTANCE:
        return "different"
    if margin is not None and margin < _UNCERTAIN_MARGIN:
        return "duplicate"
    if alignment_doubtful:
        return "alignment"
    if not slot.get("confirmed", True):
        # 짝짓기 지표가 없는데 확인이 필요한 경우(사람이 고친 대응 등) — 생김새부터 보게 한다.
        return "different"
    return None


def review(inspection: dict) -> dict:
    """``TransferInspection.as_dict()`` 에서 확인할 쪽과 요약을 만든다."""
    plan = inspection.get("plan") or {}
    slots = plan.get("slots") or []
    panel = set(inspection.get("panel_ink_sources") or [])
    blank = {page["source_index"] for page in inspection.get("source_order") or []
             if page.get("blank") and page.get("source_index") is not None}
    alignment = inspection.get("alignment") or {}
    doubtful = bool(alignment.get("requires_confirmation"))
    candidates = {source: target for source, target in inspection.get("pair_candidates") or []}

    items = []
    matched = new_pages = kept_old = kept_blank = 0
    for position, slot in enumerate(slots):
        source, target = slot.get("source_index"), slot.get("target_index")
        if source is not None and target is not None:
            matched += 1
        elif source is None:
            new_pages += 1
        else:
            kept_old += 1
            kept_blank += source in blank
        reason = _reason(slot, panel, blank, doubtful)
        if reason:
            item = {"slot": position, "source_index": source, "target_index": target, "reason": reason}
            if reason == "old_only" and source in candidates:
                item["candidate"] = candidates[source]
            items.append(item)
    return {
        "items": items,
        # 필기 없는 옛 쪽. 화면에서 짝을 바꿔 밀려난 옛 쪽을 사람에게 보일지(필기 있음) 조용히 남길지(없음) 여기로 안다.
        "blank_sources": sorted(blank),
        # 순서가 바뀌어 다시 짝지은 옛 쪽. 모든 쪽 보기에서 표시한다.
        "moved_sources": sorted(inspection.get("moved_sources") or []),
        "summary": {
            "matched": matched,                     # 옛 쪽과 새 쪽을 짝지은 수
            "automatic": matched - sum(1 for item in items if item["target_index"] is not None
                                       and item["source_index"] is not None),
            "attention": len(items),
            "new_pages": new_pages,                 # 새 PDF 에만 있는 쪽 — 필기 없이 들어간다
            "kept_old": kept_old,                   # 새 PDF 에 없어 옛 쪽째 남기는 쪽(필기 없는 쪽 포함)
            "kept_blank": kept_blank,               # 그중 필기가 없는 쪽 — 사람을 부르지 않고 알리기만 한다
            # 새 판에서 순서가 바뀌어 다시 짝지은 옛 쪽 — 자신 있게 짝지었으니 알리기만 한다(원칙 0)
            "moved": len(inspection.get("moved_sources") or []),
            "result_pages": matched + new_pages + kept_old,
        },
    }


__all__ = ["REASONS", "review"]
