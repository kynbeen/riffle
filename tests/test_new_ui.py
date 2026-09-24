"""새 화면(명세 2026-09-24-01 작업 단위 3) — 빌드가 소스와 맞는지, 파일 규칙, 두 실행 환경의 입구, 글자 대비."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from riffle.app import ComposerApi, NEW_UI_ENTRY, _dropped_files
from tests.test_app import FakeWindow

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
UI = ROOT / "riffle" / "ui"
SOURCES = ["src", "public", "index.html", "package.json", "vite.config.ts", "tsconfig.json"]


def source_hash() -> str:
    """web/vite.config.ts 의 sourceHash 와 같은 방식 — 파일 이름과 CRLF 만 LF 로 바꾼 바이트를 이름 순으로."""
    files = []
    for entry in SOURCES:
        path = WEB / entry
        items = [p for p in path.rglob("*") if p.is_file()] if path.is_dir() else [path]
        files += [p.relative_to(WEB).as_posix() for p in items]
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update((name + "\n").encode("utf-8"))
        digest.update((WEB / name).read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class NewUiBuildTests(unittest.TestCase):
    def test_committed_build_was_made_from_the_current_source(self):
        """소스를 고치고 `npm run build` 를 잊으면 앱은 옛 화면을 연다. 그런 커밋을 여기서 막는다."""
        self.assertTrue(NEW_UI_ENTRY.is_file(), "riffle/ui 가 없습니다 — web 에서 npm run build")
        recorded = (UI / "source-hash.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(recorded, source_hash(), "web 소스가 빌드보다 새롭습니다 — web 에서 npm run build")

    def test_build_uses_relative_paths_for_both_the_window_and_the_web(self):
        html = NEW_UI_ENTRY.read_text(encoding="utf-8")
        self.assertIn('src="./assets/', html)
        self.assertNotIn('src="/assets/', html)

    @unittest.skipUnless(shutil.which("node"), "Node 가 있어야 화면 규칙을 돌린다")
    def test_screen_rules_pass(self):
        """파일 규칙(classify)·확인할 쪽 문장(reasons) 등 화면 안의 순수 함수 시험."""
        tests = sorted(str(path.relative_to(WEB)) for path in (WEB / "src").glob("*.test.ts"))
        self.assertIn("src\\classify.test.ts" if sys.platform == "win32" else "src/classify.test.ts", tests)
        result = subprocess.run(["node", "--test", *tests], cwd=WEB,
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("fail 0", result.stdout)

    def test_text_colors_have_enough_contrast_in_both_themes(self):
        css = (WEB / "src" / "styles.css").read_text(encoding="utf-8")
        light = css.split("@media (prefers-color-scheme: dark)", 1)[0]
        dark = css.split("@media (prefers-color-scheme: dark)", 1)[1]
        for label, block in (("light", light), ("dark", dark)):
            tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))
            for text in ("text", "text-2", "danger", "accent"):
                for ground in ("bg", "bg-raised", "bg-hover"):
                    with self.subTest(theme=label, text=text, ground=ground):
                        self.assertGreaterEqual(contrast(tokens[text], tokens[ground]), 4.5)
            with self.subTest(theme=label, text="accent-text"):
                self.assertGreaterEqual(contrast(tokens["accent-text"], tokens["accent"]), 4.5)


class NewUiEntranceTests(unittest.TestCase):
    def test_web_serves_the_new_screen_under_new(self):
        from fastapi.testclient import TestClient

        from riffle.web import app

        with TestClient(app) as client:
            page = client.get("/new/")
            self.assertEqual(page.status_code, 200)
            self.assertIn('<div id="root">', page.text)
            asset = re.search(r'src="\./(assets/[^"]+\.js)"', page.text).group(1)
            self.assertEqual(client.get(f"/new/{asset}").status_code, 200)
            self.assertIn("Riffle", client.get("/").text)      # 옛 화면은 그대로

    def test_desktop_picker_returns_every_chosen_file_with_its_path(self):
        api = ComposerApi()
        self.addCleanup(api._close, True)
        window = FakeWindow([("C:\\a\\옛 필기.sdocx", "C:\\a\\새.pdf")])
        api._bind_window(window)
        webview = SimpleNamespace(FileDialog=SimpleNamespace(OPEN="open"))
        with patch.dict(sys.modules, {"webview": webview}):
            reply = api.choose_files()
        self.assertTrue(reply["ok"], reply)
        self.assertEqual([item["name"] for item in reply["files"]], ["옛 필기.sdocx", "새.pdf"])
        self.assertTrue(window.dialog_calls[0]["allow_multiple"])

    def test_dropped_files_carry_the_full_path_pywebview_found(self):
        event = {"dataTransfer": {"files": [
            {"name": "a.pdf", "pywebviewFullPath": "C:\\x\\a.pdf"},
            {"name": "mystery"},                                   # 경로가 없는 것은 넘기지 않는다
        ]}}
        self.assertEqual(_dropped_files(event), [{"name": "a.pdf", "path": "C:\\x\\a.pdf"}])


if __name__ == "__main__":
    unittest.main()
