// 서버와 말하는 층. 데스크톱 창(pywebview 의 Python 호출)과 웹(HTTP)의 차이는 **여기서만** 갈린다
// (명세 2026-09-24-01 「제약」). 화면은 `Backend` 하나만 안다.

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

export interface HandwritingStatus {
  ready: boolean
  source_name: string | null
  target_name: string | null
  analysis: Analysis
}

export interface Backend {
  runtime: 'desktop' | 'web'
  health(): Promise<{ version: string }>
  // 데스크톱은 파일 고르기 창을 띄워 경로를 받는다. 웹은 화면이 <input type=file> 로 고른다.
  pickFiles?(): Promise<Held[]>
  startHandwriting(source: Held, target: Held, progress?: (share: number) => void): Promise<void>
  startMerge(pdfs: Held[], progress?: (share: number) => void): Promise<void>
  handwritingStatus(): Promise<HandwritingStatus>
  retryHandwriting(): Promise<void>
  reset(): Promise<void>
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
    async pickFiles() {
      const reply = await call('choose_files')
      return (reply.files as { name: string; path: string }[]) ?? []
    },
    async startHandwriting(source, target) {
      await call('set_handwriting_source_path', source.path)
      await call('set_handwriting_target_path', target.path)
    },
    async startMerge(pdfs) { await call('add_paths', pdfs.map((pdf) => pdf.path)) },
    async handwritingStatus() { return (await call('handwriting_status')) as unknown as HandwritingStatus },
    async retryHandwriting() { await call('retry_handwriting_analysis') },
    async reset() {
      await call('reset_handwriting_transfer')
      await call('reset_documents')
    },
  }
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

function web(): Backend {
  return {
    runtime: 'web',
    async health() { return (await json('/api/health')) as unknown as { version: string } },
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
      await upload('/api/documents', form, progress)
    },
    async handwritingStatus() { return (await json('/api/handwriting/status')) as unknown as HandwritingStatus },
    async retryHandwriting() { await json('/api/handwriting/retry', { method: 'POST' }) },
    async reset() {
      await json('/api/handwriting/reset', { method: 'POST' })
      await json('/api/documents/reset', { method: 'POST' })
    },
  }
}

// 데스크톱 창은 `#desktop` 을 붙여 연다(riffle/app.py). 그 밖은 웹이다.
export const backend: Backend = window.location.hash === '#desktop' ? desktop() : web()
