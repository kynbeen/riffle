import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { backend, type HandwritingStatus, type PlanRow, type PlanSlot, type Preview, type Saved } from './api'
import { bands, links } from './links'
import { nearTarget, reassign, sourcesOf, targetOf, toRows, withDropped, type Slot } from './plan'
import { candidateWords, footnotes, headline, REASON_WORDS, type Reason, type Review, type ReviewSummary } from './reasons'
import Sheet from './Sheet'
import { countFilters, FILTER_WORDS, KIND_WORDS, kindOf, matches, oldKind, type Context, type Filter, type Mark, type PageKind } from './pages'

// 필기 옮기기(명세 2026-09-24-01 · 2026-09-25-03). 기본은 앱을 믿고 맡긴다 — 결론 한 줄, 알아 둘 것, 기계가 자신 없는
// 쪽의 카드만. 믿음이 흔들리면 `연결 보기` 에서 옛 파일과 새 파일, 그 사이의 짝을 한눈에 본다(요청 2·7).

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
  const plan = status?.inspection?.plan
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
      ) : analysis?.state === 'ready' && status?.review && plan ? (
        <Ready review={status.review} initial={plan.slots} droppedAtStart={plan.excluded_sources ?? []}
          relocated={status.inspection?.relocated_targets ?? []} source={source} onUnsaved={onUnsaved} />
      ) : (
        <div className="status t-body"><span className="spinner" aria-hidden /><span>{STAGE_WORDS[analysis?.stage ?? 'waiting'] ?? '맞추는 중'}</span></div>
      )}
    </section>
  )
}

// 지금 짝으로 센 요약. 짝을 바꾸면 숫자도 바뀐다.
function tally(slots: Slot[], reasons: Record<number, Reason>, marks: Record<number, Mark>,
               blank: Set<number>, base: ReviewSummary): ReviewSummary & { checked: number; dropped: number } {
  let automatic = 0, keptOld = 0, keptBlank = 0, newPages = 0, dropped = 0, checked = 0, resultPages = 0
  for (const slot of slots) {
    const all = sourcesOf(slot)
    const live = all.filter((s) => marks[s] !== 'excluded')     // 연결 보기에서 뺀 자동 쪽도 센다
    dropped += all.length - live.length
    if (all.length && !live.length) continue                    // 이 줄은 결과에서 빠진다
    const s = slot.source_index
    const watched = s !== null && s in reasons
    if (watched && marks[s] === 'ok') checked += 1
    if (slot.target_index !== null && live.length) { if (!watched) automatic += 1 }
    else if (slot.target_index !== null) newPages += 1
    else { keptOld += 1; if (live.every((one) => blank.has(one))) keptBlank += 1 }
    resultPages += 1
  }
  return { ...base, automatic, attention: Object.keys(reasons).length, new_pages: newPages, kept_old: keptOld,
           kept_blank: keptBlank, result_pages: resultPages, checked, dropped }
}

type Counts = ReturnType<typeof tally>

