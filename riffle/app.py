from __future__ import annotations

import logging
import os
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

# pikepdf의 nanobind 열거형 등록은 첫 import가 두 스레드에서 겹치면 프로세스를 종료할 수 있다.
try:
    import pikepdf  # noqa: F401
except ImportError:
    pikepdf = None

from . import __version__
from .engine import ComposerSession, PdfComposerError
from .page_plan import PagePlan
from .ranges import PageRangeError, parse_page_ranges
from .handwriting_transfer import (
    SUPPORTED_SUFFIXES,
    inspect_transfer,
    output_suffix,
    preview_transfer,
    transfer_handwriting,
    with_output_suffix,
)

APP_USER_MODEL_ID = "Riffle.Desktop"
MISSING_HANDWRITING_MESSAGE = "필기 원본과 대상 PDF를 모두 선택하세요."
# 저장 대화상자에 보여줄 형식 이름. 결과는 늘 원본과 같은 형식으로 나간다.
HANDWRITING_SAVE_TYPES = {
    ".sdocx": "Samsung Notes 문서 (*.sdocx)",
    ".notewise": "Notewise 문서 (*.notewise)",
    ".goodnotes": "Goodnotes 문서 (*.goodnotes)",
}
HANDWRITING_ANALYSIS_CONCURRENCY = max(
    1, int(os.environ.get("RIFFLE_ANALYSIS_CONCURRENCY", "1"))
)
_HANDWRITING_ANALYSIS_EXECUTOR = ThreadPoolExecutor(
    max_workers=HANDWRITING_ANALYSIS_CONCURRENCY,
    thread_name_prefix="riffle-analysis",
)
_ANALYSIS_MESSAGES = {
    "waiting": "두 파일을 선택해 주세요.",
    "structure": "파일 구조 확인 중…",
    "matching": "페이지 비교·자동 매칭 중…",
    "alignment": "필기 좌표 정렬 중…",
    "preview": "미리보기 준비 중…",
    "ready": "분석이 끝났습니다.",
    "error": "분석하지 못했습니다.",
}


def _png_data_uri(payload: bytes) -> str:
    import base64

    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


def configure_windows_app_identity(app_id: str = APP_USER_MODEL_ID) -> None:
    """Python 프로세스가 아니라 독립 앱으로 작업표시줄에 그룹화되게 한다."""
    import os

    if os.name != "nt":
        return
    try:
        import ctypes

        set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        result = set_app_id(app_id)
        if result != 0:
            logging.getLogger("riffle").warning(
                "Failed to set AppUserModelID: HRESULT=%s", result
            )
    except Exception:
        logging.getLogger("riffle").exception(
            "Failed to configure Windows app identity"
        )


