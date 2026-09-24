"""화면(명세 2026-09-24-01) — 빌드가 소스와 맞는지, 화면 규칙, 두 실행 환경의 입구, 문구, 글자 대비, 웹 앱 설치."""
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

from riffle.app import ComposerApi, UI_ENTRY, _dropped_files
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


def screen_texts() -> list[tuple[str, str]]:
    """화면 소스에서 사람이 보는 한국어 문장(문자열·JSX 글)만 뽑는다. 주석은 뺀다."""
    found = []
    for path in sorted((WEB / "src").glob("*.ts*")):
        if path.name.endswith(".test.ts"):
            continue
        code = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        code = re.sub(r"(^|\s)//[^\n]*", r"\1", code)
        code = re.sub(r"\$\{[^}]*\}", "", code)          # 글 속 ${…} 는 코드다
        for text in re.findall(r"'([^'\n]*)'|\"([^\"\n]*)\"|`([^`]*)`|>([^<>{}\n]+)<", code):
            value = next(part for part in text if part) if any(text) else ""
            if re.search(r"[가-힣]", value):
                found.append((path.name, value))
    return found


class ScreenBuildTests(unittest.TestCase):
    def test_committed_build_was_made_from_the_current_source(self):
        """소스를 고치고 `npm run build` 를 잊으면 앱은 옛 화면을 연다. 그런 커밋을 여기서 막는다."""
        self.assertTrue(UI_ENTRY.is_file(), "riffle/ui 가 없습니다 — web 에서 npm run build")
        recorded = (UI / "source-hash.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(recorded, source_hash(), "web 소스가 빌드보다 새롭습니다 — web 에서 npm run build")

    def test_build_uses_relative_paths_for_both_the_window_and_the_web(self):
        html = UI_ENTRY.read_text(encoding="utf-8")
        self.assertIn('src="./assets/', html)
        self.assertNotIn('src="/assets/', html)

    @unittest.skipUnless(shutil.which("node"), "Node 가 있어야 화면 규칙을 돌린다")
    def test_screen_rules_pass(self):
        """파일 규칙·확인할 쪽 문장·짝 바꾸기·합치기 순서 — 화면 안의 순수 함수 시험."""
        tests = sorted(path.relative_to(WEB).as_posix() for path in (WEB / "src").glob("*.test.ts"))
        self.assertGreaterEqual(len(tests), 4)
        result = subprocess.run(["node", "--test", *tests], cwd=WEB,
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("fail 0", result.stdout)

    def test_text_colors_have_enough_contrast_in_both_themes(self):
        css = (WEB / "src" / "styles.css").read_text(encoding="utf-8")
        light, dark = css.split("@media (prefers-color-scheme: dark)", 1)
        for label, block in (("light", light), ("dark", dark)):
            tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))
            for text in ("text", "text-2", "danger", "accent"):
                for ground in ("bg", "bg-raised", "bg-hover"):
                    with self.subTest(theme=label, text=text, ground=ground):
                        self.assertGreaterEqual(contrast(tokens[text], tokens[ground]), 4.5)
            with self.subTest(theme=label, text="accent-text"):
                self.assertGreaterEqual(contrast(tokens["accent-text"], tokens["accent"]), 4.5)


class ScreenWordsTests(unittest.TestCase):
    """성공 기준 「화면에 코드 이름과 해석할 숫자가 없다」·「이름을 하나로」(원칙 1·8)."""

    FORBIDDEN = ["원본", "대상", "구판", "기존", "매칭", "대응", "배율", "슬롯", "mm", "margin", "distance",
                 "slot", "sdocx"]

    def test_screen_sentences_use_the_users_words(self):
        sentences = screen_texts()
        self.assertGreater(len(sentences), 30)          # 검사가 실제로 문장을 읽고 있다
        for name, sentence in sentences:
            for word in self.FORBIDDEN:
                with self.subTest(file=name, word=word):
                    self.assertNotIn(word, sentence.lower())


class ScreenEntranceTests(unittest.TestCase):
    def test_web_serves_the_screen_and_its_install_files(self):
        from fastapi.testclient import TestClient

        from riffle.web import app

        with TestClient(app) as client:
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn('<div id="root">', page.text)
            self.assertIn("<title>Riffle</title>", page.text)
            asset = re.search(r'src="\./(assets/[^"]+\.js)"', page.text).group(1)
            self.assertEqual(client.get(f"/{asset}").status_code, 200)
            manifest = client.get("/manifest.webmanifest").json()
            self.assertEqual(manifest["display"], "standalone")
            for icon in manifest["icons"]:
                self.assertEqual(client.get(icon["src"]).status_code, 200, icon["src"])
            self.assertEqual(client.get("/sw.js").status_code, 200)

    def test_service_worker_never_keeps_documents_or_per_user_responses(self):
        worker = (WEB / "public" / "sw.js").read_text(encoding="utf-8")
        self.assertIn('url.pathname.startsWith("/api/")', worker)
        self.assertIn('includes("no-store")', worker)
        self.assertNotIn('cache.addAll(["/"', worker)          # 작업공간 쿠키가 실린 첫 화면은 미리 저장하지 않는다

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


class RemovedPartsStayRemovedTests(unittest.TestCase):
    """걷어낸 것이 다시 자라지 않게(명세 2026-09-24-01 작업 단위 1·2·6)."""

    def test_old_screen_sleek_handoff_and_android_are_gone(self):
        package = ROOT / "riffle"
        self.assertFalse((package / "static").exists())
        self.assertFalse((package / "merge_handoff.py").exists())
        self.assertFalse((package / "exam_range.py").exists())
        self.assertFalse((package / "_android_pdf.py").exists())
        self.assertFalse((ROOT / "android").exists())
        app = (package / "app.py").read_text(encoding="utf-8")
        main = (package / "__main__.py").read_text(encoding="utf-8")
        for word in ("startup_plan", "finish_review", "close_window", "dispatch_call", "toggle_fullscreen"):
            with self.subTest(word=word):
                self.assertNotIn(word, app)
        self.assertNotIn("--open-plan", main)
        screen = "".join(path.read_text(encoding="utf-8") for path in (WEB / "src").glob("*.ts*"))
        self.assertNotIn("AndroidBridge", screen)


if __name__ == "__main__":
    unittest.main()
