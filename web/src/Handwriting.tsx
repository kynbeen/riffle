import { useEffect, useMemo, useRef, useState } from 'react'
import { backend, type HandwritingStatus, type PlanRow, type PlanSlot, type Preview, type Saved } from './api'
import { nearTarget, reassign, targetOf, type Slot } from './plan'
import { candidateWords, footnotes, headline, REASON_WORDS, type Reason, type Review, type ReviewSummary } from './reasons'
import Sheet from './Sheet'
import { countFilters, FILTER_WORDS, KIND_WORDS, kindOf, matches, type Context, type Filter, type Mark, type PageKind } from './pages'

// 필기 옮기기 — 확인할 쪽만(명세 2026-09-24-01). 기계가 자신 있게 맞춘 쪽은 목록에 없고,
// 모든 쪽은 궁금할 때만 펼쳐 본다.

const STAGE_WORDS: Record<string, string> = {
  waiting: '준비하는 중',
  structure: '파일을 살펴보는 중',
  matching: '쪽 짝짓는 중',
  alignment: '필기 위치 맞추는 중',
  preview: '미리보기 만드는 중',
}


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
    const mark = s !== null ? marks[s] : undefined          // 모든 쪽 보기에서 뺀 자동 쪽도 센다
    if (mark === 'excluded') { dropped += 1; continue }
    if (watched && mark === 'ok') checked += 1
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
  const closest = useMemo(() => Object.fromEntries(
    review.items.filter((item) => item.closest !== undefined).map((item) => [item.source_index!, item.closest!])) as Record<number, number>,
  [review])
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
  // 두 보기 — 봐야 할 쪽(카드)과 모든 쪽(격자). 봐야 할 쪽이 없으면 모든 쪽에서 시작한다(명세 2026-09-25-01).
  const [view, setView] = useState<'review' | 'all'>(() => review.items.length > 0 ? 'review' : 'all')
  const [filter, setFilter] = useState<Filter>('all')
  const show = (next: Filter) => { setView('all'); setFilter(next) }
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
    const excluded = s !== null && marks[s] === 'excluded'
    if (s !== null && s in reasons) return { ...slot, confirmed: marks[s] === 'ok', excluded }
    return { ...slot, confirmed: true, excluded }
  })

  const key = JSON.stringify(plan())
  const changedSinceSave = saved !== null && saved.key !== key
  // 사람이 정한 것 — 카드에서 누른 것과 직접 고른 짝. 저장하지 않은 채 처음으로 가면 사라진다.
  const decided = chosen.size > 0 || Object.values(marks).some((mark) => mark !== 'open')
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
      {footnotes(counts).map((note) => (
        <div className="t-caption footnote" key={note.text}>
          {note.text} <button className="link" onClick={() => show(note.filter)}>보기</button>
        </div>
      ))}

      <div className="segmented" role="tablist" aria-label="보기">
        <button role="tab" aria-selected={view === 'review'} onClick={() => setView('review')}>봐야 할 쪽 {open}</button>
        <button role="tab" aria-selected={view === 'all'} onClick={() => setView('all')}>모든 쪽 {counts.result_pages}</button>
      </div>

      {view === 'review' && order.length === 0 && <div className="note t-body">봐야 할 쪽이 없습니다.</div>}
      {view === 'review' && order.length > 0 && (
        <div className="cards">
          {order.map((s) => {
            const onMark = (mark: Mark) => setMarks((prev) => ({ ...prev, [s]: mark }))
            // 누른 카드는 한 줄로 접어 남은 카드가 올라오게 한다. 직접 고른 짝은 얹힌 모습을 봐야 하니 펼쳐 둔다.
            return marks[s] !== 'open' && !chosen.has(s)
              ? <CardRow key={s} source={s} target={targetOf(slots, s)} mark={marks[s]} onMark={onMark} />
              : <Card key={s} source={s} target={targetOf(slots, s)} reason={reasons[s]} mark={marks[s]}
                  chosen={chosen.has(s)} candidate={candidates[s]} near={candidates[s] ?? closest[s] ?? nearTarget(slots, s)}
                  similar={closest[s]}
                  targetCount={targetCount} thumbnails={thumbnails.current} previews={previews.current}
                  onMark={onMark} onPick={(target) => pick(s, target)}
                  onReject={() => { dropCandidate(s); onMark('ok') }} />
          })}
        </div>
      )}

      {view === 'all' && (
        <AllPages slots={slots} context={{ reasons, marks, chosen, blank, moved }} filter={filter} onFilter={setFilter}
          previews={previews.current} thumbnails={thumbnails.current} targetCount={targetCount} closest={closest}
          onPick={pick} onMark={(s, mark) => setMarks((prev) => ({ ...prev, [s]: mark }))} />
      )}

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

