import { useCallback, useEffect, useRef, useState } from 'react'
import { backend, type Held, type HandwritingStatus } from './api'
import { decide } from './classify'

// 첫 화면은 놓는 곳 하나다. 놓은 파일로 할 일을 정하고(classify.ts), 곧바로 시작한다(명세 2026-09-24-01).

type Screen =
  | { kind: 'drop' }
  | { kind: 'handwriting'; source: string; target: string }
  | { kind: 'merge'; names: string[] }

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
        {screen.kind === 'handwriting' && <HandwritingScreen source={screen.source} target={screen.target} />}
        {screen.kind === 'merge' && <MergeScreen names={screen.names} />}
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
        await backend.startMerge(decision.pdfs, progress)
        onStart({ kind: 'merge', names: decision.pdfs.map((pdf) => pdf.name) })
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

// 맞추는 동안의 단계는 사람 말로(명세 「필기 옮기기」).
const STAGE_WORDS: Record<string, string> = {
  waiting: '준비하는 중',
  structure: '파일을 살펴보는 중',
  matching: '쪽 짝짓는 중',
  alignment: '필기 위치 맞추는 중',
  preview: '미리보기 만드는 중',
}

function HandwritingScreen({ source, target }: { source: string; target: string }) {
  const [status, setStatus] = useState<HandwritingStatus | null>(null)
  const [failure, setFailure] = useState('')

  useEffect(() => {
    let alive = true
    let timer = 0
    const poll = async () => {
      try {
        const next = await backend.handwritingStatus()
        if (!alive) return
        setStatus(next)
        setFailure('')
        if (next.analysis.state === 'running' || next.analysis.state === 'waiting') timer = window.setTimeout(poll, 700)
      } catch (error) {
        if (alive) setFailure((error as Error).message)
      }
    }
    void poll()
    return () => { alive = false; window.clearTimeout(timer) }
  }, [status?.analysis.state === 'error'])

  const analysis = status?.analysis
  return (
    <section className="panel">
      <div className="t-title">필기 옮기기</div>
      <div className="files t-body"><b>{source}</b><span>→</span><b>{target}</b></div>
      {failure && <div className="message error t-body">{failure}</div>}
      {analysis?.state === 'error' ? (
        <>
          <div className="message error t-body">{analysis.error || '맞추지 못했습니다.'}</div>
          <div><button className="button" onClick={async () => { await backend.retryHandwriting(); setStatus(null) }}>다시 시도</button></div>
        </>
      ) : analysis?.state === 'ready' ? (
        <>
          <div className="t-body">맞추기를 마쳤습니다.</div>
          <div className="note t-body">확인할 쪽을 보여 주는 화면은 아직 만드는 중입니다. 지금은 기존 화면에서 이어서 저장해 주세요.</div>
        </>
      ) : (
        <div className="status t-body"><span className="spinner" aria-hidden /><span>{STAGE_WORDS[analysis?.stage ?? 'waiting'] ?? '맞추는 중'}</span></div>
      )}
    </section>
  )
}

function MergeScreen({ names }: { names: string[] }) {
  return (
    <section className="panel">
      <div className="t-title">문서 합치기 · {names.length}개 문서</div>
      <div className="files t-body">{names.map((name) => <b key={name}>{name}</b>)}</div>
      <div className="note t-body">쪽을 고르고 순서를 바꾸는 화면은 아직 만드는 중입니다. 지금은 기존 화면에서 합쳐 주세요.</div>
    </section>
  )
}
