# Riffle 새 화면

React + Vite + TypeScript 로 짓는 새 화면이다(명세 [`2026-09-24-01`](../docs/specs/2026-09-24-01-새-화면.md)).
빌드 결과는 `riffle/ui/` 에 두고 **저장소에 커밋한다** — 앱을 쓰는 PC 에는 Node 가 없다.

```powershell
cd web
npm install          # 처음 한 번
npm test             # 파일 규칙(놓은 파일로 할 일 정하기) 시험
npm run build        # 타입 검사 후 riffle/ui 로 빌드. 소스를 고쳤으면 커밋 전에 꼭 돌린다
npm run dev          # 개발 서버. /api 는 켜 둔 웹 서버(python -m riffle.web, 8000)로 넘긴다
```

소스를 고치고 빌드를 잊으면 `tests/test_new_ui.py` 가 실패한다(빌드에 소스 해시를 새겨 대조한다).

옛 화면을 지우기 전까지 새 화면은 따로 연다.

- 데스크톱: `python -m riffle --new-ui`
- 웹: 주소 끝에 `/new/` (예: `http://localhost:8000/new/`)

서버와 말하는 곳은 `src/api.ts` 하나다. 데스크톱 창(pywebview)과 웹(HTTP)의 차이는 여기서만 갈린다.
데스크톱 창에 놓은 파일의 경로는 브라우저가 알려 주지 않아 Python(`riffle/app.py` 의 `_bind_file_drop`)이
`window.__riffleDropped` 로 밀어 준다.
