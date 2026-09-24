"""``end_tag.bin`` 과 파일 끝 꼬리표의 노트 높이·시각을 고친다.

Samsung Notes 는 노트 머리 정보를 두 벌 둔다. ZIP 안의 ``end_tag.bin`` 과, ZIP 종료 기록 뒤에 붙는
148바이트 안팎의 꼬리표다. 둘 다 같은 구조이고, 그 안에 **노트 전체 높이**가 ``note.note`` 와 별도로
들어 있다. 쪽을 더한 결과에서 이 값을 옛 높이로 두면 태블릿에서 늘어난 만큼 끝 쪽이 잘려 보인다
(2026-09-24 진단: Samsung Notes 가 저장한 파일은 모두 세 높이가 같았고, Riffle 결과만 달랐다).

구조는 공개 역공학 프로젝트 Dietrich 의 ``samsung_end_tag`` 정의를 따르고 실제 파일로 확인했다.
필요한 칸만 읽고, 길이가 바뀌지 않게 제자리에서 덮어쓴다.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# 표시용 시각은 파일마다 ms 이기도 하고 µs 이기도 했다. 크기로 단위를 가려 같은 단위로 쓴다.
_MICROSECOND_FLOOR = 10**14


class SdocxEndTagError(RuntimeError):
    pass


@dataclass(frozen=True)
class EndTagFields:
    modified: int
    note_height: int
    created: int
    display_created: int
    display_modified: int


_FIELDS = (
    ("i", "format_version"), ("s", "note_id"), ("Q", "modified"), ("i", "property_flags"),
    ("s", "cover_image"), ("i", "note_width"), ("f", "note_height"), ("s", "title"),
    ("i", "thumbnail_width"), ("i", "thumbnail_height"), ("s", "app_patch_name"),
    ("i", "min_format_version"), ("Q", "created"), ("i", "last_viewed_page_index"),
    ("H", "page_mode"), ("H", "document_type"), ("s", "owner_id"), ("i", "reserved_1"),
    ("i", "reserved_2"), ("Q", "display_created"), ("Q", "display_modified"),
)


def _offsets(blob: bytes) -> dict[str, tuple[str, int]]:
    """필요한 칸의 (형식, 위치). 첫 2바이트는 본문 길이다."""
    if len(blob) < 2:
        raise SdocxEndTagError("end_tag 가 너무 짧습니다.")
    end = 2 + struct.unpack_from("<H", blob, 0)[0]
    if end > len(blob):
        raise SdocxEndTagError("end_tag 본문 길이가 파일보다 깁니다.")
    position = 2
    offsets: dict[str, tuple[str, int]] = {}
    for kind, name in _FIELDS:
        if kind == "s":
            if position + 2 > end:
                raise SdocxEndTagError(f"end_tag 의 {name} 칸이 잘렸습니다.")
            length = struct.unpack_from("<H", blob, position)[0]
            position += 2 + (0 if length == 0xFFFF else length * 2)
            continue
        size = struct.calcsize("<" + kind)
        if position + size > end:
            raise SdocxEndTagError(f"end_tag 의 {name} 칸이 잘렸습니다.")
        offsets[name] = (kind, position)
        position += size
    return offsets


def read_end_tag(blob: bytes) -> EndTagFields:
    offsets = _offsets(blob)

    def value(name: str):
        kind, position = offsets[name]
        return struct.unpack_from("<" + kind, blob, position)[0]

    return EndTagFields(
        modified=value("modified"),
        note_height=round(value("note_height")),
        created=value("created"),
        display_created=value("display_created"),
        display_modified=value("display_modified"),
    )


def _display_time(previous: int, now_us: int) -> int:
    if previous == 0:
        return 0
    return now_us if previous >= _MICROSECOND_FLOOR else now_us // 1000


def patch_end_tag(
    blob: bytes, *, note_height: int | None = None, now_us: int | None = None
) -> bytes:
    """노트 높이와(주면) 만든·고친 시각을(주면) 바꾼 사본. 길이는 그대로다."""
    offsets = _offsets(blob)
    patched = bytearray(blob)
    if note_height is not None:
        struct.pack_into("<f", patched, offsets["note_height"][1], float(note_height))
    if now_us is not None:
        current = read_end_tag(blob)
        struct.pack_into("<Q", patched, offsets["created"][1], now_us)
        struct.pack_into("<Q", patched, offsets["modified"][1], now_us)
        struct.pack_into("<Q", patched, offsets["display_created"][1],
                         _display_time(current.display_created, now_us))
        struct.pack_into("<Q", patched, offsets["display_modified"][1],
                         _display_time(current.display_modified, now_us))
    return bytes(patched)


__all__ = ["EndTagFields", "SdocxEndTagError", "patch_end_tag", "read_end_tag"]
