import { useCallback, useEffect, useRef, useState } from 'react'
import { backend, type Held, type Saved } from './api'
import { kindOf } from './classify'
import { formatRanges, isDefault, key, move, syncOrder, defaultOrder, type Doc, type Ref } from './merging'

// 문서 합치기(명세 2026-09-24-01). 기본은 모든 쪽을 놓은 순서로 — 고르지 않으면 그대로 이어 붙인다(원칙 4).

type Thumbs = Map<string, string>

export default function Merge({ initial }: { initial: Doc[] }) {
  const [docs, setDocs] = useState<Doc[]>(initial)
  const [selected, setSelected] = useState<Set<string>>(() => new Set(defaultOrder(initial, allKeys(initial)).map(key)))
  const [order, setOrder] = useState<Ref[]>(() => defaultOrder(initial, allKeys(initial)))
  const [handmade, setHandmade] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState<Saved | null>(null)
  const thumbs = useRef<Thumbs>(new Map())
  const input = useRef<HTMLInputElement>(null)

  const choose = (next: Set<string>, nextDocs = docs) => {
    setSelected(next)
    setOrder((prev) => syncOrder(prev, nextDocs, next, handmade))
    setSaved(null)
  }

  const add = useCallback(async (files: Held[]) => {
    const pdfs = files.filter((file) => kindOf(file.name) === 'pdf')
    if (!pdfs.length) { setError('합칠 수 있는 것은 PDF 뿐입니다.'); return }
    setBusy('여는 중')
    setError('')
    try {
      const all = await backend.startMerge(pdfs)
      const known = new Set(docs.map((doc) => doc.id))
      const added = all.filter((doc) => !known.has(doc.id))
      const next = new Set(selected)
      for (const doc of added) for (const page of doc.pages) next.add(`${doc.id}:${page.index}`)
      setDocs(all)
      choose(next, all)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy('')
    }
  }, [docs, selected, handmade])

  // 문서를 더 놓으면 목록 끝에 붙는다.
  useEffect(() => {
    const over = (event: DragEvent) => event.preventDefault()
    const drop = (event: DragEvent) => {
      event.preventDefault()
      if (backend.runtime === 'desktop') return
      void add(Array.from(event.dataTransfer?.files ?? []).map((file) => ({ name: file.name, file })))
    }
    window.addEventListener('dragover', over)
    window.addEventListener('drop', drop)
    window.__riffleDropped = (files) => { void add(files) }
    return () => {
      window.removeEventListener('dragover', over)
      window.removeEventListener('drop', drop)
      window.__riffleDropped = undefined
    }
  }, [add])

  const remove = async (doc: Doc) => {
    try {
      await backend.removeDocument(doc.id)
      const nextDocs = docs.filter((other) => other.id !== doc.id)
      const next = new Set([...selected].filter((item) => !item.startsWith(`${doc.id}:`)))
      setDocs(nextDocs)
      setSelected(next)
      setOrder((prev) => prev.filter((ref) => ref.document_id !== doc.id))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const reorder = (from: number, to: number) => {
    setOrder((prev) => move(prev, from, to))
    setHandmade(true)
    setSaved(null)
  }

  const save = async () => {
    setBusy('저장하는 중')
    setError('')
    try {
      const first = docs.find((doc) => doc.id === order[0]?.document_id)
      const name = `${(first?.name ?? '합친 문서').replace(/\.pdf$/i, '')}-편집본.pdf`
      const result = await backend.saveMerge(order, name)
      if (result.saved) setSaved(result)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy('')
    }
  }

  const pickMore = async () => {
    if (backend.pickFiles) {
      try { await add(await backend.pickFiles()) } catch (err) { setError((err as Error).message) }
    } else {
      input.current?.click()
    }
  }

  return (
    <section className="panel wide">
      <div className="merge-head">
        <div className="t-title">문서 합치기 · {docs.length}개 문서</div>
        <button className="button quiet" onClick={pickMore} disabled={Boolean(busy)}>PDF 더하기</button>
        <input ref={input} type="file" multiple hidden accept=".pdf" onChange={(event) => {
          const files = Array.from(event.target.files ?? [])
          event.target.value = ''
          void add(files.map((file) => ({ name: file.name, file })))
        }} />
      </div>

      {docs.map((doc) => (
        <DocumentRow key={doc.id} doc={doc} selected={selected} thumbs={thumbs.current}
          onToggle={(page) => {
            const next = new Set(selected)
            const item = `${doc.id}:${page}`
            if (next.has(item)) next.delete(item); else next.add(item)
            choose(next)
          }}
          onRange={(indices) => {
            const next = new Set([...selected].filter((item) => !item.startsWith(`${doc.id}:`)))
            indices.forEach((index) => next.add(`${doc.id}:${index}`))
            choose(next)
          }}
          onRemove={() => void remove(doc)} />
      ))}

      <div className="result-head">
        <div className="t-title">결과 {order.length}쪽</div>
        {!isDefault(order, docs) && (
          <button className="button quiet" onClick={() => { setOrder(defaultOrder(docs, selected)); setHandmade(false) }}>
            순서 되돌리기
          </button>
        )}
      </div>
      <ResultStrip order={order} docs={docs} thumbs={thumbs.current} onMove={reorder} />

      {error && <div className="message error t-body">{error}</div>}
      {saved ? (
        <div className="saved">
          <div className="t-body"><b>저장했습니다</b>{saved.name ? ` · ${saved.name}` : ''}</div>
          <div className="t-caption">{`${docs.length}개 문서에서 ${order.length}쪽`}</div>
          {(saved.warnings ?? []).map((warning) => <div className="t-caption" key={warning}>{warning}</div>)}
          {saved.path && backend.openFolder && (
            <div><button className="button quiet" onClick={() => backend.openFolder!(saved.path!)}>폴더 열기</button></div>
          )}
        </div>
      ) : (
        <div className="savebar">
          {busy && <span className="t-caption">{busy}</span>}
          <button className="button" disabled={Boolean(busy) || order.length === 0} onClick={() => void save()}>PDF로 저장</button>
        </div>
      )}
    </section>
  )
}

function allKeys(docs: Doc[]): Set<string> {
  return new Set(docs.flatMap((doc) => doc.pages.map((page) => `${doc.id}:${page.index}`)))
}

function DocumentRow({ doc, selected, thumbs, onToggle, onRange, onRemove }: {
  doc: Doc; selected: Set<string>; thumbs: Thumbs
  onToggle: (page: number) => void; onRange: (indices: number[]) => void; onRemove: () => void
}) {
  const chosen = doc.pages.filter((page) => selected.has(`${doc.id}:${page.index}`)).map((page) => page.index)
  const shown = formatRanges(chosen, doc.page_count)
  const [text, setText] = useState(shown)
  const [problem, setProblem] = useState('')
  const [editing, setEditing] = useState(false)
  useEffect(() => { if (!editing) setText(shown) }, [shown, editing])

  const apply = async () => {
    setEditing(false)
    const value = text.trim()
    if (value === shown) return
    try {
      const indices = value === '' ? [] : value === '전체'
        ? doc.pages.map((page) => page.index)
        : await backend.parseRange(value, doc.page_count)
      setProblem('')
      onRange(indices)
    } catch (err) {
      setProblem((err as Error).message)
    }
  }

  return (
    <div className="doc">
      <div className="doc-head">
        <b className="t-body doc-name">{doc.name}</b>
        <label className="range t-caption">
          쪽
          <input value={text} placeholder="고른 쪽 없음" aria-label={`${doc.name} 쪽 범위`}
            onFocus={() => setEditing(true)} onChange={(event) => setText(event.target.value)}
            onBlur={() => void apply()} onKeyDown={(event) => { if (event.key === 'Enter') (event.target as HTMLInputElement).blur() }} />
        </label>
        <button className="back" onClick={onRemove} aria-label={`${doc.name} 빼기`}>빼기</button>
      </div>
      {problem && <div className="message error t-caption">{problem}</div>}
      <Strip items={doc.pages.map((page) => ({ id: doc.id, page: page.index, ratio: page.width / page.height,
                                                on: selected.has(`${doc.id}:${page.index}`) }))}
        thumbs={thumbs} onClick={(item) => onToggle(item.page)} label={(item) => `${item.page + 1}`} />
    </div>
  )
}

interface StripItem { id: string; page: number; ratio: number; on?: boolean }

// 쪽 그림 줄. 그림은 보일 때만 불러온다(쪽이 수백 개여도 가볍게).
function Strip({ items, thumbs, onClick, label, draggable, onMove, controls }: {
  items: StripItem[]; thumbs: Thumbs; onClick?: (item: StripItem) => void; label: (item: StripItem, index: number) => string
  draggable?: boolean; onMove?: (from: number, to: number) => void; controls?: boolean
}) {
  const root = useRef<HTMLDivElement>(null)
  const [, redraw] = useState(0)
  const dragging = useRef<number | null>(null)
  useEffect(() => {
    const element = root.current
    if (!element) return
    const stop = new AbortController()
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const node = entry.target as HTMLElement
        const name = `${node.dataset.id}:${node.dataset.page}`
        observer.unobserve(node)
        if (thumbs.has(name)) continue
        backend.pageImage(node.dataset.id!, Number(node.dataset.page), 'thumbnail', stop.signal)
          .then((image) => { thumbs.set(name, image); redraw((n) => n + 1) }).catch(() => {})
      }
    }, { root: element, rootMargin: '0px 600px' })
    element.querySelectorAll('[data-page]').forEach((node) => observer.observe(node))
    return () => { observer.disconnect(); stop.abort() }
  }, [items, thumbs])
  return (
    <div className="strip merge-strip" ref={root}>
      {items.map((item, index) => {
        const image = thumbs.get(`${item.id}:${item.page}`)
        return (
          <div key={`${item.id}:${item.page}:${index}`} className={`tile${item.on === false ? ' off' : ''}`}
            data-id={item.id} data-page={item.page} draggable={draggable}
            onDragStart={() => { dragging.current = index }}
            onDragOver={(event) => { if (draggable) event.preventDefault() }}
            onDrop={(event) => {
              event.preventDefault()
              event.stopPropagation()
              if (dragging.current !== null) onMove?.(dragging.current, index)
              dragging.current = null
            }}>
            <button className="tile-face" onClick={() => onClick?.(item)} aria-pressed={item.on}
              aria-label={label(item, index)}>
              {image
                ? <img src={image} alt="" draggable={false} />
                : <span className="thumb-empty" style={{ aspectRatio: String(item.ratio || 4 / 3) }} />}
            </button>
            <span className="t-caption tile-label">{label(item, index)}</span>
            {controls && (
              <span className="tile-move">
                <button className="mini" aria-label="앞으로" disabled={index === 0} onClick={() => onMove?.(index, index - 1)}>‹</button>
                <button className="mini" aria-label="뒤로" disabled={index === items.length - 1} onClick={() => onMove?.(index, index + 1)}>›</button>
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function ResultStrip({ order, docs, thumbs, onMove }: {
  order: Ref[]; docs: Doc[]; thumbs: Thumbs; onMove: (from: number, to: number) => void
}) {
  if (!order.length) return <div className="note t-body">고른 쪽이 없습니다. 위에서 쪽을 눌러 고르세요.</div>
  const names = new Map(docs.map((doc, index) => [doc.id, { index, doc }]))
  const items = order.map((ref) => {
    const page = names.get(ref.document_id)?.doc.pages[ref.page_index]
    return { id: ref.document_id, page: ref.page_index, ratio: page ? page.width / page.height : 4 / 3 }
  })
  return (
    <Strip items={items} thumbs={thumbs} draggable controls onMove={onMove}
      label={(item) => `${docs.length > 1 ? `${(names.get(item.id)?.index ?? 0) + 1}번 문서 ` : ''}${item.page + 1}쪽`} />
  )
}