function Ready({ review, initial, droppedAtStart, relocated, source, onUnsaved }: {
  review: Review; initial: PlanSlot[]; droppedAtStart: number[]; relocated: number[]; source: string
  onUnsaved: (unsaved: boolean) => void
}) {
  const notes = review.notes_mode === 'notes'
  const blank = useMemo(() => new Set(review.blank_sources), [review])
  const moved = useMemo(() => new Set(review.moved_sources ?? []), [review])
  const relocatedSet = useMemo(() => new Set(relocated), [relocated])
  // 짝 후보 — 새 PDF에 없는 옛 쪽과 닮았지만 확신이 없는 새 쪽(서버 reorder.py). 사람이 정하면 지운다.
  const [candidates, setCandidates] = useState<Record<number, number>>(() => Object.fromEntries(
    review.items.filter((item) => item.candidate !== undefined).map((item) => [item.source_index!, item.candidate!])))
  const closest = useMemo(() => Object.fromEntries(
    review.items.filter((item) => item.closest !== undefined).map((item) => [item.source_index!, item.closest!])) as Record<number, number>,
  [review])
  const dropCandidate = (s: number) => setCandidates((prev) => { const next = { ...prev }; delete next[s]; return next })
  // 서버가 결과에서 뺀 옛 쪽(새 필기본에 없는 빈 쪽)도 원래 자리에 둔다 — `뺀 쪽` 으로 보이고 되돌릴 수 있다.
  const [slots, setSlots] = useState<Slot[]>(() => withDropped(
    initial.map(({ source_index, target_index, merged }) => (merged?.length ? { source_index, target_index, merged } : { source_index, target_index })),
    droppedAtStart))
  const startMarks = useMemo<Record<number, Mark>>(() => ({
    ...Object.fromEntries(droppedAtStart.map((s) => [s, 'excluded' as Mark])),
    ...Object.fromEntries(review.items.map((item) => [item.source_index!, 'open' as Mark])),
  }), [review, droppedAtStart])
  // 확인할 옛 쪽 → 이유. 카드 순서는 order 가 쥔다(짝을 바꾸면 밀려난 옛 쪽이 새 카드로 붙는다).
  const [reasons, setReasons] = useState<Record<number, Reason>>(
    () => Object.fromEntries(review.items.map((item) => [item.source_index!, item.reason])))
  const [order, setOrder] = useState<number[]>(() => review.items.map((item) => item.source_index!))
  const [marks, setMarks] = useState<Record<number, Mark>>(startMarks)
  const [chosen, setChosen] = useState<Set<number>>(new Set())      // 사람이 직접 짝을 고른 옛 쪽
  const [asking, setAsking] = useState(false)
  const [saving, setSaving] = useState(false)
  // 저장한 순간의 결과·숫자·쪽 짝. 요약은 이 숫자로 말한다 — 저장 뒤에 바꾼 것을 저장한 것처럼 말하지 않는다(원칙 5).
  const [saved, setSaved] = useState<{ result: Saved; counts: Counts; key: string } | null>(null)
  const [error, setError] = useState('')
  // 두 보기 — 봐야 할 쪽(요약과 카드)과 연결 보기. 늘 요약에서 시작한다 — 기본은 믿고 맡기는 것(요청 2).
  const [view, setView] = useState<'review' | 'links'>('review')
  const [filter, setFilter] = useState<Filter>('all')
  const show = (next: Filter | null) => { setView('links'); setFilter(next ?? 'all') }
  const thumbnails = useRef(new Map<number, string>())
  // 미리보기. 카드·연결 보기·크게 보기가 나눠 쓴다 — 한 번 부른 쪽은 다시 부르지 않는다.
  const previews = useRef(new Map<string, Preview>())
  const targetCount = slots.filter((slot) => slot.target_index !== null).length
  const sourceCount = new Set(slots.flatMap(sourcesOf)).size

  const open = order.filter((s) => marks[s] === 'open').length
  const counts = tally(slots, reasons, marks, blank, review.summary)
  const setMark = (s: number, mark: Mark) => setMarks((prev) => ({ ...prev, [s]: mark }))

  const pick = (s: number, target: number) => {
    const { slots: next, displaced } = reassign(slots, s, target, notes)
    setSlots(next)
    setMark(s, 'ok')
    setChosen((prev) => new Set(prev).add(s))
    dropCandidate(s)
    // 밀려난 옛 쪽은 옛 쪽째 남는다(합집합). 필기가 있으면 사람이 보게 한다 — 조용히 다른 새 쪽으로 옮기지 않는다.
    if (displaced !== null && !blank.has(displaced)) {
      setReasons((prev) => ({ ...prev, [displaced]: 'old_only' }))
      setMark(displaced, 'open')
      setOrder((prev) => prev.includes(displaced) ? prev : [...prev.slice(0, prev.indexOf(s) + 1), displaced, ...prev.slice(prev.indexOf(s) + 1)])
      setChosen((prev) => { const next = new Set(prev); next.delete(displaced); return next })
    }
  }

  // 저장할 쪽 짝. 확인할 쪽이 아닌 것은 기계가 맞춘 대로 둔다. 새 PDF 에 없는 옛 쪽은 필기가 없어도 남긴다(합집합) —
  // 필기본끼리 새 판에 없는 빈 옛 쪽은 처음부터 뺀 채로 온다.
  const plan = (): PlanRow[] => toRows(slots, (s) => marks[s] === 'excluded', (slot) => {
    const s = slot.source_index
    return s !== null && s in reasons ? marks[s] === 'ok' : true
  })

  const key = JSON.stringify(plan())
  const changedSinceSave = saved !== null && saved.key !== key
  // 사람이 정한 것 — 카드에서 누른 것, 직접 고른 짝, 연결 보기에서 빼거나 다시 넣은 것. 저장 전 처음으로 가면 사라진다.
  const decided = chosen.size > 0 || Object.entries(marks).some(([s, mark]) => mark !== (startMarks[Number(s)] ?? 'open'))
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

  const context: Context = { reasons, marks, chosen, blank, moved, relocated: relocatedSet }
  return (
    <>
      <div className="t-title headline">{headline(counts, open, notes)}</div>
      {footnotes(counts).map((note) => (
        <div className="t-caption footnote" key={note.text}>
          {note.text}{note.filter && <> <button className="link" onClick={() => show(note.filter)}>보기</button></>}
        </div>
      ))}

      <div className="segmented" role="tablist" aria-label="보기">
        <button role="tab" aria-selected={view === 'review'} onClick={() => setView('review')}>봐야 할 쪽 {open}</button>
        <button role="tab" aria-selected={view === 'links'} onClick={() => show(null)}>연결 보기</button>
      </div>

      {view === 'review' && order.length === 0 && (
        <div className="calm">
          <div className="t-body">봐야 할 쪽이 없습니다. 기계가 모든 쪽을 자신 있게 맞췄습니다.</div>
          <div className="t-caption">
            옛 필기 파일과 새 PDF의 쪽이 어떻게 이어졌는지 궁금하면 <button className="link" onClick={() => show(null)}>연결 보기</button>
          </div>
        </div>
      )}
      {view === 'review' && order.length > 0 && (
        <div className="cards">
          {order.map((s) => {
            const onMark = (mark: Mark) => setMark(s, mark)
            // 누른 카드는 한 줄로 접어 남은 카드가 올라오게 한다. 직접 고른 짝은 얹힌 모습을 봐야 하니 펼쳐 둔다.
            const target = targetOf(slots, s)
            const together = target === null ? [s] : live(slots.find((slot) => slot.target_index === target)!, marks)
            return marks[s] !== 'open' && !chosen.has(s)
              ? <CardRow key={s} source={s} target={target} mark={marks[s]} onMark={onMark} />
              : <Card key={s} source={s} target={target} together={together} reason={reasons[s]} mark={marks[s]}
                  chosen={chosen.has(s)} candidate={candidates[s]} near={candidates[s] ?? closest[s] ?? nearTarget(slots, s)}
                  similar={closest[s]}
                  targetCount={targetCount} thumbnails={thumbnails.current} previews={previews.current}
                  onMark={onMark} onPick={(target) => pick(s, target)}
                  onReject={() => { dropCandidate(s); onMark('ok') }} />
          })}
        </div>
      )}

      {view === 'links' && (
        <Links slots={slots} context={context} sourceCount={sourceCount} targetCount={targetCount}
          filter={filter} onFilter={setFilter} previews={previews.current} thumbnails={thumbnails.current}
          closest={closest} onPick={pick} onMark={setMark} />
      )}

      {error && <div className="message error t-body">{error}</div>}
      {/* 저장 막대는 화면 아래에 붙어 늘 보인다 — 카드가 많아도 스크롤 끝까지 찾으러 가지 않는다. */}
      <div className="footer">
        {saved && !changedSinceSave ? (
          <div className="saved">
            <div className="t-body"><b>저장했습니다</b>{saved.result.name ? ` · ${saved.result.name}` : ''}</div>
            <div className="t-caption">
              {`${saved.counts.result_pages}쪽 · 자동 ${saved.counts.automatic} · 확인 ${saved.counts.checked} · 옛 쪽째 남김 ${saved.counts.kept_old} · 뺀 쪽 ${saved.counts.dropped}`}
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

// 이 줄에 실제로 필기를 얹는 옛 쪽 — 뺀 쪽은 빠진다.
function live(slot: Slot, marks: Record<number, Mark>): number[] {
  return sourcesOf(slot).filter((s) => marks[s] !== 'excluded')
}

function Card({ source, target, together, reason, mark, chosen, candidate, near, similar, targetCount, thumbnails, previews, onMark, onPick, onReject }: {
  source: number; target: number | null; together: number[]; reason: Reason; mark: Mark; chosen: boolean
  candidate?: number; near: number | null; similar?: number; targetCount: number
  thumbnails: Map<number, string>; previews: Map<string, Preview>; onMark: (mark: Mark) => void; onPick: (target: number) => void; onReject: () => void
}) {
  // 짝이 없고 후보가 있으면 후보 새 쪽을 옆에 놓는다 — 판단은 그림으로(원칙 2).
  const asking = target === null && mark === 'open' && candidate !== undefined
  const shown = target ?? (asking ? candidate! : null)
  // 옛 쪽은 옛 쪽 자체의 틀로(옛 필기 그대로), 새 쪽은 새 틀에 옮긴 필기로. 새 쪽에 다른 옛 쪽도 함께 얹히면 그것까지.
  const old = usePreview(-1, [source], previews, true)
  const moved = usePreview(shown ?? -1, target === null ? [source] : together, previews, shown !== null)
  const [picking, setPicking] = useState(false)
  const words = chosen
    ? { title: '직접 고른 짝입니다', detail: '옛 필기를 고르신 새 쪽에 얹습니다. 제자리에 있는지 봐 주세요.' }
    : asking ? candidateWords(candidate!) : REASON_WORDS[reason]
  return (
    <article className={`card ${mark}`}>
      <div className="pages">
        <Page label={`옛 ${source + 1}쪽`} background={old.view?.before} ink={old.view?.ink} failed={old.failed} />
        {shown !== null && (
          <Page label={asking ? `새 ${shown + 1}쪽 · 필기를 얹으면` : `새 ${shown + 1}쪽`}
            background={moved.view?.after} ink={moved.view?.ink} failed={moved.failed} />
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

function Page({ label, background, ink, failed }: { label: string; background?: string; ink?: string; failed: boolean }) {
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

// 미리보기 한 장 — 새 쪽(`targetIndex`, 없으면 -1)에 옛 쪽들(`sources`)의 필기를 얹은 모습.
function usePreview(targetIndex: number, sources: number[], previews: Map<string, Preview>, wanted: boolean) {
  const key = `${targetIndex}:${sources.join(',')}`
  const [state, setState] = useState<{ key: string; view: Preview | null; failed: boolean }>(
    () => ({ key, view: previews.get(key) ?? null, failed: false }))
  const current = state.key === key ? state : { key, view: previews.get(key) ?? null, failed: false }
  useEffect(() => {
    if (!wanted || current.view) return
    const stop = new AbortController()
    const ask = targetIndex === -1 ? (sources[0] ?? -1) : sources
    backend.preview(targetIndex, ask, stop.signal)
      .then((view) => { previews.set(key, view); setState({ key, view, failed: false }) })
      .catch(() => { if (!stop.signal.aborted) setState({ key, view: null, failed: true }) })
    return () => stop.abort()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, wanted, current.view, previews, targetIndex])
  return current
}

function useVisible<T extends Element>() {
  const [visible, setVisible] = useState(false)
  const box = useRef<T>(null)
  useEffect(() => {
    if (visible || !box.current) return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { observer.disconnect(); setVisible(true) }
    }, { rootMargin: '600px 0px' })
    observer.observe(box.current)
    return () => observer.disconnect()
  }, [visible])
  return { box, visible }
}

// 연결 보기 — 왼쪽 옛 필기 파일, 오른쪽 새 PDF, 가운데 짝을 잇는 선(명세 2026-09-25-03, 요청 7). 두 띠는 각자 제 순서
// 그대로이고, 짝끼리 같은 높이에 와서 대부분의 선이 곧다. 순서가 바뀐 쪽만 선이 건너간다. 쪽이나 선을 누르면 크게 본다.
function Links({ slots, context, sourceCount, targetCount, filter, onFilter, previews, thumbnails, closest, onPick, onMark }: {
  slots: Slot[]; context: Context; sourceCount: number; targetCount: number; filter: Filter
  onFilter: (filter: Filter) => void; previews: Map<string, Preview>; thumbnails: Map<number, string>
  closest: Record<number, number>; onPick: (source: number, target: number) => void; onMark: (source: number, mark: Mark) => void
}) {
  const laid = useMemo(() => bands(slots, sourceCount, targetCount), [slots, sourceCount, targetCount])
  const slotOfSource = useMemo(() => new Map(slots.flatMap((slot, index) => sourcesOf(slot).map((s) => [s, index] as const))), [slots])
  const slotOfTarget = useMemo(() => new Map(slots.flatMap((slot, index) => slot.target_index === null ? [] : [[slot.target_index, index] as const])), [slots])
  const kinds = slots.map((slot) => kindOf(slot, context))
  const counts = countFilters(kinds)
  const filters = (Object.keys(FILTER_WORDS) as Filter[]).filter((key) => key === 'all' || counts[key] > 0)
  const oldKindOf = (s: number) => oldKind(s, slots[slotOfSource.get(s)!], context)
  const newKindOf = (t: number) => kinds[slotOfTarget.get(t)!]
  const [viewing, setViewing] = useState<number | null>(null)
  const [follow, setFollow] = useState<number | null>(null)   // 다른 쪽으로 옮긴 옛 쪽 — 크게 보기가 따라간다
  useEffect(() => {
    if (follow === null) return
    const at = slotOfSource.get(follow)
    if (at !== undefined) setViewing(at)
    setFollow(null)
  }, [follow, slotOfSource])

  // 선 — 쪽 그림이 자리를 잡은 뒤 실제 자리를 재서 긋는다. 그림이 뜨거나 창 크기가 바뀌면 다시 잰다.
  const box = useRef<HTMLDivElement>(null)
  const [paths, setPaths] = useState<{ d: string; kind: string; key: string }[]>([])
  const [size, setSize] = useState({ width: 0, height: 0 })
  const frame = useRef(0)
  const measure = useCallback(() => {
    cancelAnimationFrame(frame.current)
    frame.current = requestAnimationFrame(() => {
      const root = box.current
      if (!root) return
      const base = root.getBoundingClientRect()
      const found: { d: string; kind: string; key: string }[] = []
      for (const { old, target } of links(slots)) {
        const left = root.querySelector(`[data-old="${old}"] .sheet-of-paper`)?.getBoundingClientRect()
        const right = root.querySelector(`[data-new="${target}"] .sheet-of-paper`)?.getBoundingClientRect()
        if (!left || !right) continue
        const x1 = left.right - base.left, y1 = left.top + left.height / 2 - base.top
        const x2 = right.left - base.left, y2 = right.top + right.height / 2 - base.top
        const bend = Math.max(16, (x2 - x1) / 2)
        found.push({ d: `M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`, kind: oldKindOf(old), key: `${old}-${target}` })
      }
      setPaths(found)
      setSize({ width: root.scrollWidth, height: root.scrollHeight })
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slots, context])
  useLayoutEffect(() => {
    measure()
    const observer = new ResizeObserver(measure)
    if (box.current) observer.observe(box.current)
    return () => { observer.disconnect(); cancelAnimationFrame(frame.current) }
  }, [measure])

  // 걸러 보기는 숨기지 않고 흐리게 한다 — 두 띠의 짝이 흩어지면 "한눈에" 가 깨진다. 첫 쪽으로 데려간다.
  const lit = (band: { olds: number[]; target: number | null }) => filter === 'all'
    || band.olds.some((s) => matches(oldKindOf(s), filter))
    || (band.target !== null && matches(newKindOf(band.target), filter))
  useEffect(() => {
    if (filter === 'all') return
    box.current?.querySelector('.band:not(.dim)')?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [filter])

  return (
    <>
      <div className="filters" role="group" aria-label="걸러 보기">
        {filters.map((key) => (
          <button key={key} className="chip-button" aria-pressed={filter === key} onClick={() => onFilter(key)}>
            {FILTER_WORDS[key]} {counts[key]}
          </button>
        ))}
      </div>
      <div className="links" ref={box} onLoadCapture={measure}>
        <div className="links-head t-caption">
          <span>옛 필기 파일 · {sourceCount}쪽</span><span />
          <span>새 PDF · {targetCount}쪽 · 결과는 이 순서</span>
        </div>
        <svg className="links-lines" width={size.width} height={size.height} aria-hidden>
          {paths.map((path) => <path key={path.key} d={path.d} className={`line ${path.kind}`} />)}
        </svg>
        {laid.map((band) => (
          <div className={`band${lit(band) ? '' : ' dim'}`} key={`${band.olds.join('.')}:${band.target}`}>
            <div className="band-old">
              {band.olds.map((s) => (
                <LinkTile key={s} side="old" index={s} kind={oldKindOf(s)} sources={[s]} previews={previews}
                  onOpen={() => setViewing(slotOfSource.get(s)!)} />
              ))}
            </div>
            <div className="band-gap" />
            <div className="band-new">
              {band.target !== null && (
                <LinkTile side="new" index={band.target} kind={newKindOf(band.target)}
                  sources={live(slots[slotOfTarget.get(band.target)!], context.marks)} previews={previews}
                  onOpen={() => setViewing(slotOfTarget.get(band.target!)!)} />
              )}
            </div>
          </div>
        ))}
      </div>
      {viewing !== null && viewing < slots.length && (
        <PageViewer slots={slots} at={viewing} context={context} previews={previews} thumbnails={thumbnails}
          targetCount={targetCount} closest={closest} onMove={setViewing} onClose={() => setViewing(null)}
          onPick={(source, target) => { onPick(source, target); setFollow(source) }} onMark={onMark} />
      )}
    </>
  )
}

// 연결 보기의 쪽 하나. 보일 때만 그림을 부른다 — 150쪽을 한 번에 만들지 않는다.
function LinkTile({ side, index, kind, sources, previews, onOpen }: {
  side: 'old' | 'new'; index: number; kind: PageKind; sources: number[]; previews: Map<string, Preview>; onOpen: () => void
}) {
  const { box, visible } = useVisible<HTMLButtonElement>()
  const { view, failed } = usePreview(side === 'old' ? -1 : index, sources, previews, visible)
  const background = side === 'old' ? view?.before : view?.after
  const label = side === 'old' ? `옛 ${index + 1}쪽` : `새 ${index + 1}쪽`
  const words = side === 'new' && kind === 'new' ? '새로 생긴 쪽' : KIND_WORDS[kind]
  const attrs = side === 'old' ? { 'data-old': index } : { 'data-new': index }
  return (
    <button className={`link-tile ${kind}`} ref={box} onClick={onOpen} aria-label={`${label} 크게 보기`} {...attrs}>
      <span className="sheet-of-paper">
        {background ? (
          <>
            <img src={background} alt="" />
            {sources.length > 0 && view?.ink && <img className="ink" src={view.ink} alt="" aria-hidden />}
          </>
        ) : (
          <span className="placeholder t-caption">{failed ? '미리보기를 만들지 못했습니다' : ''}</span>
        )}
      </span>
      <span className="page-caption">
        <span className="t-caption">{label}</span>
        {words && <span className={`badge ${kind}`}>{words}</span>}
      </span>
    </button>
  )
}

// 크게 보기 — 옛 쪽(옛 필기 그대로)과 새 쪽(옮긴 필기)을 크게 나란히. 여러 옛 쪽이 한 새 쪽에 모이면 옛 쪽마다 고친다.
// Mac 의 Quick Look 자리. 넘기기는 화면 단추로 한다(키보드 단축키를 두지 않는다 — 닫는 Esc 만).
function PageViewer({ slots, at, context, previews, thumbnails, targetCount, closest, onMove, onClose, onPick, onMark }: {
  slots: Slot[]; at: number; context: Context; previews: Map<string, Preview>; thumbnails: Map<number, string>
  targetCount: number; closest: Record<number, number>; onMove: (at: number) => void; onClose: () => void
  onPick: (source: number, target: number) => void; onMark: (source: number, mark: Mark) => void
}) {
  const slot = slots[at]
  const kind = kindOf(slot, context)
  const t = slot.target_index
  const olds = sourcesOf(slot)
  const feeding = live(slot, context.marks)
  const [picking, setPicking] = useState<number | null>(null)
  const dialog = useRef<HTMLDivElement>(null)
  useEffect(() => { dialog.current?.focus() }, [])
  useEffect(() => { setPicking(null) }, [at])
  const moved = usePreview(t ?? -1, feeding, previews, t !== null)
  const title = t === null ? `옛 ${olds[0] + 1}쪽` : olds.length ? `새 ${t + 1}쪽 · 옛 ${olds.map((s) => s + 1).join('·')}쪽 필기` : `새 ${t + 1}쪽`
  return (
    <div className="viewer-backdrop" role="dialog" aria-modal="true" aria-label={title}
      onKeyDown={(event) => { if (event.key === 'Escape') onClose() }}>
      <div className="viewer" ref={dialog} tabIndex={-1}>
        <div className="viewer-head">
          <div className="viewer-title">
            <span className="t-title">{title}</span>
            {KIND_WORDS[kind] && <span className={`badge ${kind}`}>{KIND_WORDS[kind]}</span>}
          </div>
          <span className="t-caption">{at + 1} / {slots.length}</span>
          <button className="button quiet" onClick={onClose}>닫기</button>
        </div>
        <div className={`viewer-pages${olds.length > 1 ? ' many' : ''}`}>
          {olds.length > 0 && (
            <div className="viewer-olds">
              {olds.map((s) => (
                <OldPage key={s} source={s} kind={oldKind(s, slot, context)} previews={previews} many={olds.length > 1}
                  onPick={() => setPicking((now) => (now === s ? null : s))} onMark={(mark) => onMark(s, mark)} />
              ))}
            </div>
          )}
          {t !== null && (
            <Page label={feeding.length === 0 ? `새 ${t + 1}쪽 · 필기 없음` : `새 ${t + 1}쪽 · 필기를 얹은 모습`}
              background={moved.view?.after} ink={feeding.length === 0 ? undefined : moved.view?.ink} failed={moved.failed} />
          )}
        </div>
        <div className="viewer-foot">
          <div className="actions">
            {olds.length === 0 && <span className="t-caption">새 PDF에서 새로 생긴 쪽입니다. 얹을 옛 필기가 없습니다.</span>}
            {olds.length === 1 && (
              <SourceActions kind={oldKind(olds[0], slot, context)} target={t}
                onPick={() => setPicking((now) => (now === null ? olds[0] : null))} onMark={(mark) => onMark(olds[0], mark)} />
            )}
          </div>
          <div className="actions">
            <button className="button quiet" disabled={at === 0} onClick={() => onMove(at - 1)}>이전</button>
            <button className="button quiet" disabled={at === slots.length - 1} onClick={() => onMove(at + 1)}>다음</button>
          </div>
        </div>
        {picking !== null && (
          <TargetPicker count={targetCount} current={t} start={t ?? closest[picking] ?? null} similar={closest[picking]}
            thumbnails={thumbnails} onPick={(target) => { const s = picking; setPicking(null); onPick(s, target) }}
            onClose={() => setPicking(null)} />
        )}
      </div>
    </div>
  )
}

function SourceActions({ kind, target, onPick, onMark }: {
  kind: PageKind; target: number | null; onPick: () => void; onMark: (mark: Mark) => void
}) {
  if (kind === 'excluded') return <button className="button" onClick={() => onMark('open')}>다시 넣기</button>
  return (
    <>
      {kind === 'watch' && <button className="button" onClick={() => onMark('ok')}>{target === null ? '남기기' : '맞아요'}</button>}
      <button className="button quiet" onClick={onPick}>다른 쪽</button>
      <button className="button quiet" onClick={() => onMark('excluded')}>빼기</button>
    </>
  )
}

// 크게 보기의 옛 쪽 하나. 여러 옛 쪽이 모인 새 쪽이면 옛 쪽마다 `다른 쪽`·`빼기` 를 단다.
function OldPage({ source, kind, previews, many, onPick, onMark }: {
  source: number; kind: PageKind; previews: Map<string, Preview>; many: boolean
  onPick: () => void; onMark: (mark: Mark) => void
}) {
  const old = usePreview(-1, [source], previews, true)
  return (
    <div className={`viewer-old${kind === 'excluded' ? ' off' : ''}`}>
      <Page label={`옛 ${source + 1}쪽${kind === 'excluded' ? ' · 뺐습니다' : ''}`} background={old.view?.before}
        ink={old.view?.ink} failed={old.failed} />
      {many && <div className="actions"><SourceActions kind={kind} target={0} onPick={onPick} onMark={onMark} /></div>}
    </div>
  )
}
