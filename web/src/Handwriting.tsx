import { useEffect, useMemo, useState } from 'react'
import { backend, type HandwritingStatus, type PlanRow, type PlanSlot, type Preview, type Saved } from './api'
import { footnotes, headline, REASON_WORDS, type Review, type ReviewItem } from './reasons'

// 필기 옮기기 — 확인할 쪽만(명세 2026-09-24-01). 기계가 자신 있게 맞춘 쪽은 목록에 없고,
// 모든 쪽은 궁금할 때만 펼쳐 본다.

const STAGE_WORDS: Record<string, string> = {
  waiting: '준비하는 중',
  structure: '파일을 살펴보는 중',
  matching: '쪽 짝짓는 중',
  alignment: '필기 위치 맞추는 중',
  preview: '미리보기 만드는 중',
}

type Mark = 'open' | 'ok' | 'excluded'

export default function Handwriting({ source, target }: { source: string; target: string }) {
  const [status, setStatus] = useState<HandwritingStatus | null>(null)
  const [failure, setFailure] = useState('')
  const [retries, setRetries] = useState(0)

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
  }, [retries])

  const analysis = status?.analysis
  return (
    <section className="panel wide">
      <div className="t-title">필기 옮기기</div>
      <div className="files t-body"><b>{source}</b><span>→</span><b>{target}</b></div>
      {failure && <div className="message error t-body">{failure}</div>}
      {analysis?.state === 'error' ? (
        <>
          <div className="message error t-body">{analysis.error || '맞추지 못했습니다.'}</div>
          <div><button className="button" onClick={async () => { await backend.retryHandwriting(); setRetries((n) => n + 1) }}>다시 시도</button></div>
        </>
      ) : analysis?.state === 'ready' && status?.review && status.inspection?.plan ? (
        <Ready review={status.review} slots={status.inspection.plan.slots} source={source} />
      ) : (
        <div className="status t-body"><span className="spinner" aria-hidden /><span>{STAGE_WORDS[analysis?.stage ?? 'waiting'] ?? '맞추는 중'}</span></div>
      )}
    </section>
  )
}