function Card({ source, target, reason, mark, chosen, candidate, near, similar, targetCount, thumbnails, previews, onMark, onPick, onReject }: {
  source: number; target: number | null; reason: Reason; mark: Mark; chosen: boolean
  candidate?: number; near: number | null; similar?: number; targetCount: number
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
        <TargetPicker count={targetCount} current={target} start={target ?? near} similar={similar} thumbnails={thumbnails}
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
function TargetPicker({ count, current, start, similar, thumbnails, onPick, onClose }: {
  count: number; current: number | null; start: number | null; similar?: number; thumbnails: Map<number, string>
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
            <span className="t-caption">새 {index + 1}쪽{index === similar ? ' · 가장 닮음' : ''}</span>
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

// 모든 쪽 — 결과 순서대로 필기를 얹은 쪽 그림. 표시는 사람이 알아 둘 것에만 붙는다(자동으로 맞춘 쪽은 표시 없음).
// 사람이 뺀 쪽은 원래 자리에 접힌 줄로 둔다 — 따로 모으면 어디서 빠졌는지 모른다. 쪽을 누르면 크게 보고 고친다(단위 4).
function AllPages({ slots, context, filter, onFilter, previews, thumbnails, targetCount, closest, onPick, onMark }: {
  slots: Slot[]; context: Context; filter: Filter; onFilter: (filter: Filter) => void; previews: Map<string, Preview>
  thumbnails: Map<number, string>; targetCount: number; closest: Record<number, number>
  onPick: (source: number, target: number) => void; onMark: (source: number, mark: Mark) => void
}) {
  const [viewing, setViewing] = useState<number | null>(null)
  const [follow, setFollow] = useState<number | null>(null)   // 다른 쪽으로 옮긴 옛 쪽 — 크게 보기가 따라간다
  const kinds = slots.map((slot) => kindOf(slot, context))
  const counts = countFilters(kinds)
  const filters = (Object.keys(FILTER_WORDS) as Filter[]).filter((key) => key === 'all' || counts[key] > 0)
  const shown = slots.map((slot, index) => ({ slot, kind: kinds[index] })).filter(({ kind }) => matches(kind, filter))
  // 옮긴 필기가 얹힌 새 쪽으로 크게 보기를 옮긴다 — 방금 비운 쪽을 보여 주고 끝내지 않는다.
  const followed = follow === null ? -1 : shown.findIndex(({ slot }) => slot.source_index === follow)
  useEffect(() => {
    if (follow === null) return
    if (followed >= 0) setViewing(followed)
    setFollow(null)
  }, [follow, followed])
  // 고친 쪽이 걸러 보기에서 빠지면 목록이 줄어든다 — 가리키던 자리를 목록 안으로 당긴다.
  const at = viewing === null || shown.length === 0 ? null : Math.min(viewing, shown.length - 1)
  return (
    <>
      <div className="filters" role="group" aria-label="걸러 보기">
        {filters.map((key) => (
          <button key={key} className="chip-button" aria-pressed={filter === key} onClick={() => onFilter(key)}>
            {FILTER_WORDS[key]} {counts[key]}
          </button>
        ))}
      </div>
      <div className="page-grid">
        {shown.map(({ slot, kind }, index) => kind === 'excluded'
          ? <button className="excluded-row t-caption" key={`${slot.source_index}-x`} onClick={() => setViewing(index)}>
              옛 {slot.source_index! + 1}쪽 · 뺐습니다
            </button>
          : <PageTile key={`${slot.source_index}-${slot.target_index}`} slot={slot} kind={kind} previews={previews}
              onOpen={() => setViewing(index)} />)}
      </div>
      {at !== null && (
        <PageViewer items={shown} at={at} previews={previews} thumbnails={thumbnails} targetCount={targetCount}
          closest={closest} onMove={setViewing} onClose={() => setViewing(null)}
          onPick={(source, target) => { onPick(source, target); setFollow(source) }} onMark={onMark} />
      )}
    </>
  )
}

// 미리보기 한 장. 카드·격자·크게 보기가 같은 저장소(previews)를 나눠 쓴다 — 한 번 부른 쪽은 다시 부르지 않는다.
function usePreview(targetIndex: number, sourceIndex: number, previews: Map<string, Preview>, wanted: boolean) {
  const key = `${targetIndex}:${sourceIndex}`
  const [state, setState] = useState<{ key: string; view: Preview | null; failed: boolean }>(
    () => ({ key, view: previews.get(key) ?? null, failed: false }))
  const current = state.key === key ? state : { key, view: previews.get(key) ?? null, failed: false }
  useEffect(() => {
    if (!wanted || current.view) return
    const stop = new AbortController()
    backend.preview(targetIndex, sourceIndex, stop.signal)
      .then((view) => { previews.set(key, view); setState({ key, view, failed: false }) })
      .catch(() => { if (!stop.signal.aborted) setState({ key, view: null, failed: true }) })
    return () => stop.abort()
  }, [key, wanted, current.view, previews, targetIndex, sourceIndex])
  return current
}

function pageLabel(slot: Slot, kind: PageKind): string {
  const s = slot.source_index, t = slot.target_index
  if (t === null) return `옛 ${s! + 1}쪽`
  return s === null || kind === 'auto' ? `새 ${t + 1}쪽` : `새 ${t + 1}쪽 · 옛 ${s + 1}쪽 필기`
}

// 격자의 한 쪽. 보일 때만 그림을 부른다 — 97쪽을 한 번에 만들지 않는다.
function PageTile({ slot, kind, previews, onOpen }: {
  slot: Slot; kind: PageKind; previews: Map<string, Preview>; onOpen: () => void
}) {
  const s = slot.source_index, t = slot.target_index
  const [visible, setVisible] = useState(false)
  const box = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (visible || !box.current) return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { observer.disconnect(); setVisible(true) }
    }, { rootMargin: '400px 0px' })
    observer.observe(box.current)
    return () => observer.disconnect()
  }, [visible])
  const { view, failed } = usePreview(t ?? -1, s ?? -1, previews, visible)
  const background = t === null ? view?.before : view?.after
  const label = pageLabel(slot, kind)
  return (
    <button className={`page-tile ${kind}`} ref={box} onClick={onOpen} aria-label={`${label} 크게 보기`}>
      <span className="sheet-of-paper">
        {background ? (
          <>
            <img src={background} alt="" />
            {s !== null && view?.ink && <img className="ink" src={view.ink} alt="" aria-hidden />}
          </>
        ) : (
          <span className="placeholder t-caption">{failed ? '미리보기를 만들지 못했습니다' : ''}</span>
        )}
      </span>
      <span className="page-caption">
        <span className="t-caption">{label}</span>
        {KIND_WORDS[kind] && <span className={`badge ${kind}`}>{KIND_WORDS[kind]}</span>}
      </span>
    </button>
  )
}

