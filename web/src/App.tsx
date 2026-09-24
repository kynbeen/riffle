import { useCallback, useEffect, useRef, useState } from 'react'
import { backend, type Held } from './api'
import Handwriting from './Handwriting'
import Merge from './Merge'
import type { Doc } from './merging'
import { decide } from './classify'

// 첫 화면은 놓는 곳 하나다. 놓은 파일로 할 일을 정하고(classify.ts), 곧바로 시작한다(명세 2026-09-24-01).

type Screen =
  | { kind: 'drop' }
  | { kind: 'handwriting'; source: string; target: string }
  | { kind: 'merge'; docs: Doc[] }

export default function App() {
  const [screen, setScreen] = useState<Screen>({ kind: 'drop' })
  const back = useCallback(async () => {
    try { await backend.reset() } catch { /* 비우기에 실패해도 첫 화면으로는 돌아간다 */ }
    setScreen({ kind: 'drop' })
  }, [])
  return (
    <div className="app">
      <header className="topbar">
        {screen.kind !== 'drop' && <button className="back" onClick={back} aria-label="처음으로">←</button>}
        <span className="wordmark">Riffle</span>
      </header>
      <main className="stage">
        {screen.kind === 'drop' && <DropScreen onStart={setScreen} />}
        {screen.kind === 'handwriting' && <Handwriting source={screen.source} target={screen.target} />}
        {screen.kind === 'merge' && <Merge initial={screen.docs} />}
      </main>
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
