// 서버와 말하는 층. 데스크톱 창(pywebview 의 Python 호출)과 웹(HTTP)의 차이는 **여기서만** 갈린다
// (명세 2026-09-24-01 「제약」). 화면은 `Backend` 하나만 안다.

import type { Doc, Ref } from './merging'
import type { Review } from './reasons'

export interface Held {
  name: string
  path?: string       // 데스크톱: 디스크 경로
  file?: File         // 웹: 브라우저가 준 파일
}

export interface Analysis {
  state: 'waiting' | 'running' | 'ready' | 'error'
  stage: string
  message: string
  error: string | null
}

export interface PlanSlot {
  source_index: number | null
  target_index: number | null
  confirmed: boolean
  merged?: number[]      // 이 새 쪽에 함께 얹는 옛 쪽(명세 2026-09-25-03)
}

export interface HandwritingStatus {
  ready: boolean
  source_name: string | null
  target_name: string | null
  analysis: Analysis
  inspection: {
    plan: { slots: PlanSlot[]; excluded_sources?: number[]; source_count?: number; target_count?: number } | null
    relocated_targets?: number[]
  } | null
  review: Review | null
}

export interface Preview {
  before: string        // 옛 배경(새 쪽 자리에 맞춘 것) — 그림 주소
  after: string         // 새 쪽
  ink: string           // 손필기만 그린 투명 그림
}

// 저장할 때 보내는 쪽 대응 한 줄(riffle/page_plan.py 의 PagePlan.from_payload 가 받는다).
export interface PlanRow {
  source_index: number | null
  target_index: number | null
  merged?: number[]
  confirmed: boolean
  excluded: boolean
}

export interface Saved {
  saved: boolean
  name?: string
  path?: string          // 데스크톱만 — 폴더 열기에 쓴다
  warnings?: string[]
}

export interface Backend {
  runtime: 'desktop' | 'web'
  health(): Promise<{ version: string }>
  logError(message: string): Promise<void>
  // 데스크톱은 파일 고르기 창을 띄워 경로를 받는다. 웹은 화면이 <input type=file> 로 고른다.
  pickFiles?(): Promise<Held[]>
  startHandwriting(source: Held, target: Held, progress?: (share: number) => void): Promise<void>
  // 합칠 PDF 를 올린다(더 놓아도 같은 입구). 지금까지 올린 문서 전부를 돌려준다.
  startMerge(pdfs: Held[], progress?: (share: number) => void): Promise<Doc[]>
  removeDocument(id: string): Promise<void>
  // signal: 화면이 사라지면 거둔다 — 비운 뒤에 도착한 요청이 실패로 기록되지 않게.
  pageImage(id: string, page: number, kind: 'thumbnail' | 'preview', signal?: AbortSignal): Promise<string>
  // `1-3, 5, 8-` 같은 범위 글 → 쪽 번호(0부터). 규칙은 서버 한 곳(riffle/ranges.py)에만 있다.
  parseRange(text: string, pageCount: number): Promise<number[]>
  saveMerge(order: Ref[], name: string): Promise<Saved>
  handwritingStatus(): Promise<HandwritingStatus>
  retryHandwriting(): Promise<void>
  // 새 쪽(targetIndex)에 옛 쪽(sources)의 손필기를 얹어 본다. 새 쪽이 없으면 -1(옛 쪽 하나를 그대로), 옛 쪽이
  // 없으면 -1. 여러 옛 쪽을 한 새 쪽에 모아 볼 때는 목록(대표가 맨 앞).
  preview(targetIndex: number, sources: number | number[], signal?: AbortSignal): Promise<Preview>
  saveHandwriting(name: string, plan: PlanRow[], allowUnconfirmed: boolean): Promise<Saved>
  openFolder?(path: string): Promise<void>
  reset(): Promise<void>
  // 데스크톱 창은 제목 표시줄이 없다 — 창 단추를 화면이 그린다(명세 2026-09-25-03).
  window?: { minimize(): Promise<void>; toggleMaximize(): Promise<void>; close(): Promise<void> }
}

interface Reply { ok: boolean; error?: string; [key: string]: unknown }

function unwrap<T extends Reply>(reply: T): T {
  if (!reply || !reply.ok) throw new Error(reply?.error || '앱이 응답하지 않았습니다. Riffle을 다시 실행해 주세요.')
  return reply
}

