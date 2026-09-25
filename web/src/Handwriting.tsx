import { useEffect, useMemo, useRef, useState } from 'react'
import { backend, type HandwritingStatus, type PlanRow, type PlanSlot, type Preview, type Saved } from './api'
import { nearTarget, reassign, targetOf, type Slot } from './plan'
import { candidateWords, footnotes, headline, REASON_WORDS, type Reason, type Review, type ReviewSummary } from './reasons'
import Sheet from './Sheet'

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

export default function Handwriting({ source, target, onUnsaved }: {
  source: string; target: string; onUnsaved: (unsaved: boolean) => void
}) {
  const [status, setStatus] = useState<HandwritingStatus | null>(null)
  const [failure, setFailure] = useState('')
  const [retries, setRetries] = useState(0)
  const [dropped, setDropped] = useState(false)

  // 이 화면에 놓인 파일은 받지 않는다. 막지 않으면 웹 브라우저가 그 파일을 열어 검토하던 것이 통째로 사라진다(원칙 7).
  useEffect(() => {
    const over = (event: DragEvent) => event.preventDefault()
    const drop = (event: DragEvent) => { event.preventDefault(); setDropped(true) }
    window.addEventListener('dragover', over)
    window.addEventListener('drop', drop)
    window.__riffleDropped = () => setDropped(true)
    return () => {
      window.removeEventListener('dragover', over)
      window.removeEventListener('drop', drop)
      window.__riffleDropped = undefined
    }
  }, [])

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
      {source.toLowerCase().endsWith('.goodnotes') && (
        <div className="t-caption">Goodnotes 옮기기는 아직 실험 단계입니다. 저장한 파일을 Goodnotes에서 열어 확인해 주세요.</div>
      )}
      {dropped && (
        <div className="note t-body" role="status">
          지금은 필기를 옮기는 중입니다. 다른 파일로 시작하려면 ← 로 처음으로 가세요.
        </div>
      )}
      {failure && <div className="message error t-body">{failure}</div>}
      {analysis?.state === 'error' ? (
        <>
          <div className="message error t-body">{analysis.error || '맞추지 못했습니다.'}</div>
          <div><button className="button" onClick={async () => { await backend.retryHandwriting(); setRetries((n) => n + 1) }}>다시 시도</button></div>
        </>
      ) : analysis?.state === 'ready' && status?.review && status.inspection?.plan ? (
        <Ready review={status.review} initial={status.inspection.plan.slots} source={source} onUnsaved={onUnsaved} />
      ) : (
        <div className="status t-body"><span className="spinner" aria-hidden /><span>{STAGE_WORDS[analysis?.stage ?? 'waiting'] ?? '맞추는 중'}</span></div>
      )}
    </section>
  )
}

// 지금 대응으로 센 요약. 짝을 바꾸면 숫자도 바뀐다.
function tally(slots: Slot[], reasons: Record<number, Reason>, marks: Record<number, Mark>,
               blank: Set<number>, base: ReviewSummary): ReviewSummary & { checked: number; dropped: number } {
  let automatic = 0, keptOld = 0, keptBlank = 0, newPages = 0, dropped = 0, checked = 0, resultPages = 0
  for (const slot of slots) {
    const s = slot.source_index
    const watched = s !== null && s in reasons
    const mark = watched ? marks[s!] : undefined
    if (mark === 'excluded') { dropped += 1; continue }
    if (mark === 'ok') checked += 1
    if (s !== null && slot.target_index !== null) { if (!watched) automatic += 1 }
    else if (s === null) newPages += 1
    else { keptOld += 1; if (blank.has(s)) keptBlank += 1 }
    resultPages += 1
  }
  return { ...base, automatic, attention: Object.keys(reasons).length, new_pages: newPages, kept_old: keptOld,
           kept_blank: keptBlank, result_pages: resultPages, checked, dropped }
}

type Counts = ReturnType<typeof tally>

