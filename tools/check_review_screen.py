"""필기 옮기기 검토 화면을 실제 파일로 끝까지 눌러 보는 브라우저 확인(명세 2026-09-25-01 단위 1).

사람 파일이 필요해 자동 테스트에는 넣지 않는다. 화면을 고친 뒤 직접 돌린다.

    python tools/check_review_screen.py <옛 필기> <새 PDF>

웹 서버를 빈 포트에 띄우고 Edge 를 창 크기 둘(1440×1000 라이트, 390×844 다크)로 연다. 확인하는 것:

- 카드가 있으면 봐야 할 쪽에서 시작하고, 모든 쪽 격자의 쪽 수·걸러 보기 숫자가 탭 숫자와 같다(첫 쪽 그림까지 걸린 시간도 찍는다)
- 누른 카드는 한 줄로 접힌다
- 저장 막대가 스크롤과 상관없이 화면 안에 보인다
- 저장 뒤 카드를 바꾸면 요약 숫자는 저장한 그대로이고, 저장 막대가 돌아온다
- 이 화면에 파일을 놓아도 브라우저가 받아 가지 않는다(작업이 남는다)
- 정한 것이 있고 저장 전이면 ← 가 한 번 묻는다. 저장한 뒤에는 묻지 않는다

카드가 둘 이상 나오는 파일 쌍이어야 한다(예: 병리학 2주차(1) 박민웅 옛 필기 → 2주차(1) Sleek 필기본 — 카드 4장.
1주차(3) 은 2026-09-25 부터 순서 바뀐 쪽을 자동으로 짝지어 카드가 없다).
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
failures: list[str] = []


def check(condition: bool, what: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + what)
    if not condition:
        failures.append(what)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def footer_in_view(page: Page) -> bool:
    return page.evaluate("""() => {
        const box = document.querySelector('.footer').getBoundingClientRect()
        return box.top >= 0 && box.bottom <= window.innerHeight + 1
    }""")


def run(page: Page, url: str, source: Path, target: Path) -> None:
    page.goto(url)
    page.set_input_files("input[type=file]", [str(source), str(target)])
    page.wait_for_selector(".headline", timeout=300_000)
    cards = page.locator(".card")
    check(cards.count() >= 2, f"카드가 둘 이상 나온다 ({cards.count()}장)")

    check(page.get_by_role("tab", name=re.compile("^봐야 할 쪽")).get_attribute("aria-selected") == "true",
          "카드가 있으면 봐야 할 쪽에서 시작한다")

    # 모든 쪽 — 결과 순서 격자. 쪽 수가 탭의 숫자와 같고, 걸러 보기의 '전체' 와 같다.
    all_tab = page.get_by_role("tab", name=re.compile("^모든 쪽"))
    total = int(all_tab.inner_text().split()[-1])
    started = time.perf_counter()
    all_tab.click()
    page.wait_for_selector(".page-tile img", timeout=60_000)
    print(f"       첫 쪽 그림까지 {time.perf_counter() - started:.2f}초")
    check(page.locator(".page-tile").count() == total, f"격자 쪽 수가 모든 쪽 숫자와 같다 ({total})")
    check(page.locator(".chip-button").first.inner_text() == f"전체 {total}", "걸러 보기 '전체' 가 모든 쪽 숫자와 같다")
    watch = page.locator(".chip-button", has_text="볼 쪽")
    watch.click()
    check(page.locator(".page-tile").count() == int(watch.inner_text().split()[-1]), "볼 쪽만 거르면 그 숫자만큼 남는다")
    page.get_by_role("tab", name=re.compile("^봐야 할 쪽")).click()

    page.evaluate("document.querySelector('.stage').scrollTop = 0")
    check(footer_in_view(page), "맨 위에서도 저장 막대가 보인다")

    # 파일을 놓아도 브라우저가 받아 가지 않는다 — drop 의 기본 동작(파일 열기)이 막혀야 한다.
    prevented = page.evaluate("""() => {
        const data = new DataTransfer()
        data.items.add(new File(['x'], 'x.pdf', { type: 'application/pdf' }))
        const over = new DragEvent('dragover', { dataTransfer: data, cancelable: true, bubbles: true })
        const drop = new DragEvent('drop', { dataTransfer: data, cancelable: true, bubbles: true })
        return [!document.body.dispatchEvent(over), !document.body.dispatchEvent(drop)]
    }""")
    check(prevented == [True, True], "놓은 파일의 기본 동작(브라우저가 파일 열기)을 막는다")
    check(page.get_by_text("지금은 필기를 옮기는 중입니다").count() == 1, "놓은 파일을 받지 않는다고 알린다")

    first = cards.first
    first.locator(".actions .button:not(.quiet)").click()
    check(page.locator(".card-row").count() == 1, "누른 카드가 한 줄로 접힌다")

    # 정한 것이 있고 저장 전 → ← 가 묻는다. 돌아가기를 누르면 그대로다.
    page.locator("header .back").click()
    check(page.get_by_role("dialog").count() == 1, "저장 전 ← 는 한 번 묻는다")
    page.get_by_role("dialog").get_by_role("button", name="돌아가기").click()
    check(page.locator(".card-row").count() == 1, "돌아가기를 누르면 정한 것이 그대로다")

    # 누르면 카드가 한 줄로 접혀 순번이 당겨지므로, 남은 카드의 맨 앞을 누르기를 되풀이한다.
    while page.locator(".card").count():
        page.locator(".card").first.locator(".actions .button:not(.quiet)").click()
    page.evaluate("document.querySelector('.stage').scrollTop = 1e6")
    page.get_by_role("button", name="새 파일로 저장").click()
    page.wait_for_selector(".saved", timeout=120_000)
    before = page.locator(".saved .t-caption").first.inner_text()

    row = page.locator(".card-row").last
    row.get_by_role("button", name="되돌리기").click()
    page.locator(".card").last.get_by_role("button", name="빼기").click()
    check(page.locator(".saved").count() == 0, "저장 뒤 바꾸면 저장 완료 요약을 내린다")
    check(page.get_by_role("button", name="새 파일로 저장").count() == 1, "저장 뒤 바꾸면 저장 단추가 돌아온다")
    check(page.get_by_text("저장한 뒤 바꾼 것이 있습니다").count() == 1, "저장 뒤 바꾼 것이 있다고 말한다")

    # 되돌리면 다시 저장한 상태 그대로 — 요약도 저장한 숫자다.
    page.locator(".card-row").last.get_by_role("button", name="다시 넣기").click()
    page.locator(".card").last.locator(".actions .button:not(.quiet)").click()
    check(page.locator(".saved").count() == 1, "저장한 상태로 되돌리면 저장 완료로 돌아온다")
    after = page.locator(".saved .t-caption").first.inner_text() if page.locator(".saved").count() else ""
    check(before == after, f"요약 숫자는 저장한 그대로다 ({before!r})")

    page.locator("header .back").click()
    check(page.get_by_role("dialog").count() == 0, "저장한 뒤의 ← 는 묻지 않는다")
    page.wait_for_selector(".drop")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "riffle.web:app", "--host", "127.0.0.1",
                               "--port", str(port), "--log-level", "warning"], cwd=ROOT)
    url = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(60):
            try:
                urlopen(url + "api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge")
            for width, height, scheme in ((1440, 1000, "light"), (390, 844, "dark")):
                print(f"{width}×{height} {scheme}")
                context = browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme,
                                              accept_downloads=True)
                page = context.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                run(page, url, source, target)
                check(not errors, f"화면 오류 없음 {errors}")
                context.close()
            browser.close()
    finally:
        server.terminate()
    print("통과" if not failures else f"실패 {len(failures)}건")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
