import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// 글꼴은 빌드 결과에 들어간다 — 인터넷이 없어도 같은 모양이다.
import 'pretendard/dist/web/variable/pretendardvariable.css'
import './styles.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
