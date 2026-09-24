import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// 글꼴은 빌드 결과에 들어간다 — 인터넷이 없어도 같은 모양이다.
import 'pretendard/dist/web/variable/pretendardvariable.css'
import './styles.css'
import App from './App'
import { backend } from './api'

// 화면에서 난 오류는 앱 기록(데스크톱 %LOCALAPPDATA%\Riffle\app.log · 웹 서버 로그)에 남긴다 — 조용한 실패는 없다(원칙 5).
const report = (value: unknown) => {
  const message = value instanceof Error ? `${value.message}\n${value.stack ?? ''}` : String(value)
  void backend.logError(message).catch(() => { /* 기록이 실패해도 원래 오류를 가리지 않는다 */ })
}
window.addEventListener('error', (event) => report(event.error ?? event.message))
window.addEventListener('unhandledrejection', (event) => report(event.reason))

// 웹에서만 — 데스크톱 창은 파일로 열어 서비스 워커를 쓰지 않는다.
if (backend.runtime === 'web' && 'serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((error) => console.warn('Riffle 웹 앱 설치 준비에 실패했습니다', error))
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