function Ready({ review, initial, source, onUnsaved }: {
  review: Review; initial: PlanSlot[]; source: string; onUnsaved: (unsaved: boolean) => void
}) {
  const blank = useMemo(() => new Set(review.blank_sources), [review])
  const moved = useMemo(() => new Set(review.moved_sources ?? []), [review])
  // 짝 후보 — 새 PDF에 없는 옛 쪽과 닮았지만 확신이 없는 새 쪽(서버 reorder.py). 사람이 정하면 지운다.
  const [candidates, setCandidates] = useState<Record<number, number>>(() => Object.fromEntries(
    review.items.filter((item) => item.candidate !== undefined).map((item) => [item.source_index!, item.candidate!])))
  const dropCandidate = (s: number) => setCandidates((prev) => { const next = { ...prev }; delete next[s]; return next })
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
  // 저장한 순간의 결과·숫자·쪽 대응. 요약은 이 숫자로 말한다 — 저장 뒤에 바꾼 것을 저장한 것처럼 말하지 않는다(원칙 5).
  const [saved, setSaved] = useState<{ result: Saved; counts: Counts; key: string } | null>(null)
  const [error, setError] = useState('')
  const [showAll, setShowAll] = useState(false)
  const thumbnails = useRef(new Map<number, string>())
  // 카드 미리보기. 접었다 펼칠 때마다 다시 부르지 않는다(처음으로 갈 때 늦게 도착하는 요청도 줄어든다).
  const previews = useRef(new Map<string, Preview>())
  const targetCount = slots.filter((slot) => slot.target_index !== null).length

  const open = order.filter((s) => marks[s] === 'open').length
  const counts = tally(slots, reasons, marks, blank, review.summary)

  const pick = (s: number, target: number) => {
    const { slots: next, displaced } = reassign(slots, s, target)
    setSlots(next)
    setMarks((prev) => ({ ...prev, [s]: 'ok' }))
    setChosen((prev) => new Set(prev).add(s))
    dropCandidate(s)
    // 밀려난 옛 쪽은 옛 쪽째 남는다(합집합). 필기가 있으면 사람이 보게 한다 — 조용히 다른 새 쪽으로 옮기지 않는다.
    if (displaced !== null && !blank.has(displaced)) {
      setReasons((prev) => ({ ...prev, [displaced]: 'old_only' }))
      setMarks((prev) => ({ ...prev, [displaced]: 'open' }))
      setOrder((prev) => prev.includes(displaced) ? prev : [...prev.slice(0, prev.indexOf(s) + 1), displaced, ...prev.slice(prev.indexOf(s) + 1)])
      setChosen((prev) => { const next = new Set(prev); next.delete(displaced); return next })
    }
  }

  // 저장할 쪽 대응. 확인할 쪽이 아닌 것은 기계가 맞춘 대로 둔다. 새 PDF 에 없는 옛 쪽은 필기가 없어도 남긴다(합집합).
  const plan = (): PlanRow[] => slots.map((slot) => {
    const s = slot.source_index
    if (s !== null && s in reasons) {
      return { ...slot, confirmed: marks[s] === 'ok', excluded: marks[s] === 'excluded' }
    }
    return { ...slot, confirmed: true, excluded: false }
  })

  const key = JSON.stringify(plan())
  const changedSinceSave = saved !== null && saved.key !== key
  // 사람이 정한 것 — 카드에서 누른 것과 직접 고른 짝. 저장하지 않은 채 처음으로 가면 사라진다.
  const decided = chosen.size > 0 || order.some((s) => marks[s] !== 'open')
  const unsaved = decided && (saved === null || changedSinceSave)
  useEffect(() => { onUnsaved(unsaved) }, [unsaved, onUnsaved])

  const save = async (allowUnconfirmed: boolean) => {
    setAsking(false)
    setSaving(true)
    setError('')
    const rows = plan()
    const snapshot = counts
    try {
      const name = `${source.replace(/\.[^.]+$/, '')}-필기`
      const result = await backend.saveHandwriting(name, rows, allowUnconfirmed)
      if (result.saved) setSaved({ result, counts: snapshot, key: JSON.stringify(rows) })
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
          {order.map((s) => {
            const onMark = (mark: Mark) => setMarks((prev) => ({ ...prev, [s]: mark }))
            // 누른 카드는 한 줄로 접어 남은 카드가 올라오게 한다. 직접 고른 짝은 얹힌 모습을 봐야 하니 펼쳐 둔다.
            return marks[s] !== 'open' && !chosen.has(s)
              ? <CardRow key={s} source={s} target={targetOf(slots, s)} mark={marks[s]} onMark={onMark} />
              : <Card key={s} source={s} target={targetOf(slots, s)} reason={reasons[s]} mark={marks[s]}
                  chosen={chosen.has(s)} candidate={candidates[s]} near={candidates[s] ?? nearTarget(slots, s)}
                  targetCount={targetCount} thumbnails={thumbnails.current} previews={previews.current}
                  onMark={onMark} onPick={(target) => pick(s, target)}
                  onReject={() => { dropCandidate(s); onMark('ok') }} />
          })}
        </div>
      )}

      <details className="all" open={showAll} onToggle={(event) => setShowAll((event.target as HTMLDetailsElement).open)}>
        <summary className="t-body">모든 쪽 보기 ({slots.length})</summary>
        {showAll && <AllPages slots={slots} reasons={reasons} marks={marks} blank={blank} chosen={chosen} moved={moved} />}
      </details>

      {error && <div className="message error t-body">{error}</div>}
      {/* 저장 막대는 화면 아래에 붙어 늘 보인다 — 카드가 많아도 스크롤 끝까지 찾으러 가지 않는다. */}
      <div className="footer">
        {saved && !changedSinceSave ? (
          <div className="saved">
            <div className="t-body"><b>저장했습니다</b>{saved.result.name ? ` · ${saved.result.name}` : ''}</div>
            <div className="t-caption">
              {`자동 ${saved.counts.automatic} · 확인 ${saved.counts.checked} · 옛 쪽째 남김 ${saved.counts.kept_old} · 뺀 쪽 ${saved.counts.dropped}`}
            </div>
            {/* 필기 옮기기 결과의 경고는 "확인 안 한 쪽을 승인하고 저장함" 하나뿐이고, 위 요약 줄이 이미 말한다. */}
            {saved.result.path && backend.openFolder && (
              <div><button className="button quiet" onClick={() => backend.openFolder!(saved.result.path!)}>폴더 열기</button></div>
            )}
          </div>
        ) : (
          <div className="savebar">
            <span className="t-caption">
              {[changedSinceSave ? '저장한 뒤 바꾼 것이 있습니다' : '', open > 0 ? `${open}쪽을 아직 보지 않았습니다` : '']
                .filter(Boolean).join(' · ')}
            </span>
            <button className="button" disabled={saving} onClick={() => (open > 0 ? setAsking(true) : void save(false))}>
              {saving ? '저장하는 중' : '새 파일로 저장'}
            </button>
          </div>
        )}
      </div>

      {asking && (
        <Sheet title={`${open}쪽을 아직 보지 않았습니다`} cancel="돌아가기" confirm="그대로 저장"
          onCancel={() => setAsking(false)} onConfirm={() => void save(true)}>
          기계가 맞춘 대로 저장합니다. 옛 필기 파일은 그대로 남아 있어 언제든 다시 옮길 수 있습니다.
        </Sheet>
      )}
    </>
  )
}

