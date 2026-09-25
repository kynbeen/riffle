from __future__ import annotations

import argparse
import traceback

from .app import configure_logging, run


def main() -> None:
    parser = argparse.ArgumentParser(description="Riffle 데스크톱 앱을 실행합니다.")
    parser.add_argument("--debug", action="store_true", help="개발자 도구와 디버그 로그를 켭니다.")
    parser.add_argument("files", nargs="*", help="열 파일 — 창에 놓은 것과 같게 처리합니다(필기 파일과 새 PDF, 또는 PDF 여러 개).")
    args = parser.parse_args()
    log_path = configure_logging()
    try:
        run(debug=args.debug, files=args.files)
    except Exception as exc:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(traceback.format_exc())
        try:
            from tkinter import messagebox

            messagebox.showerror(
                "Riffle",
                "앱을 시작하지 못했습니다. 서버를 따로 실행할 필요는 없습니다.\n\n"
                f"오류: {exc}\n\n진단 기록: {log_path}",
            )
        except Exception:
            pass
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
