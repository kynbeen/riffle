import { useEffect, useMemo, useRef, useState } from 'react'
import { backend, type HandwritingStatus, type PlanRow, type PlanSlot, type Preview, type Saved } from './api'
import { reassign, targetOf, type Slot } from './plan'
import { footnotes, headline, REASON_WORDS, type Reason, type Review, type ReviewSummary } from './reasons'

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
        <Ready review={status.review} initial={status.inspection.plan.slots} source={source} />
      ) : (
        <div className="status t-body"><span className="spinner" aria-hidden /><span>{STAGE_WORDS[analysis?.stage ?? 'waiting'] ?? '맞추는 중'}</span></div>
      )}
    </section>
  )
}

// 지금 대응으로 센 요약. 짝을 바꾸면 숫자도 바뀐다.
function tally(slots: Slot[], reasons: Record<number, Reason>, marks: Record<number, Mark>,
               blank: Set<number>, base: ReviewSummary): ReviewSummary & { checked: number; dropped: number } {
  let automatic = 0, keptOld = 0, omitted = 0, newPages = 0, dropped = 0, checked = 0, resultPages = 0
  for (const slot of slots) {
    const s = slot.source_index
    const watched = s !== null && s in reasons
    const mark = watched ? marks[s!] : undefined
    if (mark === 'excluded') { dropped += 1; continue }
    if (mark === 'ok') checked += 1
    if (s !== null && slot.target_index !== null) { if (!watched) automatic += 1 }
    else if (s === null) newPages += 1
    else if (blank.has(s)) { omitted += 1; continue }
    else keptOld += 1
    resultPages += 1
  }
  return { ...base, automatic, attention: Object.keys(reasons).length, new_pages: newPages, kept_old: keptOld,
           omitted, result_pages: resultPages, checked, dropped }
}