// --- 데스크톱 창 -----------------------------------------------------------------------------------

type PyApi = Record<string, (...args: unknown[]) => Promise<Reply>>

declare global {
  interface Window {
    pywebview?: { api: PyApi }
    // 창에 놓은 파일의 경로는 Python 이 이 함수로 밀어 준다(브라우저는 경로를 알려 주지 않는다).
    __riffleDropped?: (files: { name: string; path: string }[]) => void
  }
}

function pywebviewReady(): Promise<PyApi> {
  if (window.pywebview?.api) return Promise.resolve(window.pywebview.api)
  return new Promise((resolve) => {
    window.addEventListener('pywebviewready', () => resolve(window.pywebview!.api), { once: true })
  })
}

function desktop(): Backend {
  const call = async (method: string, ...args: unknown[]) => {
    const api = await pywebviewReady()
    if (typeof api[method] !== 'function') throw new Error(`앱 기능을 찾지 못했습니다: ${method}. Riffle을 다시 설치해 주세요.`)
    return unwrap(await api[method](...args))
  }
  return {
    runtime: 'desktop',
    async health() { return (await call('health')) as unknown as { version: string } },
    async logError(message) { await call('log_client_error', message) },
    async pickFiles() {
      const reply = await call('choose_files')
      return (reply.files as { name: string; path: string }[]) ?? []
    },
    async startHandwriting(source, target) {
      await call('set_handwriting_source_path', source.path)
      await call('set_handwriting_target_path', target.path)
    },
    async startMerge(pdfs) {
      const reply = await call('add_paths', pdfs.map((pdf) => pdf.path))
      return reply.sources as Doc[]
    },
    async removeDocument(id) { await call('remove_document', id) },
    async pageImage(id, page, kind) { return (await call('page_image', id, page, kind)).image as string },
    async parseRange(text, pageCount) { return (await call('parse_range', text, pageCount)).indices as number[] },
    async saveMerge(order, name) {
      const reply = await call('save_result', order, name)
      if (reply.cancelled) return { saved: false }
      const result = reply.result as { path: string; warnings?: string[] }
      return { saved: true, path: result.path, name: result.path.split(/[\\/]/).pop(), warnings: result.warnings }
    },
    async handwritingStatus() { return (await call('handwriting_status')) as unknown as HandwritingStatus },
    async retryHandwriting() { await call('retry_handwriting_analysis') },
    async preview(targetIndex, sources) {
      const list = Array.isArray(sources) ? sources : null
      return (await call('handwriting_preview', targetIndex, list ? (list[0] ?? -1) : sources, '',
                          list ? list.join(',') : '')) as unknown as Preview
    },
    async saveHandwriting(name, plan, allowUnconfirmed) {
      const reply = await call('save_handwriting_transfer', name, plan, allowUnconfirmed)
      if (reply.cancelled) return { saved: false }
      const result = reply.result as { path: string; warnings?: string[] }
      return { saved: true, path: result.path, name: result.path.split(/[\\/]/).pop(), warnings: result.warnings }
    },
    async openFolder(path) { await call('open_folder', path) },
    window: {
      async minimize() { await call('window_minimize') },
      async toggleMaximize() { await call('window_toggle_maximize') },
      async close() { await call('window_close') },
    },
    async reset() {
      await call('reset_handwriting_transfer')
      await call('reset_documents')
    },
  }
}

// 내려받은 파일 이름 — 서버가 Content-Disposition 에 한글 이름을 filename* 로 싣는다.
function downloadName(header: string | null, fallback: string): string {
  const encoded = header?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) return decodeURIComponent(encoded)
  return header?.match(/filename="?([^";]+)"?/i)?.[1] ?? fallback
}

// --- 웹 ---------------------------------------------------------------------------------------------

async function json(url: string, init?: RequestInit): Promise<Reply> {
  const response = await fetch(url, init)
  let reply: Reply
  try { reply = await response.json() } catch { reply = { ok: false, error: `서버 응답을 읽지 못했습니다(${response.status}).` } }
  return unwrap(reply)
}

