import { useCallback, useEffect, useRef, useState } from 'react'
import { backend, type Held } from './api'
import Handwriting from './Handwriting'
import Merge from './Merge'
import type { Doc } from './merging'
import { decide } from './classify'
import Sheet from './Sheet'

// 첫 화면은 놓는 곳 하나다. 놓은 파일로 할 일을 정하고(classify.ts), 곧바로 시작한다(명세 2026-09-24-01).

type Screen =
  | { kind: 'drop' }
  | { kind: 'handwriting'; source: string; target: string }
  | { kind: 'merge'; docs: Doc[] }

export default function App() {
  const [screen, setScreen] = useState<Screen>({ kind: 'drop' })
  const [version, setVersion] = useState('')
  useEffect(() => { backend.health().then((reply) => setVersion(reply.version)).catch(() => {}) }, [])
  // 사람이 정한 것을 저장하지 않았으면 처음으로 가기 전에 한 번 묻는다. 원본은 남아도 판단은 사라진다(원칙 7).
  const [unsaved, setUnsaved] = useState(false)
  const [asking, setAsking] = useState(false)
  // 화면을 먼저 닫아 남은 미리보기 요청을 거둔 뒤 서버를 비운다(거꾸로 하면 늦게 온 요청이 실패로 남는다).
  const leave = useCallback(async () => {
    setAsking(false)
    setUnsaved(false)
    setScreen({ kind: 'drop' })
    try { await backend.reset() } catch { /* 비우기에 실패해도 첫 화면으로는 돌아간다 */ }
  }, [])
  const back = () => (unsaved ? setAsking(true) : void leave())
  // 데스크톱 창은 제목 표시줄 없이 화면을 채운다(명세 2026-09-25-03). 이 막대가 제목 표시줄 노릇을 한다 — 빈 곳을
  // 끌면 창이 움직이고(pywebview-drag-region), 두 번 누르면 최대화·복원, 오른쪽 끝에 Windows 창 단추 셋.
  const frame = backend.window
  return (
    <div className="app">
      <header className={`topbar${frame ? ' pywebview-drag-region framed' : ''}`}
        onDoubleClick={frame ? (event) => { if (event.target === event.currentTarget) void frame.toggleMaximize() } : undefined}>
        {screen.kind !== 'drop' && <button className="back" onClick={back} aria-label="처음으로" title="처음으로">←</button>}
        <span className="wordmark" title={version ? `Riffle ${version}` : undefined}>Riffle</span>
        {frame && (
          <div className="window-buttons">
            <button aria-label="최소화" title="최소화" onClick={() => void frame.minimize()}>
              <svg viewBox="0 0 10 10" aria-hidden><path d="M0 5h10" /></svg>
            </button>
            <button aria-label="최대화 또는 복원" title="최대화 또는 복원" onClick={() => void frame.toggleMaximize()}>
              <svg viewBox="0 0 10 10" aria-hidden><rect x="0.5" y="0.5" width="9" height="9" rx="1" /></svg>
            </button>
            <button className="close" aria-label="닫기" title="닫기" onClick={() => void frame.close()}>
              <svg viewBox="0 0 10 10" aria-hidden><path d="M0 0l10 10M10 0L0 10" /></svg>
            </button>
          </div>
        )}
      </header>
      <main className="stage">
        {screen.kind === 'drop' && <DropScreen onStart={setScreen} />}
        {screen.kind === 'handwriting' && <Handwriting source={screen.source} target={screen.target} onUnsaved={setUnsaved} />}
        {screen.kind === 'merge' && <Merge initial={screen.docs} />}
      </main>
      {asking && (
        <Sheet title="정한 것을 저장하지 않았습니다" cancel="돌아가기" confirm="처음으로"
          onCancel={() => setAsking(false)} onConfirm={() => void leave()}>
          처음으로 가면 카드에서 정한 것이 사라집니다. 옛 필기 파일과 새 PDF는 그대로 남아 있습니다.
        </Sheet>
      )}
    </div>
  )
}

