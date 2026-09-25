"""Goodnotes 6 필기를 새 PDF 배경 위로 옮긴다.

``.goodnotes`` 는 ZIP이고, 필기는 ``notes/<쪽 내용 ID>`` 저널에, 배경은
``attachments/<첨부 ID>`` PDF에 들어 있다. 둘을 이어 주는 것은 ``index.events.pb`` 의
용지·쪽 생성·쪽 연결 기록이다(자세한 구조는 ``goodnotes_archive``).

필기 저널의 알려진 획 좌표는 새 PDF의 캔버스에 맞춰 변환하며, 알 수 없는 데이터는
보존한다. 저장 뒤 배경 참조·캔버스 비율·필기 수를 다시 읽어 검증한다.

쪽을 더하거나 지우거나 순서를 바꾸면 쪽 ID가 새로 필요하므로 아카이브를 다시 만든다.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from PIL import Image

from .ink_layer import GOODNOTES
from .ink_transform import canvas_transform
from .alignment import Alignment
from .goodnotes_archive import (
    GoodnotesDocument,
    GoodnotesPage,
    background_pdf,
    build_events,
    build_index,
    new_page_ids,
    read_document,
    safe_members,
)
from .goodnotes_ink import (
    count_goodnotes_strokes,
    render_goodnotes_ink,
    transform_goodnotes_journal,
)
from .goodnotes_proto import GoodnotesTransferError, field_values, split_delimited
from .page_match import MatchResult
from .page_plan import PagePlan
from .transfer_plan import (
    SourceInk,
    TransferInspection,
    alignment_for_plan,
    build_planned_background_pdf,
    compose_slot_ink,
    inspect_pdfs,
    open_pdf,
    preview_slot,
)

_SOURCE_LABEL = "Goodnotes 배경 PDF"


def _open_archive(source: Path) -> ZipFile:
    try:
        return ZipFile(source, "r")
    except BadZipFile as exc:
        raise GoodnotesTransferError(
            f"Goodnotes 파일을 열 수 없습니다: {source.name}"
        ) from exc


def _checked_paths(source: str | Path, target: str | Path) -> tuple[Path, Path]:
    source_path = Path(source).expanduser().resolve()
    target_path = Path(target).expanduser().resolve()
    if source_path.suffix.lower() != ".goodnotes" or not source_path.is_file():
        raise GoodnotesTransferError("필기가 들어 있는 .goodnotes 파일을 선택하세요.")
    if target_path.suffix.lower() != ".pdf" or not target_path.is_file():
        raise GoodnotesTransferError("새 배경으로 사용할 PDF를 선택하세요.")
    return source_path, target_path


def _stroke_counts(archive: ZipFile, document: GoodnotesDocument) -> list[int]:
    counts = []
    for page in document.pages:
        if page.notes_member is None:
            counts.append(0)
            continue
        counts.append(count_goodnotes_strokes(archive.read(page.notes_member)))
    return counts


def inspect_goodnotes_transfer(
    source_goodnotes: str | Path,
    target_pdf: str | Path,
    *,
    progress: Callable[[str], None] | None = None,
) -> TransferInspection:
    source, target = _checked_paths(source_goodnotes, target_pdf)
    if progress:
        progress("structure")
    with _open_archive(source) as archive:
        members = safe_members(archive)
        document = read_document(archive, members)
        embedded_pdf = background_pdf(archive, document)
        stroke_counts = _stroke_counts(archive, document)
        ink = source_ink(archive, document)
    return inspect_pdfs(
        source_name=source.name,
        target_name=target.name,
        embedded_pdf=embedded_pdf,
        target=target,
        ink=ink,
        source_label=_SOURCE_LABEL,
        error=GoodnotesTransferError,
        progress=progress,
        annotated_page_count=sum(count > 0 for count in stroke_counts),
        stroke_cache_count=sum(stroke_counts),
        embedded_pdf_name=f"{len(document.attachments)}개 첨부 배경",
        source_page_count=len(document.pages),
        target_size=target.stat().st_size,
    )


def source_ink(archive: ZipFile, document: GoodnotesDocument) -> SourceInk:
    """쪽 순서 = 배경 PDF 쪽 번호. 판정·배치는 공통 층이 한다(명세 2026-09-25-03)."""
    counts: dict[int, int] = {}
    pages: dict[int, tuple[bytes, tuple[float, float]]] = {}
    for index, page in enumerate(document.pages):
        payload = archive.read(page.notes_member) if page.notes_member else b""
        counts[index] = count_goodnotes_strokes(payload) if payload else 0
        if counts[index]:
            pages[index] = (payload, page.canvas)
    return SourceInk(GOODNOTES, pages, stroke_counts=counts)


def _planned_background_bytes(
    embedded_pdf: bytes, target: Path, plan: PagePlan, alignment: Alignment | None
) -> bytes:
    """결과 쪽 순서대로 배경 PDF를 만든다.

    Goodnotes 첨부는 쪽마다 "이 첨부의 몇 쪽"을 가리킨다. 결과에서는 첨부 하나에 쪽을
    결과 순서 그대로 담아, 쪽 번호가 곧 결과 쪽 번호가 되게 한다.
    """
    if all(
        slot.target_index == output_index
        for output_index, slot in enumerate(plan.slots)
    ):
        return target.read_bytes()
    source_document = open_pdf(embedded_pdf, _SOURCE_LABEL, error=GoodnotesTransferError)
    try:
        target_document = open_pdf(target, "대상 PDF", error=GoodnotesTransferError)
    except Exception:
        source_document.close()
        raise
    with source_document, target_document:
        return build_planned_background_pdf(
            source_document,
            target_document,
            plan,
            alignment,
            error=GoodnotesTransferError,
        )


def _thumbnail(background: bytes, notes: bytes | None, canvas: tuple[float, float]) -> bytes:
    """서재에 보이는 미리보기. 새 배경 첫 쪽 위에 그 쪽 필기를 얹는다."""
    from . import pdf as pymupdf

    with pymupdf.open(stream=background, filetype="pdf") as document:
        page = document[0]
        scale = min(386 / max(page.rect.width, 1.0), 3.0)
        payload = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
    with Image.open(BytesIO(payload)) as rendered:
        sheet = rendered.convert("RGB")
        if notes:
            ink, _count = render_goodnotes_ink(notes, sheet.size, canvas)
            with Image.open(BytesIO(ink)) as layer:
                sheet.paste(layer, (0, 0), layer)
        output = BytesIO()
        sheet.save(output, format="JPEG", quality=82)
    return output.getvalue()


def _copy_member(archive: ZipFile, members: dict, name: str, default: bytes) -> bytes:
    return archive.read(name) if name in members else default


def transfer_goodnotes_handwriting(
    source_goodnotes: str | Path,
    target_pdf: str | Path,
    output_goodnotes: str | Path,
    *,
    match_override: MatchResult | None = None,
    plan_override: PagePlan | None = None,
) -> dict:
    source, target = _checked_paths(source_goodnotes, target_pdf)
    output = Path(output_goodnotes).expanduser().resolve()
    if output.suffix.lower() != ".goodnotes":
        output = output.with_name(output.name + ".goodnotes")
    if output == source:
        raise GoodnotesTransferError("원본 Goodnotes 파일을 덮어쓸 수 없습니다.")

    inspection = inspect_goodnotes_transfer(source, target)
    if plan_override is not None:
        plan = plan_override
    elif match_override is not None:
        plan = PagePlan.from_match(match_override, inspection.source_page_count, inspection.page_count)
    else:
        plan = inspection.page_plan()
    relocate = inspection.notes_mode == "notes"

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.stem}-", suffix=".tmp.goodnotes"
    )
    os.close(fd)
    temporary = Path(temp_name)
    try:
        with _open_archive(source) as archive:
            members = safe_members(archive)
            if any(65 in field_values(record)
                   for record in split_delimited(archive.read("index.events.pb"))):
                raise GoodnotesTransferError(
                    "기존 Goodnotes 목차의 보존·병합은 아직 지원하지 않습니다. "
                    "목차가 사라지지 않도록 저장을 중단했습니다."
                )
            document = read_document(archive, members)
            embedded_pdf = background_pdf(archive, document)
            ink = source_ink(archive, document)
            alignment = inspection.alignment
            if match_override is not None or plan_override is not None:
                alignment = alignment_for_plan(
                    embedded_pdf,
                    target,
                    plan,
                    source_label=_SOURCE_LABEL,
                    error=GoodnotesTransferError,
                )
            attachment = _planned_background_bytes(
                embedded_pdf, target, plan, alignment
            )

            reference = next(
                (
                    document.pages[slot.source_index]
                    for slot in plan.slots
                    if slot.source_index is not None
                ),
                document.pages[0],
            )
            slots: list[tuple[GoodnotesPage, str, str]] = []
            notes_members: list[tuple[str, bytes]] = []
            index_pairs: list[tuple[str, str]] = []
            expected_stroke_counts: list[int] = []
            source_document = open_pdf(
                embedded_pdf, _SOURCE_LABEL, error=GoodnotesTransferError
            )
            try:
                target_document = open_pdf(target, "대상 PDF", error=GoodnotesTransferError)
            except Exception:
                source_document.close()
                raise
            with source_document, target_document:
                reference_index = next(
                    (
                        slot.source_index
                        for slot in plan.slots
                        if slot.source_index is not None
                    ),
                    0,
                )
                for slot in plan.slots:
                    page = (
                        reference
                        if slot.source_index is None
                        else document.pages[slot.source_index]
                    )
                    transform = None
                    if slot.target_index is not None:
                        transform_source = (
                            reference_index
                            if slot.source_index is None
                            else slot.source_index
                        )
                        transform = canvas_transform(
                            source_document[transform_source],
                            target_document[slot.target_index],
                            document.pages[transform_source].canvas,
                            alignment,
                        )
                        page = replace(
                            page,
                            canvas=(transform.target_width, transform.target_height),
                        )
                    entity_id, content_id = new_page_ids()
                    slots.append((page, entity_id, content_id))
                    member = f"notes/{content_id}"
                    # 새로 끼어든 쪽은 필기가 없다. 빈 저널도 앱이 받아들이는 형태다.
                    payload = b""
                    expected_stroke_count = 0
                    if slot.source_index is not None:
                        expected_stroke_count = sum(
                            ink.stroke_counts.get(index, 0) for index in slot.sources
                        )
                        composed = None
                        if slot.target_index is not None:
                            composed, _placement = compose_slot_ink(
                                ink, source_document, target_document, slot.target_index,
                                slot.sources, alignment, relocate=relocate,
                            )
                        if composed is not None:
                            payload = composed
                        elif page.notes_member:
                            payload = archive.read(page.notes_member)
                            if transform is not None:
                                payload = transform_goodnotes_journal(payload, transform)
                    notes_members.append((member, payload))
                    index_pairs.append((content_id, member))
                    expected_stroke_counts.append(expected_stroke_count)

            attachment_id = str(uuid.uuid4()).upper()
            events = build_events(
                document,
                slots,
                attachment_id,
                len(attachment),
                target.stem,
            )
            search_blob = b""
            for identifier, member in document.attachments.items():
                candidate = f"search/{identifier}"
                if candidate in members:
                    search_blob = archive.read(candidate)
                    break
            first_notes = notes_members[0][1] if notes_members else b""
            thumbnail = _thumbnail(attachment, first_notes, slots[0][0].canvas)

            with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as result:
                result.writestr("schema.pb", archive.read("schema.pb"))
                result.writestr(
                    "document.info.pb", _copy_member(archive, members, "document.info.pb", b"")
                )
                result.writestr("index.events.pb", events)
                result.writestr("index.notes.pb", build_index(index_pairs))
                result.writestr(
                    "index.attachments.pb",
                    build_index([(attachment_id, f"attachments/{attachment_id}")]),
                )
                result.writestr(
                    "index.search.pb",
                    build_index(
                        [(attachment_id, f"search/{attachment_id}")],
                        {attachment_id: [(3, 0, 1)]},
                    ),
                )
                result.writestr(f"search/{attachment_id}", search_blob)
                result.writestr(f"attachments/{attachment_id}", attachment)
                for member, payload in notes_members:
                    result.writestr(member, payload)
                result.writestr("thumbnail.jpg", thumbnail)

        _validate_output(temporary, plan, attachment, expected_stroke_counts)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "path": str(output),
        "page_count": len(plan.slots),
        "annotated_page_count": inspection.annotated_page_count,
        "stroke_count": inspection.stroke_cache_count,
        "mode": inspection.mode,
        "new_page_count": sum(slot.source_index is None for slot in plan.slots),
        "source_only_count": sum(slot.target_index is None for slot in plan.slots),
    }


def _validate_output(
    path: Path,
    plan: PagePlan,
    attachment: bytes,
    expected_stroke_counts: list[int],
) -> None:
    """저장한 파일을 다시 읽어 배경·캔버스·필기 수를 함께 확인한다."""
    from . import pdf as pymupdf

    with _open_archive(path) as archive:
        members = safe_members(archive)
        document = read_document(archive, members)
        if len(document.pages) != len(plan.slots):
            raise GoodnotesTransferError("저장된 Goodnotes의 페이지 수가 달라졌습니다.")
        if len(document.attachments) != 1:
            raise GoodnotesTransferError("저장된 Goodnotes의 배경 첨부가 하나가 아닙니다.")
        attachment_id, member = next(iter(document.attachments.items()))
        if archive.read(member) != attachment:
            raise GoodnotesTransferError("저장된 Goodnotes의 배경 검증에 실패했습니다.")
        with pymupdf.open(stream=attachment, filetype="pdf") as background:
            if background.page_count != len(document.pages):
                raise GoodnotesTransferError("저장된 Goodnotes의 배경 페이지 수가 다릅니다.")
            for index, page in enumerate(document.pages):
                if page.attachment_id != attachment_id or page.source_page != index + 1:
                    raise GoodnotesTransferError(
                        f"저장된 Goodnotes {index + 1}쪽의 배경 참조가 어긋났습니다."
                    )
                if page.notes_member is None:
                    raise GoodnotesTransferError(
                        f"저장된 Goodnotes {index + 1}쪽의 필기 항목을 찾을 수 없습니다."
                    )
                page_ratio = page.canvas[0] / max(page.canvas[1], 1e-9)
                pdf_rect = background[index].rect
                pdf_ratio = float(pdf_rect.width) / max(float(pdf_rect.height), 1e-9)
                if abs(page_ratio - pdf_ratio) > 0.002:
                    raise GoodnotesTransferError(
                        f"저장된 Goodnotes {index + 1}쪽의 캔버스 비율이 PDF와 다릅니다."
                    )
                actual_count = count_goodnotes_strokes(archive.read(page.notes_member))
                if actual_count != expected_stroke_counts[index]:
                    raise GoodnotesTransferError(
                        f"저장된 Goodnotes {index + 1}쪽의 필기 수가 달라졌습니다."
                    )


def preview_goodnotes_transfer(
    source_goodnotes: str | Path,
    target_pdf: str | Path,
    page_index: int,
    inspection: TransferInspection | None = None,
    *,
    source_index_override: int = -2,
    sources: tuple[int, ...] | None = None,
) -> tuple[bytes, bytes, bytes, int]:
    """이전 배경과 새 배경, 그리고 그 위에 얹을 Goodnotes 필기 레이어를 그린다.

    새 쪽 자리는 저장과 같은 공통 길(``preview_slot``)로 그린다. ``sources`` 는 그 새 쪽에 얹을 옛 쪽들.
    """
    from . import pdf as pymupdf

    source, target = _checked_paths(source_goodnotes, target_pdf)
    inspection = inspection or inspect_goodnotes_transfer(source, target)
    target_index = max(0, min(int(page_index), inspection.page_count - 1))
    if source_index_override == -2:
        source_index = next(
            (
                pair.source_index
                for pair in inspection.match.pairs
                if pair.target_index == target_index
            ),
            None,
        )
    elif source_index_override < 0:
        source_index = None
    else:
        source_index = int(source_index_override)
    if source_index is not None and not 0 <= source_index < (inspection.source_page_count or 0):
        source_index = None

    with _open_archive(source) as archive:
        members = safe_members(archive)
        document = read_document(archive, members)
        embedded_pdf = background_pdf(archive, document)
        notes = b""
        canvas = document.pages[0].canvas
        ink = source_ink(archive, document)
        if source_index is not None:
            page = document.pages[source_index]
            canvas = page.canvas
            if page.notes_member:
                notes = archive.read(page.notes_member)

    if page_index == -1:
        from .transfer_plan import render_source_background

        if source_index is None:
            raise GoodnotesTransferError("보존할 원본 쪽을 지정하세요.")
        background = render_source_background(embedded_pdf, source_index, error=GoodnotesTransferError)
        with Image.open(BytesIO(background)) as image:
            ink, count = render_goodnotes_ink(notes, image.size, canvas)
        return background, background, ink, count

    if sources is not None:
        chosen = tuple(sources)
    else:
        chosen = () if source_index is None else (source_index,)
        if source_index_override == -2:
            chosen += dict(inspection.merged).get(target_index, ())
    return preview_slot(
        ink, embedded_pdf, target, target_index, chosen, inspection, _render_on_canvas,
        source_label=_SOURCE_LABEL, error=GoodnotesTransferError,
    )


def _render_on_canvas(payload: bytes | None, width: int, height: int, canvas: tuple[float, float]) -> tuple[bytes, int]:
    """이미 새 캔버스 좌표로 옮긴 저널을 그린다."""
    if not payload:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue(), 0
    return render_goodnotes_ink(payload, (width, height), canvas)


__all__ = [
    "GoodnotesTransferError",
    "inspect_goodnotes_transfer",
    "preview_goodnotes_transfer",
    "transfer_goodnotes_handwriting",
]