// 올리는 동안 진행 막대를 채우려면 fetch 가 아니라 XMLHttpRequest 가 필요하다(올림 진행을 알려 준다).
function upload(url: string, form: FormData, progress?: (share: number) => void): Promise<Reply> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('POST', url)
    request.responseType = 'json'
    request.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) progress?.(event.loaded / event.total)
    })
    request.addEventListener('load', () => {
      try { resolve(unwrap(request.response ?? { ok: false, error: `올리지 못했습니다(${request.status}).` })) }
      catch (error) { reject(error) }
    })
    request.addEventListener('error', () => reject(new Error('서버에 닿지 못했습니다. 연결을 확인해 주세요.')))
    request.send(form)
  })
}

// 결과 파일을 만들어 곧바로 내려받는다(웹). 서버가 거절하면 그 사유를 그대로 올린다.
async function download(url: string, body: unknown, fallback: string): Promise<Saved> {
  const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!response.ok) {
    let message = `저장하지 못했습니다(${response.status}).`
    try { message = (await response.json()).error || message } catch { /* 본문이 JSON 이 아니다 */ }
    throw new Error(message)
  }
  const fileName = downloadName(response.headers.get('Content-Disposition'), fallback)
  const link = document.createElement('a')
  link.href = URL.createObjectURL(await response.blob())
  link.download = fileName
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(link.href), 60_000)
  let warnings: string[] = []
  try { warnings = JSON.parse(decodeURIComponent(response.headers.get('X-Riffle-Warnings') || '[]')) } catch { /* 없으면 없는 대로 */ }
  return { saved: true, name: fileName, warnings }
}

function web(): Backend {
  return {
    runtime: 'web',
    async health() { return (await json('/api/health')) as unknown as { version: string } },
    async logError(message) {
      await json('/api/client-error', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ message }) })
    },
    async startHandwriting(source, target, progress) {
      const total = (source.file?.size ?? 0) + (target.file?.size ?? 0) || 1
      const sourceForm = new FormData()
      sourceForm.append('file', source.file!, source.name)
      await upload('/api/handwriting/source', sourceForm, (share) => progress?.(share * (source.file?.size ?? 0) / total))
      const targetForm = new FormData()
      targetForm.append('file', target.file!, target.name)
      const done = (source.file?.size ?? 0) / total
      await upload('/api/handwriting/target', targetForm, (share) => progress?.(done + share * (1 - done)))
    },
    async startMerge(pdfs, progress) {
      const form = new FormData()
      pdfs.forEach((pdf) => form.append('files', pdf.file!, pdf.name))
      return (await upload('/api/documents', form, progress)).sources as Doc[]
    },
    async removeDocument(id) { await json(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }) },
    async pageImage(id, page, kind, signal) {
      return (await json(`/api/documents/${encodeURIComponent(id)}/pages/${page}?kind=${kind}`, { signal })).image as string
    },
    async parseRange(text, pageCount) {
      const reply = await json('/api/ranges', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: text, page_count: pageCount }),
      })
      return reply.indices as number[]
    },
    async saveMerge(order, name) {
      return download('/api/documents/export', { order, suggested_name: name }, name)
    },
    async handwritingStatus() { return (await json('/api/handwriting/status')) as unknown as HandwritingStatus },
    async retryHandwriting() { await json('/api/handwriting/retry', { method: 'POST' }) },
    async preview(targetIndex, sources, signal) {
      const list = Array.isArray(sources) ? sources : null
      const query = new URLSearchParams({ page_index: String(targetIndex),
                                          source_index: String(list ? (list[0] ?? -1) : sources) })
      if (list) query.set('sources', list.join(','))
      return (await json(`/api/handwriting/preview?${query}`, { signal })) as unknown as Preview
    },
    async saveHandwriting(name, plan, allowUnconfirmed) {
      return download('/api/handwriting/export',
        { suggested_name: name, page_plan: plan, allow_unconfirmed: allowUnconfirmed }, name)
    },
    async reset() {
      await json('/api/handwriting/reset', { method: 'POST' })
      await json('/api/documents/reset', { method: 'POST' })
    },
  }
}

// 데스크톱 창은 `#desktop` 을 붙여 연다(riffle/app.py). 그 밖은 웹이다.
export const backend: Backend = window.location.hash === '#desktop' ? desktop() : web()
