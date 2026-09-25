# Riffle 화면

React + Vite + TypeScript 로 짓는 화면이다(명세 [`2026-09-24-01`](../docs/specs/2026-09-24-01-새-화면.md)).
빌드 결과는 `riffle/ui/` 에 두고 **저장소에 커밋한다** — 앱을 쓰는 PC 에는 Node 가 없다.
데스크톱 창(`python -m riffle`)과 웹(`python -m riffle.web`, 주소 `/`)이 같은 빌드를 연다.

```powershell
cd web
npm install          # 처음 한 번
npm test             # 화면 안 순수 함수 시험(파일 규칙·확인할 쪽 문장·짝 바꾸기·합치기 순서)
npm run build        # 타입 검사 후 riffle/ui 로 빌드. 소스를 고쳤으면 커밋 전에 꼭 돌린다
npm run dev          # 개발 서버. /api 는 켜 둔 웹 서버(python -m riffle.web, 8000)로 넘긴다
```

필기 옮기기 검토 화면을 고쳤으면 실제 파일로 브라우저 확인을 돌린다(사람 파일이 필요해 자동 테스트 밖이다):
`python tools/check_review_screen.py <옛 필기> <새 PDF>` — 카드 접기·저장 막대·저장 뒤 정직함·파일 놓기·`←` 확인.

소스를 고치고 빌드를 잊으면 `tests/test_new_ui.py` 가 실패한다(빌드에 소스 해시를 새겨 대조한다).
같은 파일이 화면 문구에 내부 용어(`원본`·`대상`·`매칭`·`mm` 같은 것)가 섞이지 않았는지도 검사한다.

서버와 말하는 곳은 `src/api.ts` 하나다. 데스크톱 창(pywebview)과 웹(HTTP)의 차이는 여기서만 갈린다.
데스크톱 창에 놓은 파일의 경로는 브라우저가 알려 주지 않아 Python(`riffle/app.py` 의 `_bind_file_drop`)이
`window.__riffleDropped` 로 밀어 준다.

미리보기·쪽 그림 요청은 화면이 사라지면 `AbortController` 로 거둔다. `←` 는 화면을 먼저 닫고 서버를 비운다 —
거꾸로 하면 비운 뒤에 도착한 요청이 실패로 기록된다.

웹에서는 `public/sw.js`(서비스 워커 — 브라우저가 화면 파일을 보관해 두는 장치)가 화면 파일만 보관한다.
`/api/` 요청과 `no-store` 응답은 절대 보관하지 않는다(남의 문서·세션이 섞이지 않게).