function DropScreen({ onStart }: { onStart: (screen: Screen) => void }) {
  const [held, setHeld] = useState<Held[]>([])
  const [message, setMessage] = useState<{ text: string; error: boolean }>({ text: '', error: false })
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState<{ label: string; share: number | null } | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const heldRef = useRef(held)
  heldRef.current = held

  const accept = useCallback(async (added: Held[]) => {
    if (!added.length) return
    const decision = decide(heldRef.current, added)
    if (decision.kind === 'wait') {
      setHeld(decision.held)
      setMessage({ text: decision.message, error: false })
      return
    }
    if (decision.kind === 'reject') {
      setMessage({ text: decision.message, error: true })
      return
    }
    const uploading = backend.runtime === 'web'
    setBusy({ label: uploading ? '올리는 중' : '여는 중', share: uploading ? 0 : null })
    const progress = (share: number) => setBusy({ label: '올리는 중', share })
    try {
      if (decision.kind === 'handwriting') {
        await backend.startHandwriting(decision.source, decision.target, progress)
        onStart({ kind: 'handwriting', source: decision.source.name, target: decision.target.name })
      } else {
        const docs = await backend.startMerge(decision.pdfs, progress)
        onStart({ kind: 'merge', docs })
      }
    } catch (error) {
      setBusy(null)
      setMessage({ text: (error as Error).message, error: true })
    }
  }, [onStart])

  // 창 어디에 놓아도 받는다. 데스크톱 창에서는 브라우저가 경로를 알려 주지 않아 Python 이 밀어 준다.
  useEffect(() => {
    let depth = 0
    const enter = (event: DragEvent) => { event.preventDefault(); depth += 1; setOver(true) }
    const leave = () => { depth = Math.max(0, depth - 1); if (!depth) setOver(false) }
    const overHandler = (event: DragEvent) => event.preventDefault()
    const drop = (event: DragEvent) => {
      event.preventDefault()
      depth = 0
      setOver(false)
      if (backend.runtime === 'desktop') return
      const files = Array.from(event.dataTransfer?.files ?? [])
      void accept(files.map((file) => ({ name: file.name, file })))
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragleave', leave)
    window.addEventListener('dragover', overHandler)
    window.addEventListener('drop', drop)
    window.__riffleDropped = (files) => { void accept(files) }
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('dragover', overHandler)
      window.removeEventListener('drop', drop)
      window.__riffleDropped = undefined
    }
  }, [accept])

  const choose = async () => {
    if (backend.pickFiles) {
      try { await accept(await backend.pickFiles()) }
      catch (error) { setMessage({ text: (error as Error).message, error: true }) }
    } else {
      input.current?.click()
    }
  }

  return (
    <section className={`drop${over ? ' over' : ''}`} aria-label="파일 놓는 곳">
      <div className="t-display">파일을 여기에 놓으세요</div>
      <div className="rules t-body">
        <span><b>필기 파일과 새 PDF</b> → 필기 옮기기</span>
        <span><b>PDF 여러 개</b> → 문서 합치기</span>
      </div>
      {held.length > 0 && (
        <div className="held">{held.map((file) => <span className="chip" key={file.name}>{file.name}</span>)}</div>
      )}
      {message.text && <div className={`message t-body${message.error ? ' error' : ''}`} role="status">{message.text}</div>}
      {busy ? (
        <div className="status t-body">
          {busy.share === null
            ? <span className="spinner" aria-hidden />
            : <span className="progress"><span style={{ width: `${Math.round(busy.share * 100)}%` }} /></span>}
          <span>{busy.label}</span>
        </div>
      ) : (
        <button className="button" onClick={choose}>파일 고르기</button>
      )}
      <input
        ref={input} type="file" multiple hidden accept=".sdocx,.notewise,.goodnotes,.pdf"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? [])
          event.target.value = ''
          void accept(files.map((file) => ({ name: file.name, file })))
        }}
      />
    </section>
  )
}
