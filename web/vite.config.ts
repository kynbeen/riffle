import { createHash } from 'node:crypto'
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// 새 화면(명세 2026-09-24-01). Sleek 과 같은 방식이다.
// 빌드 결과는 `riffle/ui/` 에 두고 저장소에 커밋한다 — 앱을 쓰는 PC 에는 Node 가 없다.
// 개발 중에는 `npm run dev` 가 /api 를 켜 둔 웹 서버(`python -m riffle.web`, 8000)로 넘긴다.

// 커밋된 빌드가 지금 소스로 만든 것인지 테스트가 확인할 수 있게 소스 해시를 남긴다(tests/test_new_ui.py).
// 줄끝은 LF 로 맞춰 센다 — Windows 에서 받으면 git 이 CRLF 로 바꿔 놓는다.
export const SOURCES = ['src', 'public', 'index.html', 'package.json', 'vite.config.ts', 'tsconfig.json']
const OUT_DIR = join(__dirname, '..', 'riffle', 'ui')

function files(root: string, entry: string): string[] {
  const path = join(root, entry)
  try {
    return readdirSync(path, { withFileTypes: true })
      .flatMap((item) => files(root, relative(root, join(path, item.name))))
  } catch {
    return [entry.replaceAll('\\', '/')]
  }
}

function sourceHash(): Plugin {
  return {
    name: 'source-hash',
    closeBundle() {
      const root = __dirname
      const hash = createHash('sha256')
      for (const file of SOURCES.flatMap((entry) => files(root, entry)).sort()) {
        hash.update(file + '\n')
        // 바이트 단위로 CRLF 만 LF 로 — 아이콘 같은 이진 파일도 글자로 읽다 깨지지 않게.
        const bytes = readFileSync(join(root, file))
        hash.update(Buffer.from(bytes.toString('latin1').replaceAll('\r\n', '\n'), 'latin1'))
      }
      writeFileSync(join(OUT_DIR, 'source-hash.txt'), hash.digest('hex') + '\n')
    },
  }
}

export default defineConfig({
  plugins: [react(), sourceHash()],
  // 상대 경로 — 데스크톱 창은 파일로, 웹은 옮겨 가는 동안 /new/ 아래에서 연다.
  base: './',
  build: { outDir: OUT_DIR, emptyOutDir: true, assetsDir: 'assets', chunkSizeWarningLimit: 1500 },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
