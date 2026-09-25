"""사람이 확정한 필기 옮기기를 다시 돌려 볼 **사례**로 남긴다(명세 2026-09-25-01 단위 4b).

저장할 때마다 이 PC 에 JSON 한 개: 옛·새 쪽 지문(쪽마다 16×16 밝기 256칸), 기계가 낸 짝, 사람이 확정해 저장한 짝.
지문만 있으면 어떤 판정이든 나중에 그대로 다시 돌려 사람이 확정한 짝과 비교할 수 있다(``tools/check_reorder.py --cases``).

**남기지 않는 것:** 파일 이름(필기한 사람의 이름이 들어 있다), 쪽 그림·필기, PDF. 지문은 256칸으로 뭉갠 밝기라 글자를
되살릴 수 없다. **배포된 웹(Render)에서는 남기지 않는다** — 받는 쪽 동의 절차는 명세 2026-09-25-02 의 일이다.
남기기에 실패해도 저장은 그대로 성공한다(사례는 덤이다).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .page_match import MatchResult, PageFingerprint, match_fingerprints

LOG = logging.getLogger("riffle.cases")
CASE_VERSION = 1


def cases_dir() -> Path:
    override = os.environ.get("RIFFLE_CASES_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Riffle" / "cases"


def _prints(prints: list[PageFingerprint]) -> dict:
    return {
        "cells": [[round(value, 2) for value in page.cells] for page in prints],
        "aspect": [round(page.aspect, 4) for page in prints],
    }


def _rows(page_plan: list[dict]) -> list[dict]:
    rows = []
    for row in page_plan:
        item = {
            "source": row.get("source_index"),
            "target": row.get("target_index"),
            "excluded": bool(row.get("excluded", False)),
            "confirmed": bool(row.get("confirmed", False)),
        }
        if row.get("merged"):
            item["merged"] = list(row["merged"])     # 함께 얹은 옛 쪽(명세 2026-09-25-03) — 있을 때만
        rows.append(item)
    return rows


def build_case(inspection: Any, page_plan: list[dict], fmt: str) -> dict | None:
    """분석 결과(지문을 쥔)와 저장한 쪽 계획으로 사례 하나. 지문이 없으면(옛 분석) 만들지 않는다."""
    prints = getattr(inspection, "prints", None)
    match: MatchResult | None = getattr(inspection, "match", None)
    if not prints or match is None:
        return None
    source, target = prints
    return {
        "case_version": CASE_VERSION,
        "app_version": __version__,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "format": fmt,
        "source": _prints(source),
        "target": _prints(target),
        "machine": [[pair.source_index, pair.target_index] for pair in match.pairs],
        "moved": list(getattr(inspection, "moved_sources", ()) or ()),
        "candidates": [list(pair) for pair in getattr(inspection, "pair_candidates", ()) or ()],
        "final": _rows(page_plan),
    }


def record_case(inspection: Any, page_plan: list[dict], fmt: str, directory: Path | None = None) -> Path | None:
    try:
        case = build_case(inspection, page_plan, fmt)
        if case is None:
            return None
        root = directory or cases_dir()
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = root / f"{stamp}-{secrets.token_hex(3)}.json"
        path.write_text(json.dumps(case, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return path
    except Exception:                                   # 사례는 덤이다 — 저장을 막지 않는다
        LOG.exception("사례를 남기지 못했습니다")
        return None


def load_prints(block: dict) -> list[PageFingerprint]:
    return [PageFingerprint(index=index, cells=tuple(cells), aspect=aspect)
            for index, (cells, aspect) in enumerate(zip(block["cells"], block["aspect"]))]


def score_case(case: dict, pair_fn: Callable) -> Counter:
    """사례를 지금 판정으로 다시 돌려 사람이 확정한 짝과 비교한다. 사람이 뺀 쪽은 채점하지 않는다.

    맞음 · 조용히 틀림(다른 쪽이나 '짝 없음' 을 자신 있게 냄) · 틀림(카드) · 후보 · 놓침.
    """
    source, target = load_prints(case["source"]), load_prints(case["target"])
    result = pair_fn(match_fingerprints(source, target), source, target)
    got = {pair.source_index: pair for pair in result.match.pairs if pair.source_index is not None}
    tally: Counter = Counter()
    for row in case["final"]:
        s, t = row["source"], row["target"]
        if s is None or row["excluded"]:
            continue
        pair = got.get(s)
        if pair is None:
            continue
        if pair.target_index == t:
            tally["맞음"] += 1
        elif pair.target_index is not None and not pair.confident:
            tally["틀림(카드)"] += 1
        elif pair.target_index is None:
            tally["후보" if result.candidates.get(s) == t else "놓침"] += 1
        else:
            tally["조용히 틀림"] += 1
    return tally


def load_cases(directory: Path) -> list[tuple[Path, dict]]:
    cases = []
    for path in sorted(directory.glob("*.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if case.get("case_version") == CASE_VERSION:
            cases.append((path, case))
    return cases


__all__ = ["build_case", "cases_dir", "load_cases", "load_prints", "record_case", "score_case"]