function Card({ source, target, reason, mark, chosen, candidate, near, targetCount, thumbnails, previews, onMark, onPick, onReject }: {
  source: number; target: number | null; reason: Reason; mark: Mark; chosen: boolean
  candidate?: number; near: number | null; targetCount: number
  thumbnails: Map<number, string>; previews: Map<string, Preview>; onMark: (mark: Mark) => void; onPick: (target: number) => void; onReject: () => void
}) {
  // 짝이 없고 후보가 있으면 후보 새 쪽을 옆에 놓는다 — 판단은 그림으로(원칙 2).
  const asking = target === null && mark === 'open' && candidate !== undefined
  const shown = target ?? (asking ? candidate! : null)
  // 옛 쪽은 옛 쪽 자체의 틀로(옛 필기 그대로), 새 쪽은 새 틀에 옮긴 필기로 — 필기본처럼 새 쪽이 넓어도
  // 옛 쪽이 작게 쪼그라들지 않는다.
  const [oldView, setOldView] = useState<Preview | null>(() => previews.get(`-1:${source}`) ?? null)
  const [newView, setNewView] = useState<Preview | null>(null)
  const load = (targetIndex: number, set: (view: Preview) => void, signal: AbortSignal) => {
    const key = `${targetIndex}:${source}`
    const kept = previews.get(key)
    if (kept) { set(kept); return }
    backend.preview(targetIndex, source, signal).then((view) => { previews.set(key, view); set(view) })
      .catch((error: Error) => { if (!signal.aborted) setFailed(error.message) })
  }
  const [failed, setFailed] = useState('')
  const [picking, setPicking] = useState(false)
  useEffect(() => {
    const stop = new AbortController()
    load(-1, setOldView, stop.signal)
    return () => stop.abort()
  }, [source])
  useEffect(() => {
    const stop = new AbortController()
    setNewView(null)
    if (shown !== null) load(shown, setNewView, stop.signal)
    return () => stop.abort()
  }, [source, shown])
  const words = chosen
    ? { title: '직접 고른 짝입니다', detail: '옛 필기를 고르신 새 쪽에 얹습니다. 제자리에 있는지 봐 주세요.' }
    : asking ? candidateWords(candidate!) : REASON_WORDS[reason]
  return (
    <article className={`card ${mark}`}>
      <div className="pages">
        <Page label={`옛 ${source + 1}쪽`} background={oldView?.before} ink={oldView?.ink} failed={failed} />
        {shown !== null && (
          <Page label={asking ? `새 ${shown + 1}쪽 · 필기를 얹으면` : `새 ${shown + 1}쪽`}
            background={newView?.after} ink={newView?.ink} failed={failed} />
        )}
      </div>
      <div className="why">
        <div className="t-body"><b>{words.title}</b></div>
        <div className="t-caption">{words.detail}</div>
        <div className="actions">
          {asking ? (
            <>
              <button className="button" onClick={() => onPick(candidate!)}>같은 쪽이에요</button>
              <button className="button quiet" onClick={onReject}>아니에요</button>
              <button className="button quiet" onClick={() => setPicking((now) => !now)}>다른 쪽</button>
            </>
          ) : mark === 'open' ? (
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
        <TargetPicker count={targetCount} current={target} start={target ?? near} thumbnails={thumbnails}
          onPick={(chosenTarget) => { setPicking(false); onPick(chosenTarget) }}
          onClose={() => setPicking(false)} />
      )}
    </article>
  )
}