class ComposerApi:
    """Small JSON-friendly bridge exposed to the embedded web UI."""

    def __init__(self, session: ComposerSession | None = None) -> None:
        # pywebview exposes every public attribute on js_api. Keep native and
        # stateful Python objects private or its serializer walks the complete
        # WinForms/WebView2 object graph and eventually recurses forever.
        self._session = session or ComposerSession()
        self._window: Any | None = None
        self._closed = False
        self._handwriting_source: Path | None = None
        self._handwriting_target: Path | None = None
        self._handwriting_cache: tuple | None = None
        self._handwriting_lock = threading.RLock()
        self._handwriting_generation = 0
        self._handwriting_future: Future | None = None
        self._handwriting_analysis = {
            "state": "waiting",
            "stage": "waiting",
            "message": _ANALYSIS_MESSAGES["waiting"],
            "error": None,
        }

    def _bind_window(self, window: Any) -> None:
        self._window = window

    @staticmethod
    def _ok(**payload: Any) -> dict:
        return {"ok": True, **payload}

    @staticmethod
    def _error(exc: Exception) -> dict:
        logging.getLogger("riffle").error(
            "Desktop API request failed: %s", exc, exc_info=exc
        )
        return {"ok": False, "error": str(exc)}

    def health(self) -> dict:
        return self._ok(version=__version__)

    def log_client_error(self, message: str) -> dict:
        logging.getLogger("riffle").error("UI error: %s", message)
        return self._ok()

    def toggle_fullscreen(self) -> dict:
        try:
            if self._window is None:
                raise PdfComposerError("앱 창이 아직 준비되지 않았습니다.")
            self._window.toggle_fullscreen()
            return self._ok()
        except Exception as exc:
            return self._error(exc)

    def choose_pdfs(self) -> dict:
        try:
            if self._window is None:
                raise PdfComposerError("앱 창이 아직 준비되지 않았습니다.")
            import webview

            paths = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=("PDF 문서 (*.pdf)",),
            )
            return self.add_paths(list(paths or []))
        except Exception as exc:
            return self._error(exc)

    @staticmethod
    def _dialog_path(value: Any) -> Path | None:
        if not value:
            return None
        if isinstance(value, str):
            return Path(value).expanduser().resolve()
        return Path(value[0]).expanduser().resolve() if value else None

    def _inspection(self):
        """본문 정렬 추정은 문서 전체를 훑으므로 파일이 그대로면 결과를 다시 쓴다."""
        with self._handwriting_lock:
            source = self._handwriting_source
            target = self._handwriting_target
            if not source or not target:
                raise PdfComposerError(MISSING_HANDWRITING_MESSAGE)
            key = self._handwriting_key(source, target)
            cached = self._handwriting_cache
            if cached and cached[0] == key:
                return cached[1]
            analysis = dict(self._handwriting_analysis)
            future = self._handwriting_future
        if future is not None and not future.done():
            raise PdfComposerError("필기 문서를 분석하는 중입니다. 잠시 후 다시 시도하세요.")
        if analysis["state"] == "error":
            raise PdfComposerError(analysis["error"] or _ANALYSIS_MESSAGES["error"])

        # 테스트나 데스크톱 내부 호출처럼 선택 도우미를 거치지 않은 경우만 동기로 계산한다.
        # 정상 UI 경로는 _start_handwriting_analysis가 백그라운드에서 이 캐시를 채운다.
        inspection = inspect_transfer(source, target)
        with self._handwriting_lock:
            if source == self._handwriting_source and target == self._handwriting_target:
                self._handwriting_cache = (key, inspection)
        return inspection

    @staticmethod
    def _handwriting_key(source: Path, target: Path) -> tuple:
        return (
            str(source),
            str(target),
            source.stat().st_mtime_ns,
            target.stat().st_mtime_ns,
        )

    def _set_analysis_stage(self, generation: int, stage: str) -> None:
        with self._handwriting_lock:
            if generation != self._handwriting_generation:
                return
            self._handwriting_analysis = {
                "state": "running",
                "stage": stage,
                "message": _ANALYSIS_MESSAGES[stage],
                "error": None,
            }

    def _run_handwriting_analysis(
        self, generation: int, source: Path, target: Path, inspector
    ) -> None:
        try:
            inspection = inspector(
                source,
                target,
                progress=lambda stage: self._set_analysis_stage(generation, stage),
            )
            key = self._handwriting_key(source, target)
        except Exception as exc:
            with self._handwriting_lock:
                if generation != self._handwriting_generation:
                    return
                self._handwriting_cache = None
                self._handwriting_analysis = {
                    "state": "error",
                    "stage": "error",
                    "message": _ANALYSIS_MESSAGES["error"],
                    "error": str(exc),
                }
            return
        with self._handwriting_lock:
            if generation != self._handwriting_generation:
                return
            self._handwriting_cache = (key, inspection)
            self._handwriting_analysis = {
                "state": "ready",
                "stage": "ready",
                "message": _ANALYSIS_MESSAGES["ready"],
                "error": None,
            }

    def _start_handwriting_analysis(self) -> None:
        with self._handwriting_lock:
            self._handwriting_generation += 1
            generation = self._handwriting_generation
            previous = self._handwriting_future
            self._handwriting_future = None
            self._handwriting_cache = None
            source = self._handwriting_source
            target = self._handwriting_target
            if previous is not None:
                previous.cancel()
            if not source or not target:
                self._handwriting_analysis = {
                    "state": "waiting",
                    "stage": "waiting",
                    "message": _ANALYSIS_MESSAGES["waiting"],
                    "error": None,
                }
                return
            self._handwriting_analysis = {
                "state": "running",
                "stage": "structure",
                "message": _ANALYSIS_MESSAGES["structure"],
                "error": None,
            }
            self._handwriting_future = _HANDWRITING_ANALYSIS_EXECUTOR.submit(
                self._run_handwriting_analysis, generation, source, target, inspect_transfer
            )

    def _set_handwriting_path(self, kind: str, path: Path) -> Path | None:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise PdfComposerError(f"파일을 찾을 수 없습니다: {path.name}")
        if kind == "source":
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                raise PdfComposerError(".sdocx · .notewise · .goodnotes 파일을 선택하세요.")
            attribute = "_handwriting_source"
        elif kind == "target":
            if path.suffix.lower() != ".pdf":
                raise PdfComposerError(".pdf 파일을 선택하세요.")
            attribute = "_handwriting_target"
        else:
            raise PdfComposerError("알 수 없는 필기 파일 종류입니다.")
        with self._handwriting_lock:
            previous = getattr(self, attribute)
            setattr(self, attribute, path)
        self._start_handwriting_analysis()
        return previous

    def _handwriting_status(self) -> dict:
        with self._handwriting_lock:
            source = self._handwriting_source
            target = self._handwriting_target
            analysis = dict(self._handwriting_analysis)
            cached = self._handwriting_cache
        inspection = cached[1].as_dict() if cached and analysis["state"] == "ready" else None
        return {
            "source_name": source.name if source else None,
            "source_format": source.suffix.lower().lstrip(".") if source else None,
            "target_name": target.name if target else None,
            "ready": inspection is not None,
            "inspection": inspection,
            "analysis": analysis,
        }

    def handwriting_status(self) -> dict:
        return self._ok(**self._handwriting_status())

    def set_handwriting_source_path(self, path: str) -> dict:
        return self._select_handwriting_path("source", path)

    def set_handwriting_target_path(self, path: str) -> dict:
        return self._select_handwriting_path("target", path)

    def _select_handwriting_path(self, kind: str, path: str) -> dict:
        try:
            self._set_handwriting_path(kind, Path(path))
            return self._ok(cancelled=False, **self._handwriting_status())
        except Exception as exc:
            return self._error(exc)

    def retry_handwriting_analysis(self) -> dict:
        try:
            if not self._handwriting_source or not self._handwriting_target:
                raise PdfComposerError(MISSING_HANDWRITING_MESSAGE)
            self._start_handwriting_analysis()
            return self._ok(**self._handwriting_status())
        except Exception as exc:
            return self._error(exc)

    def handwriting_preview(self, page_index: int = 0, source_index: int = -2, native_page_id: str = "") -> dict:
        try:
            inspection = self._inspection()
            index = -1 if int(page_index) == -1 else max(0, min(int(page_index), inspection.page_count - 1))
            if native_page_id:
                from .sdocx_transfer import preview_native_page

                before, after, ink, stroke_count = preview_native_page(
                    self._handwriting_source, str(native_page_id)
                )
            else:
                before, after, ink, stroke_count = preview_transfer(
                    self._handwriting_source,
                    self._handwriting_target,
                    index,
                    inspection,
                    source_index_override=int(source_index),
                )
            return self._ok(
                index=index,
                page_count=inspection.page_count,
                before=_png_data_uri(before),
                after=_png_data_uri(after),
                ink=_png_data_uri(ink),
                stroke_count=stroke_count,
            )
        except Exception as exc:
            return self._error(exc)

    def choose_files(self) -> dict:
        """새 화면의 `파일 고르기`. 필기 파일과 PDF를 한 창에서 여러 개 고른다 — 무엇을 할지는 화면이 정한다."""
        try:
            if self._window is None:
                raise PdfComposerError("앱 창이 아직 준비되지 않았습니다.")
            import webview

            selected = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=(
                    "필기 파일과 PDF (*.sdocx;*.notewise;*.goodnotes;*.pdf)",
                    "모든 파일 (*.*)",
                ),
            )
            files = [Path(item) for item in (selected or ())]
            return self._ok(files=[{"name": path.name, "path": str(path)} for path in files])
        except Exception as exc:
            return self._error(exc)

    def choose_handwriting_source(self) -> dict:
        try:
            if self._window is None:
                raise PdfComposerError("앱 창이 아직 준비되지 않았습니다.")
            import webview

            selected = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=("필기 문서 (*.sdocx;*.notewise;*.goodnotes)",),
            )
            path = self._dialog_path(selected)
            if path is None:
                return self._ok(cancelled=True, **self._handwriting_status())
            self._set_handwriting_path("source", path)
            return self._ok(cancelled=False, **self._handwriting_status())
        except Exception as exc:
            return self._error(exc)

    def choose_handwriting_target(self) -> dict:
        try:
            if self._window is None:
                raise PdfComposerError("앱 창이 아직 준비되지 않았습니다.")
            import webview

            selected = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=("PDF 문서 (*.pdf)",),
            )
            path = self._dialog_path(selected)
            if path is None:
                return self._ok(cancelled=True, **self._handwriting_status())
            self._set_handwriting_path("target", path)
            return self._ok(cancelled=False, **self._handwriting_status())
        except Exception as exc:
            return self._error(exc)

    def reset_handwriting_transfer(self) -> dict:
        with self._handwriting_lock:
            self._handwriting_source = None
            self._handwriting_target = None
        self._start_handwriting_analysis()
        return self._ok(**self._handwriting_status())

    def save_handwriting_transfer(
        self,
        suggested_name: str = "필기-이전.sdocx",
        page_plan: list[dict] | list[int | None] | None = None,
        allow_unconfirmed: bool = False,
    ) -> dict:
        try:
            if self._window is None:
                raise PdfComposerError("앱 창이 아직 준비되지 않았습니다.")
            inspection = self._inspection()
            import webview

            safe_name = re.sub(r'[<>:"/\\|?*]+', "_", suggested_name).strip(" .")
            suffix = output_suffix(self._handwriting_source)
            selected = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=with_output_suffix(safe_name, self._handwriting_source)
                if safe_name else f"필기-이전{suffix}",
                file_types=(HANDWRITING_SAVE_TYPES.get(suffix, HANDWRITING_SAVE_TYPES[".sdocx"]),),
            )
            output = self._dialog_path(selected)
            if output is None:
                return self._ok(cancelled=True, inspection=inspection.as_dict())
            return self.transfer_handwriting_to_path(
                str(output), page_plan, allow_unconfirmed
            )
        except Exception as exc:
            return self._error(exc)

    def transfer_handwriting_to_path(
        self,
        output_path: str,
        page_plan: list[dict] | list[int | None] | None = None,
        allow_unconfirmed: bool = False,
    ) -> dict:
        try:
            inspection = self._inspection()
            output = Path(output_path).expanduser().resolve()
            alignment = getattr(inspection, "alignment", None)
            if (alignment is not None and alignment.requires_confirmation
                    and not allow_unconfirmed
                    and not (page_plan is not None and all(isinstance(item, dict) for item in page_plan))):
                raise PdfComposerError("자동 정렬 품질이 낮습니다. 쪽 대응을 확인한 뒤 저장하세요.")
            if page_plan is not None and all(isinstance(item, dict) for item in page_plan):
                plan = PagePlan.from_payload(
                    inspection.source_page_count,
                    inspection.page_count,
                    page_plan,
                    inspection.match,
                )
                if plan.unconfirmed and not allow_unconfirmed:
                    raise PdfComposerError(
                        f"확인하지 않은 쪽 대응이 {len(plan.unconfirmed)}개 남아 있습니다."
                    )
                result = transfer_handwriting(
                    self._handwriting_source,
                    self._handwriting_target,
                    output,
                    plan_override=plan,
                )
                if plan.unconfirmed:
                    result.setdefault("warnings", []).append(
                        f"확인하지 않은 쪽 대응 {len(plan.unconfirmed)}개를 사용자 승인으로 저장했습니다: "
                        + ", ".join(plan.unconfirmed_labels)
                    )
            elif page_plan is not None and getattr(inspection, "mode", None) == "rebuild":
                from .page_match import match_from_target_mapping

                match = match_from_target_mapping(
                    inspection.source_page_count,
                    page_plan,
                    inspection.match,
                )
                result = transfer_handwriting(
                    self._handwriting_source,
                    self._handwriting_target,
                    output,
                    match_override=match,
                )
            else:
                result = transfer_handwriting(
                    self._handwriting_source, self._handwriting_target, output
                )
            return self._ok(cancelled=False, result=result)
        except Exception as exc:
            return self._error(exc)

    def add_paths(self, paths: list[str] | str | Path) -> dict:
        try:
            if isinstance(paths, (str, Path)):
                paths = [paths]
            resolved = [Path(path).expanduser().resolve() for path in paths]
            added = self._session.add_files(resolved)
            return self._ok(
                added=added,
                sources=[source.as_dict() for source in self._session.sources],
            )
        except Exception as exc:
            return self._error(exc)

    def reset_documents(self) -> dict:
        """문서 합치기 쪽만 비운다.

        도구별로 따로 비울 수 있어야 한다. 한쪽을 정리하려다 다른 쪽에서 고르던 파일까지
        사라지면, 사용자는 하지도 않은 일을 당한다. 그래서 필기 옮기기 상태는 건드리지 않는다.
        """
        try:
            cleared = self._session.clear_sources()
            return self._ok(sources=[], cleared=[str(path) for path in cleared])
        except Exception as exc:
            return self._error(exc)

    def remove_document(self, document_id: str) -> dict:
        try:
            self._session.remove_source(document_id)
            return self._ok()
        except Exception as exc:
            return self._error(exc)

    def page_image(self, document_id: str, page_index: int, kind: str) -> dict:
        try:
            image = self._session.page_image(document_id, int(page_index), kind)
            return self._ok(image=image)
        except Exception as exc:
            return self._error(exc)

    def parse_range(self, text: str, page_count: int) -> dict:
        try:
            indices = parse_page_ranges(text, int(page_count))
            return self._ok(indices=indices)
        except (PageRangeError, ValueError) as exc:
            return self._error(exc)

    def save_result(self, order: list[dict], suggested_name: str = "조합된 문서.pdf") -> dict:
        try:
            if self._window is None:
                raise PdfComposerError("앱 창이 아직 준비되지 않았습니다.")
            import webview

            safe_name = re.sub(r'[<>:"/\\|?*]+', "_", suggested_name).strip(" .")
            if not safe_name.lower().endswith(".pdf"):
                safe_name += ".pdf"
            paths = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=safe_name or "조합된 문서.pdf",
                file_types=("PDF 문서 (*.pdf)",),
            )
            if not paths:
                return self._ok(cancelled=True)
            output_path = paths if isinstance(paths, str) else paths[0]
            result = self._session.build_pdf(order, output_path)
            return self._ok(cancelled=False, result=result)
        except Exception as exc:
            return self._error(exc)

    def build_result_to_path(self, order: list[dict], output_path: str) -> dict:
        try:
            result = self._session.build_pdf(order, output_path)
            return self._ok(cancelled=False, result=result)
        except Exception as exc:
            return self._error(exc)

    def _close(self, wait_for_analysis: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        with self._handwriting_lock:
            self._handwriting_generation += 1
            future = self._handwriting_future
            if future is not None:
                future.cancel()
        if wait_for_analysis and future is not None and not future.cancelled():
            # The session folder is removed next; let the worker release its copies first.
            future.result()
        self._session.close()


NEW_UI_ENTRY = Path(__file__).with_name("ui") / "index.html"
OLD_UI_ENTRY = Path(__file__).with_name("static") / "index.html"


def _dropped_files(event: dict) -> list[dict]:
    """창에 놓은 파일의 이름과 전체 경로. 브라우저는 경로를 숨기고 pywebview 만 알려 준다."""
    files = (event.get("dataTransfer") or {}).get("files") or []
    return [
        {"name": item.get("name") or Path(item["pywebviewFullPath"]).name,
         "path": item["pywebviewFullPath"]}
        for item in files if item.get("pywebviewFullPath")
    ]


def _bind_file_drop(window: Any) -> None:
    """창에 놓은 파일의 경로를 새 화면으로 밀어 준다(`window.__riffleDropped`)."""
    import json

    from webview.dom import DOMEventHandler

    def on_drop(event: dict) -> None:
        files = _dropped_files(event)
        if files:
            window.evaluate_js(
                f"window.__riffleDropped && window.__riffleDropped({json.dumps(files, ensure_ascii=False)})"
            )

    window.dom.document.events.drop += DOMEventHandler(on_drop, prevent_default=True, stop_propagation=True)


def run(debug: bool = False, new_ui: bool = False) -> None:
    configure_windows_app_identity()
    import webview

    api = ComposerApi()
    # 새 화면(명세 2026-09-24-01)은 옛 화면을 지우기 전까지 `--new-ui` 로만 연다.
    static_file = NEW_UI_ENTRY if new_ui else OLD_UI_ENTRY
    window = webview.create_window(
        "Riffle",
        str(static_file.resolve()) + "#desktop",
        js_api=api,
        width=1440,
        height=900,
        min_size=(1080, 680),
        maximized=True,
        background_color="#0b1020",
        text_select=True,
    )
    api._bind_window(window)
    window.events.closed += api._close
    if new_ui:
        window.events.loaded += lambda: _bind_file_drop(window)
    icon = Path(__file__).parents[1] / "assets" / "icon.ico"
    webview.start(
        debug=debug,
        http_server=True,
        private_mode=True,
        gui="edgechromium",
        icon=str(icon) if icon.exists() else None,
    )


def configure_logging() -> Path:
    import os

    local_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    log_dir = local_data / "Riffle"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
        force=True,
    )
    logging.getLogger("riffle").info("Application starting (version %s)", __version__)
    return log_path
