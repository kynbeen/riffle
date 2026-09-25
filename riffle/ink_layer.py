"""필기 형식마다 다른 것 세 가지만 여기 모은다(명세 2026-09-25-03 「공통 층」, 사용자 요청 2026-09-25).

Riffle 은 Samsung Notes 를 정본으로 두고 Notewise·Goodnotes 도 **완전히 같게** 동작해야 한다. 판정(쪽 짝·반복
나누기·여백 자리)은 형식과 무관하게 :mod:`page_ink` 한 곳에서 하고, 형식마다 다른 것은 쪽 하나의 필기 바이트에 대한
세 동작뿐이다.

- ``boxes``      — 맨 위 객체(요소)마다 획 점들의 상자(그 쪽 캔버스 좌표). 획이 아니면 ``None``.
- ``transform``  — 객체마다 다른 변환을 적용한다. 목록 순서는 ``boxes`` 와 같다.
- ``merge``      — 다른 쪽들의 객체를 바이트째 뒤에 붙인다(옛 반복 쪽 여럿 → 새 쪽 하나).

획은 다시 쓰지 않는다 — 좌표 숫자만 제자리에서 바꾸고, 레코드는 바이트째 옮긴다(원칙 7). 뜻을 모르는 객체는
상자가 ``None`` 이고 쪽 변환을 따른다(형식마다 기존과 같게 — 좌표를 모르는 객체는 건드리지 않는다).
"""
from __future__ import annotations

import base64
from typing import Protocol, Sequence

from .ink_transform import CanvasTransform

Box = tuple[float, float, float, float]


class InkCodec(Protocol):
    def boxes(self, payload: bytes) -> list[Box | None]: ...

    def transform(self, payload: bytes, page: CanvasTransform,
                  per_object: Sequence[CanvasTransform] | None) -> bytes: ...

    def merge(self, base: bytes, others: Sequence[bytes]) -> bytes: ...


class SamsungNotesInk:
    """``.page`` 바이트. 레이어 안의 맨 위 객체가 단위다(묶음 객체의 자식은 부모를 따라간다)."""

    def boxes(self, payload: bytes) -> list[Box | None]:
        from .sdocx_ink import object_boxes

        return object_boxes(payload)

    def transform(self, payload: bytes, page: CanvasTransform,
                  per_object: Sequence[CanvasTransform] | None) -> bytes:
        from .sdocx_ink import transform_page_ink, transform_page_objects

        if per_object is None:
            return transform_page_ink(payload, page)
        return transform_page_objects(payload, page, list(per_object))

    def merge(self, base: bytes, others: Sequence[bytes]) -> bytes:
        from .sdocx_ink import merge_page_objects

        return merge_page_objects(base, list(others))


class NotewiseInk:
    """Base64 로 감싼 쪽 메시지. 필드 4 하나가 객체 하나이고, 객체마다 자기 행렬(필드 3)을 갖는다."""

    @staticmethod
    def _message(payload: bytes) -> bytes:
        return base64.b64decode(payload, validate=False)

    @staticmethod
    def _wrap(message: bytes) -> bytes:
        # Notewise 는 Android Base64.DEFAULT(76자 줄바꿈)를 쓴다 — 표기를 지켜야 쪽 순서가 유지된다(notewise_transfer).
        return base64.encodebytes(message)

    def boxes(self, payload: bytes) -> list[Box | None]:
        from .notewise_ink import object_stroke
        from .notewise_proto import iter_fields

        boxes: list[Box | None] = []
        for number, wire, value in iter_fields(self._message(payload)):
            if number != 4 or wire != 2:
                continue
            stroke = object_stroke(bytes(value))
            if stroke is None:
                boxes.append(None)
                continue
            xs = [x for x, _y in stroke.points]
            ys = [y for _x, y in stroke.points]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        return boxes

    def transform(self, payload: bytes, page: CanvasTransform,
                  per_object: Sequence[CanvasTransform] | None) -> bytes:
        from .notewise_proto import encode_field, iter_fields
        from .notewise_transfer import _transform_page_object

        if per_object is None:
            per_object = [page] * len(self.boxes(payload))
        output = bytearray()
        index = 0
        for number, wire, value in iter_fields(self._message(payload)):
            if number == 4 and wire == 2:
                if index >= len(per_object):
                    raise ValueError("객체마다 줄 변환의 수가 객체 수와 다릅니다.")
                transform = per_object[index]
                index += 1
                if not transform.identity:
                    value = _transform_page_object(bytes(value), transform)
            output.extend(encode_field(number, wire, value))
        if index != len(per_object):
            raise ValueError("객체마다 줄 변환의 수가 객체 수와 다릅니다.")
        return self._wrap(bytes(output))

    def merge(self, base: bytes, others: Sequence[bytes]) -> bytes:
        from .notewise_proto import encode_field, iter_fields

        extra = [bytes(value) for other in others for number, wire, value in iter_fields(self._message(other))
                 if number == 4 and wire == 2]
        if not extra:
            return base
        fields = list(iter_fields(self._message(base)))
        last = max((position for position, (number, wire, _v) in enumerate(fields) if number == 4 and wire == 2),
                   default=len(fields) - 1)
        output = bytearray()
        for position, (number, wire, value) in enumerate(fields):
            output.extend(encode_field(number, wire, value))
            if position == last:
                for item in extra:
                    output.extend(encode_field(4, 2, item))
        if not fields:
            for item in extra:
                output.extend(encode_field(4, 2, item))
        return self._wrap(bytes(output))


class GoodnotesInk:
    """쪽 저널(``notes/<내용 ID>``). 스키마 25 이상은 (머리말, 본문) 두 레코드가 요소 하나다."""

    def boxes(self, payload: bytes) -> list[Box | None]:
        from .goodnotes_ink import element_boxes

        return element_boxes(payload)

    def transform(self, payload: bytes, page: CanvasTransform,
                  per_object: Sequence[CanvasTransform] | None) -> bytes:
        from .goodnotes_ink import transform_goodnotes_elements, transform_goodnotes_journal

        if not payload:
            return payload
        if per_object is None:
            return transform_goodnotes_journal(payload, page)
        return transform_goodnotes_elements(payload, list(per_object))

    def merge(self, base: bytes, others: Sequence[bytes]) -> bytes:
        from .goodnotes_ink import merge_goodnotes_journals

        return merge_goodnotes_journals(base, list(others))


SAMSUNG_NOTES = SamsungNotesInk()
NOTEWISE = NotewiseInk()
GOODNOTES = GoodnotesInk()

__all__ = ["Box", "GOODNOTES", "InkCodec", "NOTEWISE", "SAMSUNG_NOTES"]