function Ready({ review, slots, source }: { review: Review; slots: PlanSlot[]; source: string }) {
  const attention = useMemo(() => new Map(review.items.map((item) => [item.slot, item])), [review])
  const [marks, setMarks] = useState<Record<number, Mark>>(
    () => Object.fromEntries(review.items.map((item) => [item.slot, 'open' as Mark])))
  const [asking, setAsking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<Saved | null>(null)
  const [error, setError] = useState('')
  const [showAll, setShowAll] = useState(false)
  const open = review.items.filter((item) => marks[item.slot] === 'open').length

  // 저장할 쪽 대응. 확인할 쪽이 아닌 것은 기계가 맞춘 대로 두고, 필기 없는 옛 쪽은 뺀다(review.py 가 부르지 않은 옛 쪽 전용).
  const plan = (): PlanRow[] => slots.map((slot, position) => {
    const mark = marks[position]
    if (attention.has(position)) {
      return { source_index: slot.source_index, target_index: slot.target_index,
               confirmed: mark === 'ok', excluded: mark === 'excluded' }
    }
    const blankOld = slot.target_index === null
    return { source_index: slot.source_index, target_index: slot.target_index, confirmed: true, excluded: blankOld }
  })

  const save = async (allowUnconfirmed: boolean) => {
    setAsking(false)
    setSaving(true)
    setError('')
    try {
      const name = `${source.replace(/\.[^.]+$/, '')}-필기`
      const result = await backend.saveHandwriting(name, plan(), allowUnconfirmed)
      if (result.saved) setSaved(result)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const s = review.summary
  const excluded = Object.values(marks).filter((mark) => mark === 'excluded').length
  return (
    <>
      <div className="t-title headline">{headline(s, open)}</div>
      {footnotes(s).map((note) => <div className="t-caption" key={note}>{note}</div>)}

      {review.items.length > 0 && (
        <div className="cards">
          {review.items.map((item) => (
            <Card key={item.slot} item={item} mark={marks[item.slot]}
              onMark={(mark) => setMarks((prev) => ({ ...prev, [item.slot]: mark }))} />
          ))}
        </div>
      )}

      <details className="all" open={showAll} onToggle={(event) => setShowAll((event.target as HTMLDetailsElement).open)}>
        <summary className="t-body">모든 쪽 보기 ({slots.length})</summary>
        {showAll && <AllPages slots={slots} attention={attention} marks={marks} />}
      </details>

      {error && <div className="message error t-body">{error}</div>}
      {saved ? (
        <div className="saved">
          <div className="t-body"><b>저장했습니다</b>{saved.name ? ` · ${saved.name}` : ''}</div>
          <div className="t-caption">
            {`자동 ${s.automatic} · 확인 ${s.attention - open - excluded} · 옛 쪽째 남김 ${s.kept_old} · 뺀 쪽 ${s.omitted + excluded}`}
          </div>
          {(saved.warnings ?? [])
            // 확인하지 않고 저장한 쪽 수는 위 요약 줄이 이미 말한다 — 옛 화면용 문장을 되풀이하지 않는다.
            .filter((warning) => !warning.startsWith('확인하지 않은 쪽 대응'))
            .map((warning) => <div className="t-caption" key={warning}>{warning}</div>)}
          {saved.path && backend.openFolder && (
            <div><button className="button quiet" onClick={() => backend.openFolder!(saved.path!)}>폴더 열기</button></div>
          )}
        </div>
      ) : (
        <div className="savebar">
          {open > 0 && <span className="t-caption">{open}쪽을 아직 보지 않았습니다</span>}
          <button className="button" disabled={saving} onClick={() => (open > 0 ? setAsking(true) : void save(false))}>
            {saving ? '저장하는 중' : '새 파일로 저장'}
          </button>
        </div>
      )}

      {asking && (
        <div className="sheet-backdrop" role="dialog" aria-modal="true" aria-label="확인하지 않은 쪽"
          onKeyDown={(event) => { if (event.key === 'Escape') setAsking(false) }}>
          <div className="sheet">
            <div className="t-title">{open}쪽을 아직 보지 않았습니다</div>
            <div className="t-body">기계가 맞춘 대로 저장합니다. 원본은 그대로 남아 있어 언제든 다시 옮길 수 있습니다.</div>
            <div className="sheet-actions">
              <button className="button quiet" autoFocus onClick={() => setAsking(false)}>돌아가기</button>
              <button className="button" onClick={() => void save(true)}>그대로 저장</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function Card({ item, mark, onMark }: { item: ReviewItem; mark: Mark; onMark: (mark: Mark) => void }) {
  // 옛 쪽은 옛 쪽 자체의 틀로(옛 필기 그대로), 새 쪽은 새 틀에 옮긴 필기로 — 필기본처럼 새 쪽이 넓어도
  // 옛 쪽이 작게 쪼그라들지 않는다.
  const [oldView, setOldView] = useState<Preview | null>(null)
  const [newView, setNewView] = useState<Preview | null>(null)
  const [failed, setFailed] = useState('')
  useEffect(() => {
    let alive = true
    const fail = (error: Error) => { if (alive) setFailed(error.message) }
    if (item.source_index !== null) {
      backend.preview(-1, item.source_index).then((view) => { if (alive) setOldView(view) }).catch(fail)
    }
    if (item.target_index !== null) {
      backend.preview(item.target_index, item.source_index ?? -1).then((view) => { if (alive) setNewView(view) }).catch(fail)
    }
    return () => { alive = false }
  }, [item])
  const words = REASON_WORDS[item.reason]
  return (
    <article className={`card ${mark}`}>
      <div className="pages">
        {item.source_index !== null && (
          <Page label={`옛 ${item.source_index + 1}쪽`} background={oldView?.before} ink={oldView?.ink} failed={failed} />
        )}
        {item.target_index !== null && (
          <Page label={`새 ${item.target_index + 1}쪽`} background={newView?.after} ink={newView?.ink} failed={failed} />
        )}
      </div>
      <div className="why">
        <div className="t-body"><b>{words.title}</b></div>
        <div className="t-caption">{words.detail}</div>
        <div className="actions">
          {mark === 'open' ? (
            <>
              <button className="button" onClick={() => onMark('ok')}>맞아요</button>
              <button className="button quiet" onClick={() => onMark('excluded')}>빼기</button>
            </>
          ) : (
            <>
              <span className="t-caption">{mark === 'ok' ? '확인했습니다' : '결과에서 뺐습니다'}</span>
              <button className="button quiet" onClick={() => onMark('open')}>{mark === 'ok' ? '되돌리기' : '다시 넣기'}</button>
            </>
          )}
        </div>
      </div>
    </article>
  )
}

function Page({ label, background, ink, failed }: { label: string; background?: string; ink?: string; failed: string }) {
  return (
    <figure className="page">
      <div className="sheet-of-paper">
        {background ? (
          <>
            <img src={background} alt={label} />
            {ink && <img className="ink" src={ink} alt="" aria-hidden />}
          </>
        ) : (
          <div className="placeholder t-caption">{failed ? '미리보기를 만들지 못했습니다' : <span className="spinner" aria-hidden />}</div>
        )}
      </div>
      <figcaption className="t-caption">{label}</figcaption>
    </figure>
  )
}

function AllPages({ slots, attention, marks }: {
  slots: PlanSlot[]
  attention: Map<number, ReviewItem>
  marks: Record<number, Mark>
}) {
  return (
    <ol className="all-list">
      {slots.map((slot, position) => {
        const item = attention.get(position)
        const mark = marks[position]
        let state = '자동'
        if (item) state = mark === 'ok' ? '확인함' : mark === 'excluded' ? '뺌' : '볼 쪽'
        else if (slot.source_index === null) state = '새로 생긴 쪽'
        else if (slot.target_index === null) state = '필기가 없어 뺌'
        const pair = slot.source_index !== null && slot.target_index !== null
          ? `옛 ${slot.source_index + 1}쪽 → 새 ${slot.target_index + 1}쪽`
          : slot.source_index === null ? `새 ${slot.target_index! + 1}쪽` : `옛 ${slot.source_index + 1}쪽`
        return (
          <li key={position} className={item && mark === 'open' ? 'attention' : ''}>
            <span className="t-body">{pair}</span><span className="t-caption">{state}</span>
          </li>
        )
      })}
    </ol>
  )
}
