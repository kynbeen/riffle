# Riffle

Riffle은 PDF 문서 합치기와 Samsung Notes·Notewise·Goodnotes 6 필기 옮기기를 한 화면에서
제공하는 도구입니다.
Windows 데스크톱 앱과 Docker 기반 웹앱이 같은 PDF·필기 문서 처리 엔진과 같은 화면을 사용합니다.
이 PC 에서는 데스크톱 앱을, 다른 기기에서는 웹(**<https://useriffle.onrender.com>**)을 씁니다.
Android 앱은 2026-09-24 사용자 결정으로 걷었습니다(명세 `2026-09-24-01`).

Riffle 은 NotEditor 의 새 이름입니다(2026-09-24). Riffle 1.0.0 은 별개 앱으로 설치되어, 이미 설치한
NotEditor 1.2.0 을 덮지 않습니다.

> **처음 쓰시나요?** 설치부터 첫 사용까지 그대로 따라 할 수 있게 정리했습니다 →
> **[설치와 첫 사용 안내](docs/설치와-첫-사용.md)**
>
> 구현 완료 범위와 아직 남은 실기 검증은 **[현재 상태](docs/current-status.md)** 에서 확인합니다.
>
> 화면·문구·흐름을 바꿀 때 판단이 갈리면 **[UX 철학](docs/UX-철학.md)** 이 기준입니다.
> 화면은 [명세 2026-09-24-01](docs/specs/2026-09-24-01-새-화면.md)에서 처음부터 다시 설계했습니다.

## 기능

첫 화면에는 파일을 놓는 곳 하나만 있습니다. **필기 파일과 새 PDF**를 놓으면 필기 옮기기,
**PDF 여러 개**를 놓으면 문서 합치기가 열립니다. 도구를 고르는 단계는 없습니다.

### 문서 합치기

- 놓은 순서대로 모든 쪽이 결과에 들어가고, 문서마다 쪽 그림을 눌러 빼거나 다시 넣기
- `1-3, 5, 8-` 형식의 쪽 범위 칸 — 쪽 그림 선택과 같은 상태를 가리킴
- 결과 줄에서 쪽을 끌거나 `‹ ›` 로 순서 변경, 기본 순서와 다를 때만 `순서 되돌리기`
- `PDF 더하기`나 놓기로 문서 추가, 문서 `빼기`
- 쪽 그림은 화면에 보일 때만 불러와 수백 쪽 문서도 바로 열림
- 텍스트·벡터·이미지·링크·주석·양식 위젯을 가능한 범위에서 보존
- 미리보기만 PNG로 렌더하고 결과 PDF는 원본 페이지 객체를 복사

### 필기 옮기기

- 필기·형광펜이 들어 있는 Samsung Notes `.sdocx`를 새 PDF 배경으로 이전
- 필기가 들어 있는 Notewise `.notewise`를 새 PDF 배경으로 이전
- 필기가 들어 있는 Goodnotes 6 `.goodnotes`를 새 PDF 배경으로 이전 (실험적, 아래 제한 참고)
- 쪽 추가·삭제 시 본문 지문과 순서를 이용해 공통 쪽 자동 매칭
- 새 PDF에 없는 기존 필기 쪽은 추정 순서에 남기고 기존 배경·필기를 결과 미리보기와 저장본에 보존
- Samsung Notes의 별도 노트 쪽도 원본 순서에 따라 검토·보존. 단색 배경은 필기와 함께 표시하며,
  템플릿·이미지 배경은 미리보기 제한을 표시하되 저장본에는 원본 그대로 보존
- 기계가 자신 없는 쪽만 이유 한 줄과 함께 카드로 보여 줌(옛 쪽과 새 쪽에 실제 필기를 겹쳐서).
  카드마다 `맞아요`·`다른 쪽`(새 PDF의 쪽을 골라 짝 바꾸기)·`빼기`, 나머지 쪽은 `모든 쪽 보기`에 접어 둠
- Sleek 필기본(오른쪽 필기 칸이 있는 PDF)은 칸을 빼고 짝을 지으며, 칸 위에 손필기가 있으면 알림
- 대상 PDF와 원본의 페이지 비율이 달라도 새 PDF 크기·비율을 온전히 보존하며 필기 좌표 자동 변환
- 페이지 크기나 여백 변경 시 본문 위치 기준 자동 정렬
- Samsung Notes 결과의 만든 시각·고친 시각을 옮긴 시각으로 바꿈
- 원본 SDOCX와 PDF를 수정하지 않고 새 `.sdocx`로 저장
- 원본 Notewise와 PDF를 수정하지 않고 새 `.notewise`로 저장
- 원본 Goodnotes 6 문서와 PDF를 수정하지 않고 새 `.goodnotes`로 저장

Goodnotes 목차 입력·생성 기능은 제공하지 않습니다. 기존 목차가 있는 원본은 목차가 사라지지
않도록 저장을 중단합니다.

가로·세로 정렬 배율이 일치하지 않거나 최대 본문 오차가 50mm를 넘거나 쪽 경계 이탈 추정이
5mm 이상이면 모든 짝지은 쪽을 확인할 쪽으로 올립니다. 확인하지 않은 카드가 남은 채 저장하면
한 번 묻고, `그대로 저장`을 눌러야 저장합니다.

## 가장 쉬운 Windows 설치

[**최신 릴리스**](https://github.com/kynbeen/riffle/releases/latest)에서
`Riffle-Setup-<버전>.exe`를 내려받아 실행합니다. Python을 따로 설치할 필요가 없고,
설치 프로그램이 시작 메뉴와 바탕화면에 두 실행 방식의 바로가기를 만듭니다.

서명 인증서가 없어 처음 실행할 때 SmartScreen의 「Windows의 PC 보호」 창이 뜹니다.
**「추가 정보」 → [실행]** 으로 넘어갑니다. 화면 그대로의 안내는
[설치와 첫 사용 안내](docs/설치와-첫-사용.md#파란-경고창이-떴어요)에 있습니다.

### 명령 한 줄로 설치 (원터치)

내려받기와 설치를 한 번에 끝냅니다. PowerShell에 붙여넣고 Enter를 누르면 됩니다.

```powershell
iwr https://raw.githubusercontent.com/kynbeen/riffle/main/install-online.ps1 -OutFile "$env:TEMP\Riffle-install.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\Riffle-install.ps1"
```

[`install-online.ps1`](install-online.ps1)은 최신 릴리스 조회 → 설치 파일 내려받기 →
실행, 이 세 가지만 합니다. 내려받은 파일 크기와 Windows 실행 파일의 `MZ` 헤더를 확인한 뒤에만
실행하며, 기본값은 조용한 설치입니다. `-Wizard` 를 붙이면 설치 위치를 직접 고를 수 있습니다.

### 소스에서 설치 (개발자용)

소스 압축 파일을 받은 사용자는 PowerShell에서 아래 한 줄로 설치할 수도 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Python 3.12 이상이 필요하며, 전용 `venv` 생성·의존성 설치·아이콘 생성·바로가기 등록·PATH 등록을
한 번에 처리합니다. 기존 `setup.ps1`과 `install-app.ps1`은 개발 및 이전 설치 흐름과의 호환을 위해
남아 있습니다.

### PATH 등록

`install.ps1`은 이 폴더를 사용자 PATH에 넣습니다. 그러면 어느 폴더에서든 아래처럼 실행할 수
있습니다(이미 열려 있던 터미널에는 적용되지 않으니 새 창을 여세요).

```powershell
riffle
```

실행 주체는 저장소 루트의 `riffle.cmd`이며, `venv`의 `pythonw.exe`가 있으면 그것으로,
없으면 `dist\Riffle\Riffle.exe`로 앱을 띄웁니다.

`riffle.cmd`는 **저장소 루트에 그대로 두세요.** 이 파일은 자기가 있는 폴더를 Riffle
루트로 보고 `venv`·`dist`를 찾습니다. 다른 폴더로 복사하지 말고, PATH에는 이 폴더를 넣습니다.

이 파일은 ASCII·CRLF로만 저장합니다. `cmd.exe`는 LF만 있는 배치 파일의 `rem` 줄을 명령으로
실행하려 들고, OEM 코드페이지에서 한글 주석을 깨뜨립니다(실제로 겪은 함정입니다).
`.gitattributes`가 체크아웃 때 CRLF를 보장합니다.

## 데스크톱 개발 실행

```powershell
.\install.ps1
.\venv\Scripts\python.exe -m riffle --debug
```

앱 로그는 `%LOCALAPPDATA%\Riffle\app.log`에 기록됩니다.

데스크톱 앱은 웹과 같은 화면(`riffle/ui/`)을 창에 엽니다. 시작할 때 창을 최대화합니다.
파일 고르기·저장은 Windows 대화상자와 Python 브리지(화면이 Python 기능을 부르는 통로)를 쓰고,
창에 끌어다 놓은 파일은 pywebview가 알려 준 경로를 Python이 화면으로 넘깁니다.
`python -m riffle <파일들>` 로 열면 창에 놓은 것과 똑같이 시작합니다(필기 파일과 새 PDF, 또는 PDF 여러 개).
여러 경우를 창 하나씩 띄워 보는 확인 도구는 `tools/open_cases.py` 입니다.

로컬 웹 판(`Riffle 로컬 웹`)은 2026-09-26 걷었습니다. 이 PC 에서는 데스크톱 앱을, 다른 기기에서는 원격 웹을 씁니다.

Sleek 인계 화면(`--open-plan` 합치기·원본 비교)은 2026-09-24 걷었습니다(명세
[2026-09-24-01](docs/specs/2026-09-24-01-새-화면.md)). Sleek 이 사람 없이 Riffle 엔진(`riffle.engine`·`riffle.page_match`·
`riffle.ranges`·`riffle.pdf`)을 직접 부르는 길은 남아 있고 `tests/test_sleek_engine_contract.py` 가 그 입구를 지킵니다.
엔진을 옮기거나 지우기 전에 Sleek 의 `riffle_*_driver.py` 를 먼저 보세요.

## 웹앱 실행

Docker가 있으면 다음 명령만 실행합니다.

```powershell
docker compose up --build
```

브라우저에서 `http://localhost:8000`을 엽니다. Docker 없이 개발 서버를 실행하려면:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\venv\Scripts\python.exe -m riffle.web
```

웹 업로드는 브라우저 세션별 임시 디렉터리에 격리됩니다. 기본 만료 시간은 2시간이며 서버 종료,
세션 만료 또는 `←`(처음으로)를 누를 때 정리됩니다. 결과 파일은 생성 직후 다운로드로 반환되고 서버의
임시 출력은 응답 완료 후 삭제됩니다.

웹앱은 PWA로 제공됩니다. 지원 브라우저의 주소창 또는 메뉴에서 Riffle을 설치하면 독립 창과
앱 아이콘으로 실행할 수 있습니다. 서비스 워커는 UI 파일만 오프라인 캐시하며 `/api/` 요청,
업로드 문서와 변환 결과는 캐시하지 않습니다. 문서 작업에는 서버 연결이 필요합니다.

환경 변수:

| 변수 | 기본값 | 설명 |
|---|---:|---|
| `PORT` | `8000` | 웹 서버 포트 |
| `RIFFLE_HOST` | `0.0.0.0` | 바인드 주소 |
| `RIFFLE_MAX_UPLOAD_MB` | `512` | 파일 하나의 최대 업로드 크기 |
| `RIFFLE_SESSION_TTL` | `7200` | 비활성 작업공간 만료 시간(초) |
| `RIFFLE_MAX_SESSIONS` | `200` | 동시 작업공간 상한. 넘으면 가장 오래 쉰 것부터 정리 |
| `RIFFLE_SWEEP_INTERVAL` | `60` | 만료된 작업공간을 쓸어내는 주기(초) |
| `RIFFLE_PREVIEW_CONCURRENCY` | `2` | 프로세스 전체에서 동시에 렌더링할 미리보기 수 |
| `RIFFLE_PREVIEW_CACHE_MB` | `16` | 사용자 작업공간 하나의 미리보기 LRU 캐시 상한(MB) |
| `RIFFLE_ANALYSIS_CONCURRENCY` | `1` | 동시에 실행할 필기 문서 분석 작업 수 |

### 접속자별 작업공간

접속자마다 임시 폴더 하나가 배정되고, 올린 파일·미리보기·결과는 전부 그 안에서만 삽니다.
브라우저는 `HttpOnly` 쿠키로 자기 작업공간을 가리킵니다. 작업공간 안은 도구별로 다시
나뉩니다 — `uploads/documents/`와 `uploads/handwriting/`.

- **작업공간은 첫 화면과 API 요청에서만 만들어집니다.** 정적 자산과 상시 가동 핑은 만들지
  않습니다. 그러지 않으면 접속 한 번에 아무도 쓰지 않는 폴더가 여러 개 생깁니다.
- **사용자별 응답에는 `Cache-Control: no-store`와 `Vary: Cookie`가 붙습니다.** 중간 프록시가
  이걸 저장하면 다음 사람에게 남의 문서가, 첫 화면이라면 남의 세션 쿠키까지 건네집니다.
- **자동 정리**: 같은 자리에 파일을 다시 올리면 앞엣것을 지웁니다. 목록에서 뺀 문서는 사본까지
  지우고, 등록에 실패한 업로드도 남기지 않습니다. 비활성 작업공간은
  `RIFFLE_SWEEP_INTERVAL`마다 통째로 사라집니다.
- **수동 정리는 `←` 하나입니다.** 첫 화면으로 돌아가면 그 작업공간에 올린 파일을 모두 비웁니다.
  화면을 먼저 닫아 남은 미리보기 요청을 거둔 뒤 비우므로, 늦게 도착한 요청이 실패로 남지 않습니다.

실서비스에서는 Docker 이미지를 HTTPS 역방향 프록시 뒤에 두고, 프록시의 요청 본문 제한도
`RIFFLE_MAX_UPLOAD_MB` 이상으로 맞추세요. Riffle은 로그인 기능을 제공하지 않으므로 공개
인터넷에 배포할 때는 호스팅 플랫폼이나 프록시에서 접근 제어를 추가하는 것을 권장합니다.

## Docker 배포

업체 종속 설정은 없습니다. 저장소 루트의 `Dockerfile`을 빌드할 수 있는 Render, Fly.io,
Cloud Run, Railway 또는 일반 컨테이너 서버에 배포할 수 있습니다.

저장소의 `render.yaml`은 서울과 가까운 싱가포르 리전의 Render 웹 서비스 `useriffle`
(<https://useriffle.onrender.com>, Render 작업공간 `riffle`)을 정의합니다. 무료 인스턴스의 메모리 한계를 고려해 파일 하나당
업로드 한도는 100MB, 비활성 세션 만료는 1시간으로 설정합니다. 업로드와 변환은 모두 Render 컨테이너
안에서 실행되며 사용자 PC에서 별도 서버를 실행할 필요가 없습니다.

**웹은 릴리스 때만 배포됩니다.** 서비스는 `main` 이 아니라 `release` 가지를 따라가고, 그 가지는
`v*` 릴리스 태그를 올렸을 때 `release.yml` 이 옮깁니다(아래 「릴리스 파일 만들기」). 그래서 `main` 에
개발 중 커밋을 올려도 웹은 바뀌지 않습니다. 이미지 안에는 깃이 없어, 그 가지에 버전을 새긴
`riffle/_version.py` 를 한 커밋 더 얹어 싣습니다.

옛 NotEditor 웹(`noteditor` 서비스, <https://not-editor.onrender.com>)은 `noteditor-1.2` 가지(= NotEditor 1.2.0)에
고정돼 계속 돕니다(Render 작업공간 `NotEditor`). Render 무료 인스턴스 시간(월 750시간)은 작업공간 단위라 두 서비스가 따로 씁니다.
`riffle` 주소는 다른 계정이 잡고 있어 받을 수 없었습니다(Render·Fly.io·Railway·Netlify·Vercel 모두) — 그래서 `useriffle` 입니다.

Render 설정은 대시보드 대신 Render CLI(`render`, [render-oss/cli](https://github.com/render-oss/cli))로도 봅니다 —
`render login` 한 번 뒤 `render services`, `render deploys list <서비스 id>`, `render logs`.

```bash
docker build -t riffle .
docker run --rm -p 8000:8000 riffle
```

서버는 상태를 로컬 임시 저장소에만 두므로 여러 인스턴스로 확장할 때는 같은 사용자의 요청이 같은
인스턴스로 가도록 세션 고정(sticky session)을 사용해야 합니다.

## 테스트

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m unittest discover -s tests
```

화면(`web/`)을 고쳤다면 커밋 전에 `web`에서 `npm test`와 `npm run build`를 돌립니다
([web/README.md](web/README.md)). 빌드를 잊으면 `tests/test_new_ui.py`가 실패합니다.

## 릴리스 파일 만들기

### Windows

`v1.0.0` 같은 태그를 푸시하면 `.github/workflows/release.yml`이 다음 작업을 자동 수행합니다.

1. 전체 테스트 실행
2. 태그에서 버전을 확정해 앱과 설치 파일에 함께 새김
3. PyInstaller로 독립 실행 폴더 생성
4. Inno Setup으로 `Riffle-Setup-<버전>.exe` 생성
5. GitHub Release에 설치 파일 첨부
6. 웹 배포 가지 `release` 를 태그 커밋(+ 버전 파일)으로 옮김 → Render 가 웹을 다시 배포

태그 이름과 버전 번호는 모든 제품 공통 원칙(`kynbeen/workspace` 의 `docs/principles/제품-이름과-버전.md`)을 따라
`vMAJOR.MINOR.PATCH` 입니다. 앱 화면에는 이름 `Riffle` 만 보이고, 세부 버전은 이름 위에 마우스를
올렸을 때, `/api/health`, 앱 로그, Windows 설치된 앱 목록에만 나옵니다. NotEditor 시절 태그는 `noteditor-v1.0.0`~`noteditor-v1.2.0` 으로 옮겼고
버전 계산에서 빠집니다.

### 태그를 붙이기 전에

공통 원칙의 「새 태그 전에 할 일」을 따릅니다. Riffle 에서는 구체적으로:

1. 문서를 코드에 맞춘다 — 이 README, [설치와 첫 사용](docs/설치와-첫-사용.md), [현재 상태](docs/current-status.md)
   (기준일·버전·시험 개수), [백로그](docs/backlog.md)(이번 판으로 끝난 항목), [web/README.md](web/README.md).
   걷은 기능·옛 주소는 지우고, 바뀐 것은 고치고, 적힌 곳이 없는 새 기능은 적는다. 날짜 붙은 `docs/handoffs/`·`docs/specs/` 는 고치지 않는다.
2. `python -m unittest discover -s tests`, `web` 에서 `npm test`·`npm run build`(빌드가 바뀌면 커밋).
3. `main` 을 푸시하고 GitHub Actions `test` 가 초록인지 본다. 빨간 채로 태그를 붙이지 않는다.
4. `git tag v<버전>` → `git push origin v<버전>`. 끝나면 `https://useriffle.onrender.com/api/health` 의 `version` 이
   새 버전인지 확인한다.

### 버전은 어디서 오나

**깃 태그가 유일한 출처입니다.** 소스에 버전 번호를 적어 두지 않으므로 앱이 말하는 버전과
설치 파일 버전이 어긋날 일이 없습니다.

| 상황 | `/api/health` 와 앱 로그가 말하는 버전 |
| --- | --- |
| `v1.0.0` 태그로 만든 설치 파일·웹 | `1.0.0` |
| 태그 이후 3커밋 진행한 개발 체크아웃 | `1.0.0+3.gbf90fcf` |
| 커밋하지 않은 수정이 있는 상태 | 뒤에 `.dirty` 가 붙음 |
| 태그가 아직 없는 저장소 | `0.0.0+<커밋해시>` |
| 버전 파일 없이 Render 에 올라간 이미지 | `0.0.0+<커밋해시 7자리>` |
| 알 방법이 전혀 없을 때 | `0.0.0+unknown` |

`RIFFLE_VERSION` 환경변수를 주면 그 값이 무엇보다 우선합니다.
개발 체크아웃에서는 이전 빌드의 `_version.py`가 남아 있어도 현재 Git 커밋을 표시합니다.
설치 파일은 빌드할 때 새긴 릴리스 버전을 표시합니다.

로컬에서는 Python 개발 의존성과 Inno Setup 6을 설치한 뒤 같은 과정을 실행할 수 있습니다.

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m riffle.make_icon
$version = .\venv\Scripts\python.exe -m riffle.stamp_version
.\venv\Scripts\pyinstaller.exe --noconfirm Riffle.spec
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "/DAppVersion=$version" "installer\Riffle.iss"
```

## 폴더 구조

```text
Riffle/                 Git 저장소 루트
├─ riffle/              import 가능한 Python 애플리케이션 패키지
│  └─ ui/                  데스크톱과 웹이 함께 쓰는 화면(web/ 빌드 결과, 커밋함)
├─ web/                    화면 소스(React + Vite + TypeScript)
├─ tests/                  엔진·UI·웹 API 테스트
├─ installer/              Windows 설치 프로그램 정의
├─ .github/workflows/      테스트 및 Release 자동화
├─ Dockerfile              웹 배포 이미지
└─ install.ps1             소스 기반 원터치 Windows 설치
```

저장소와 `riffle` 패키지가 한 단계 중첩된 것은 의도된 구조입니다. Python 런타임 코드와 정적
자원을 하나의 import 패키지로 묶어 테스트·Docker·PyInstaller에서 같은 경로로 찾게 하고, 루트의
문서·설치·배포 파일과 섞이지 않게 합니다.

## 제한 및 안전

- 암호화된 PDF와 DRM 우회는 지원하지 않습니다.
- 페이지 구성이 바뀌므로 기존 디지털 서명은 유효하지 않게 됩니다.
- 여러 원본을 합칠 때 책갈피, 문서 첨부, 문서 단위 서명은 복사하지 않고 경고합니다.
- 필기 이전은 Samsung의 비공개 SDOCX 형식을 이용한 상호운용 기능입니다.
- Notewise 이전은 공개되지 않은 내보내기 형식을 관찰해 구현한 상호운용 기능입니다. PDF 배경
  교체, 페이지 추가·삭제, 본문 기준 자동 정렬, 펜·형광펜 미리보기를 지원합니다. 자동 매칭은
  원본 순서를 보존하지만 사용자가 경고를 확인하면 대상 쪽을 직접 재정렬할 수 있습니다.
  펜·형광펜 외 Notewise 객체의 미리보기 렌더링은 후속 지원 범위입니다.
- **Goodnotes 6 이전은 실험 기능입니다.** 공개되지 않은 `.goodnotes` 형식을 실제 내보내기
  파일로 관찰해 구현했습니다. 동일 비율일 때는 필기 저널(`notes/`)을 원본 바이트 그대로 옮기고,
  비율이 달라질 때만 대상 캔버스에 맞추어 획 좌표계를 안전하게 변환합니다. 다음 경계를 알고 쓰세요.
  - 저장 결과를 **Goodnotes 앱에서 다시 열어 확인한 적은 아직 없습니다**(개발 환경에 macOS·iPad가
    없습니다). 중요한 노트는 원본을 반드시 따로 보관하세요.
  - 검증에 쓴 실제 파일은 Goodnotes 6 Mac 내보내기(스키마 25) **한 쪽짜리 한 개**입니다.
    여러 쪽 문서와 PDF를 가져와 만든 문서는 같은 코드 경로를 타지만 실제 파일로 확인하지
    못했습니다.
  - 펜·볼펜·연필·형광펜·마커는 미리보기에 그리고, 도형·이미지·글상자는 그리지 않습니다.
    **그리지 않을 뿐 저장 결과에는 그대로 남습니다.**
- 원본 파일은 읽기 전용으로 열며 사용자가 요청한 결과 외에는 영구 파일을 만들지 않습니다.

## 라이선스

Riffle 자체 코드는 [MIT License](LICENSE)로 제공됩니다.
데스크톱·웹에서 사용하는 PyMuPDF는 [AGPL-3.0 또는 Artifex 상용 라이선스](https://pymupdf.readthedocs.io/en/latest/about.html)를 따릅니다.
개인 기기에서 혼자 사용하는 데 상용 라이선스가 필수인 것은 아닙니다. 다만 무료 배포도
배포이며, PyMuPDF를 포함한 프로그램의 배포·네트워크 제공에는 해당 라이선스의 소스 제공 등
조건을 검토해야 합니다. 자체 코드의 MIT 표시는 포함된 모든 의존성의 조건을 대체하지 않습니다.
제3자 코드 고지는 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)를 확인하세요.