// 크게 보기 — 옛 쪽(옛 필기 그대로)과 새 쪽(옮긴 필기)을 크게 나란히. 카드와 같은 단추로 고친다.
// Mac 의 Quick Look 자리. 넘기기는 화면 단추로 한다(키보드 단축키를 두지 않는다 — 닫는 Esc 만).
function PageViewer({ items, at, previews, thumbnails, targetCount, closest, onMove, onClose, onPick, onMark }: {
  items: { slot: Slot; kind: PageKind }[]; at: number; previews: Map<string, Preview>; thumbnails: Map<number, string>
  targetCount: number; closest: Record<number, number>; onMove: (at: number) => void; onClose: () => void
  onPick: (source: number, target: number) => void; onMark: (source: number, mark: Mark) => void
}) {
  const { slot, kind } = items[at]
  const s = slot.source_index, t = slot.target_index
  const [picking, setPicking] = useState(false)
  const dialog = useRef<HTMLDivElement>(null)
  useEffect(() => { dialog.current?.focus() }, [])
  useEffect(() => { setPicking(false) }, [at])
  const old = usePreview(-1, s ?? -1, previews, s !== null)
  const moved = usePreview(t ?? -1, s ?? -1, previews, t !== null)
  const label = pageLabel(slot, kind)
  return (
    <div className="viewer-backdrop" role="dialog" aria-modal="true" aria-label={label}
      onKeyDown={(event) => { if (event.key === 'Escape') onClose() }}>
      <div className="viewer" ref={dialog} tabIndex={-1}>
        <div className="viewer-head">
          <div className="viewer-title">
            <span className="t-title">{label}</span>
            {KIND_WORDS[kind] && <span className={`badge ${kind}`}>{KIND_WORDS[kind]}</span>}
          </div>
          <span className="t-caption">{at + 1} / {items.length}</span>
          <button className="button quiet" onClick={onClose}>닫기</button>
        </div>
        <div className="viewer-pages">
          {s !== null && (
            <Page label={`옛 ${s + 1}쪽`} background={old.view?.before} ink={old.view?.ink} failed={old.failed ? '실패' : ''} />
          )}
          {t !== null && (
            <Page label={s === null ? `새 ${t + 1}쪽 · 필기 없음` : `새 ${t + 1}쪽 · 필기를 얹은 모습`}
              background={moved.view?.after} ink={s === null ? undefined : moved.view?.ink} failed={moved.failed ? '실패' : ''} />
          )}
        </div>
        <div className="viewer-foot">
          <div className="actions">
            {s === null ? (
              <span className="t-caption">새 PDF에서 새로 생긴 쪽입니다. 얹을 옛 필기가 없습니다.</span>
            ) : kind === 'excluded' ? (
              <button className="button" onClick={() => onMark(s, 'open')}>다시 넣기</button>
            ) : (
              <>
                {kind === 'watch' && (
                  <button className="button" onClick={() => onMark(s, 'ok')}>{t === null ? '남기기' : '맞아요'}</button>
                )}
                <button className="button quiet" onClick={() => setPicking((now) => !now)}>다른 쪽</button>
                <button className="button quiet" onClick={() => onMark(s, 'excluded')}>빼기</button>
              </>
            )}
          </div>
          <div className="actions">
            <button className="button quiet" disabled={at === 0} onClick={() => onMove(at - 1)}>이전</button>
            <button className="button quiet" disabled={at === items.length - 1} onClick={() => onMove(at + 1)}>다음</button>
          </div>
        </div>
        {picking && s !== null && (
          <TargetPicker count={targetCount} current={t} start={t ?? closest[s] ?? null} similar={closest[s]}
            thumbnails={thumbnails} onPick={(target) => { setPicking(false); onPick(s, target) }}
            onClose={() => setPicking(false)} />
        )}
      </div>
    </div>
  )
}