// 정한 카드는 한 줄로. 무엇을 정했는지와 되돌리는 단추만 남긴다.
function CardRow({ source, target, mark, onMark }: {
  source: number; target: number | null; mark: Mark; onMark: (mark: Mark) => void
}) {
  const pair = target === null ? `옛 ${source + 1}쪽` : `옛 ${source + 1}쪽 → 새 ${target + 1}쪽`
  const state = mark === 'excluded' ? '결과에서 뺐습니다' : target === null ? '옛 쪽째 남깁니다' : '확인했습니다'
  return (
    <article className="card-row">
      <span className="t-body">{pair}</span>
      <span className="t-caption">{state}</span>
      <button className="button quiet" onClick={() => onMark('open')}>{mark === 'excluded' ? '다시 넣기' : '되돌리기'}</button>
    </article>
  )
}

// 새 PDF 의 쪽을 가로로 펼쳐 하나를 고른다. 쪽 그림은 보일 때만 불러온다.
function TargetPicker({ count, current, start, thumbnails, onPick, onClose }: {
  count: number; current: number | null; start: number | null; thumbnails: Map<number, string>
  onPick: (target: number) => void; onClose: () => void
}) {
  const strip = useRef<HTMLDivElement>(null)
  const [, redraw] = useState(0)
  useEffect(() => {
    const root = strip.current
    if (!root) return
    const stop = new AbortController()
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const index = Number((entry.target as HTMLElement).dataset.index)
        observer.unobserve(entry.target)
        if (thumbnails.has(index)) continue
        backend.preview(index, -1, stop.signal).then((view) => { thumbnails.set(index, view.after); redraw((n) => n + 1) }).catch(() => {})
      }
    }, { root, rootMargin: '0px 400px' })
    root.querySelectorAll('[data-index]').forEach((node) => observer.observe(node))
    // 1쪽부터 훑게 하지 않는다 — 지금 짝, 후보, 또는 옛 쪽 자리에서 가장 가까운 새 쪽에서 시작한다.
    if (start !== null) root.querySelector(`[data-index="${start}"]`)?.scrollIntoView({ inline: 'center', block: 'nearest' })
    return () => { observer.disconnect(); stop.abort() }
  }, [thumbnails, start])
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

function AllPages({ slots, reasons, marks, blank, chosen, moved }: {
  slots: Slot[]; reasons: Record<number, Reason>; marks: Record<number, Mark>; blank: Set<number>; chosen: Set<number>
  moved: Set<number>
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
        else if (moved.has(s) && slot.target_index !== null) state = '자동 · 순서 바뀜'
        else if (slot.target_index === null) state = blank.has(s) ? '옛 쪽째 남김 · 필기 없음' : '옛 쪽째 남김'
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