function Ready({ review, initial, source }: { review: Review; initial: PlanSlot[]; source: string }) {
  const blank = useMemo(() => new Set(review.blank_sources), [review])
  const [slots, setSlots] = useState<Slot[]>(() => initial.map(({ source_index, target_index }) => ({ source_index, target_index })))
  // 확인할 옛 쪽 → 이유. 카드 순서는 order 가 쥔다(짝을 바꾸면 밀려난 옛 쪽이 새 카드로 붙는다).
  const [reasons, setReasons] = useState<Record<number, Reason>>(
    () => Object.fromEntries(review.items.map((item) => [item.source_index!, item.reason])))
  const [order, setOrder] = useState<number[]>(() => review.items.map((item) => item.source_index!))
  const [marks, setMarks] = useState<Record<number, Mark>>(
    () => Object.fromEntries(review.items.map((item) => [item.source_index!, 'open' as Mark])))
  const [chosen, setChosen] = useState<Set<number>>(new Set())      // 사람이 직접 짝을 고른 옛 쪽
  const [asking, setAsking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<Saved | null>(null)
  const [error, setError] = useState('')
  const [showAll, setShowAll] = useState(false)
  const thumbnails = useRef(new Map<number, string>())
  const targetCount = slots.filter((slot) => slot.target_index !== null).length

  const open = order.filter((s) => marks[s] === 'open').length
  const counts = tally(slots, reasons, marks, blank, review.summary)

  const pick = (s: number, target: number) => {
    const { slots: next, displaced } = reassign(slots, s, target)
    setSlots(next)
    setMarks((prev) => ({ ...prev, [s]: 'ok' }))
    setChosen((prev) => new Set(prev).add(s))
    if (displaced !== null && !blank.has(displaced)) {
      // 밀려난 옛 쪽에 필기가 있으면 옛 쪽째 남기고 사람이 보게 한다 — 조용히 다른 새 쪽으로 옮기지 않는다.
      setReasons((prev) => ({ ...prev, [displaced]: 'old_only' }))
      setMarks((prev) => ({ ...prev, [displaced]: 'open' }))
      setOrder((prev) => prev.includes(displaced) ? prev : [...prev.slice(0, prev.indexOf(s) + 1), displaced, ...prev.slice(prev.indexOf(s) + 1)])
      setChosen((prev) => { const next = new Set(prev); next.delete(displaced); return next })
    }
  }

  // 저장할 쪽 대응. 확인할 쪽이 아닌 것은 기계가 맞춘 대로 두고, 필기 없는 옛 쪽은 뺀다.
  const plan = (): PlanRow[] => slots.map((slot) => {
    const s = slot.source_index
    if (s !== null && s in reasons) {
      return { ...slot, confirmed: marks[s] === 'ok', excluded: marks[s] === 'excluded' }
    }
    return { ...slot, confirmed: true, excluded: s !== null && slot.target_index === null && blank.has(s) }
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

  return (
    <>
      <div className="t-title headline">{headline(counts, open)}</div>
      {footnotes(counts).map((note) => <div className="t-caption" key={note}>{note}</div>)}

      {order.length > 0 && (
        <div className="cards">
          {order.map((s) => (
            <Card key={s} source={s} target={targetOf(slots, s)} reason={reasons[s]} mark={marks[s]}
              chosen={chosen.has(s)} targetCount={targetCount} thumbnails={thumbnails.current}
              onMark={(mark) => setMarks((prev) => ({ ...prev, [s]: mark }))}
              onPick={(target) => pick(s, target)} />
          ))}
        </div>
      )}

      <details className="all" open={showAll} onToggle={(event) => setShowAll((event.target as HTMLDetailsElement).open)}>
        <summary className="t-body">모든 쪽 보기 ({slots.length})</summary>
        {showAll && <AllPages slots={slots} reasons={reasons} marks={marks} blank={blank} chosen={chosen} />}
      </details>

      {error && <div className="message error t-body">{error}</div>}
      {saved ? (
        <div className="saved">
          <div className="t-body"><b>저장했습니다</b>{saved.name ? ` · ${saved.name}` : ''}</div>
          <div className="t-caption">
            {`자동 ${counts.automatic} · 확인 ${counts.checked} · 옛 쪽째 남김 ${counts.kept_old} · 뺀 쪽 ${counts.omitted + counts.dropped}`}
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

function Card({ source, target, reason, mark, chosen, targetCount, thumbnails, onMark, onPick }: {
  source: number; target: number | null; reason: Reason; mark: Mark; chosen: boolean; targetCount: number
  thumbnails: Map<number, string>; onMark: (mark: Mark) => void; onPick: (target: number) => void
}) {
  // 옛 쪽은 옛 쪽 자체의 틀로(옛 필기 그대로), 새 쪽은 새 틀에 옮긴 필기로 — 필기본처럼 새 쪽이 넓어도
  // 옛 쪽이 작게 쪼그라들지 않는다.
  const [oldView, setOldView] = useState<Preview | null>(null)
  const [newView, setNewView] = useState<Preview | null>(null)
  const [failed, setFailed] = useState('')
  const [picking, setPicking] = useState(false)
  useEffect(() => {
    let alive = true
    backend.preview(-1, source).then((view) => { if (alive) setOldView(view) })
      .catch((error: Error) => { if (alive) setFailed(error.message) })
    return () => { alive = false }
  }, [source])
  useEffect(() => {
    let alive = true
    setNewView(null)
    if (target !== null) {
      backend.preview(target, source).then((view) => { if (alive) setNewView(view) })
        .catch((error: Error) => { if (alive) setFailed(error.message) })
    }
    return () => { alive = false }
  }, [source, target])
  const words = chosen
    ? { title: '직접 고른 짝입니다', detail: '옛 필기를 고르신 새 쪽에 얹습니다. 제자리에 있는지 봐 주세요.' }
    : REASON_WORDS[reason]
  return (
    <article className={`card ${mark}`}>
      <div className="pages">
        <Page label={`옛 ${source + 1}쪽`} background={oldView?.before} ink={oldView?.ink} failed={failed} />
        {target !== null && (
          <Page label={`새 ${target + 1}쪽`} background={newView?.after} ink={newView?.ink} failed={failed} />
        )}
      </div>
      <div className="why">
        <div className="t-body"><b>{words.title}</b></div>
        <div className="t-caption">{words.detail}</div>
        <div className="actions">
          {mark === 'open' ? (
            <>
              <button className="button" onClick={() => onMark('ok')}>{target === null ? '남기기' : '맞아요'}</button>
              <button className="button quiet" onClick={() => setPicking((now) => !now)}>다른 쪽</button>
              <button className="button quiet" onClick={() => onMark('excluded')}>빼기</button>
            </>
          ) : (
            <>
              <span className="t-caption">{mark === 'ok' ? '확인했습니다' : '결과에서 뺐습니다'}</span>
              <button className="button quiet" onClick={() => onMark('open')}>{mark === 'ok' ? '되돌리기' : '다시 넣기'}</button>
              {mark === 'ok' && <button className="button quiet" onClick={() => setPicking((now) => !now)}>다른 쪽</button>}
            </>
          )}
        </div>
      </div>
      {picking && (
        <TargetPicker count={targetCount} current={target} thumbnails={thumbnails}
          onPick={(chosenTarget) => { setPicking(false); onPick(chosenTarget) }}
          onClose={() => setPicking(false)} />
      )}
    </article>
  )
}

// 새 PDF 의 쪽을 가로로 펼쳐 하나를 고른다. 쪽 그림은 보일 때만 불러온다.
function TargetPicker({ count, current, thumbnails, onPick, onClose }: {
  count: number; current: number | null; thumbnails: Map<number, string>
  onPick: (target: number) => void; onClose: () => void
}) {
  const strip = useRef<HTMLDivElement>(null)
  const [, redraw] = useState(0)
  useEffect(() => {
    const root = strip.current
    if (!root) return
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const index = Number((entry.target as HTMLElement).dataset.index)
        observer.unobserve(entry.target)
        if (thumbnails.has(index)) continue
        backend.preview(index, -1).then((view) => { thumbnails.set(index, view.after); redraw((n) => n + 1) }).catch(() => {})
      }
    }, { root, rootMargin: '0px 400px' })
    root.querySelectorAll('[data-index]').forEach((node) => observer.observe(node))
    root.querySelector('.current')?.scrollIntoView({ inline: 'center', block: 'nearest' })
    return () => observer.disconnect()
  }, [thumbnails])
  return (
    <div className="picker" onKeyDown={(event) => { if (event.key === 'Escape') onClose() }}>
      <div className="picker-head">
        <span className="t-caption">옛 필기를 얹을 새 쪽을 고르세요</span>
        <button className="button quiet" onClick={onClose}>닫기</button>
      </div>
      <div className="strip" ref={strip}>
        {Array.from({ length: count }, (_, index) => (
          <button key={index} data-index={index} className={`thumb${index === current ? ' current' : ''}`}
            onClick={() => onPick(index)} aria-label={`새 ${index + 1}쪽`}>
            {thumbnails.has(index)
              ? <img src={thumbnails.get(index)} alt="" />
              : <span className="thumb-empty" />}
            <span className="t-caption">새 {index + 1}쪽</span>
          </button>
        ))}
      </div>
    </div>
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

function AllPages({ slots, reasons, marks, blank, chosen }: {
  slots: Slot[]; reasons: Record<number, Reason>; marks: Record<number, Mark>; blank: Set<number>; chosen: Set<number>
}) {
  return (
    <ol className="all-list">
      {slots.map((slot) => {
        const s = slot.source_index
        const watched = s !== null && s in reasons
        const mark = watched ? marks[s!] : undefined
        let state = '자동'
        if (watched) state = mark === 'excluded' ? '뺌' : chosen.has(s!) ? '직접 고름' : mark === 'ok' ? '확인함' : '볼 쪽'
        else if (s === null) state = '새로 생긴 쪽'
        else if (slot.target_index === null) state = blank.has(s) ? '필기가 없어 뺌' : '옛 쪽째 남김'
        const pair = s !== null && slot.target_index !== null
          ? `옛 ${s + 1}쪽 → 새 ${slot.target_index + 1}쪽`
          : s === null ? `새 ${slot.target_index! + 1}쪽` : `옛 ${s + 1}쪽`
        return (
          <li key={`${s}-${slot.target_index}`} className={watched && mark === 'open' ? 'attention' : ''}>
            <span className="t-body">{pair}</span><span className="t-caption">{state}</span>
          </li>
        )
      })}
    </ol>
  )
}
