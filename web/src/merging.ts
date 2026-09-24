// 문서 합치기의 선택·순서 규칙(명세 2026-09-24-01 「문서 합치기」). 화면과 떨어진 순수 함수라 node 로 시험한다.

export interface PageInfo { index: number; width: number; height: number }
export interface Doc { id: string; name: string; page_count: number; pages: PageInfo[] }
export interface Ref { document_id: string; page_index: number }

export const key = (ref: Ref) => `${ref.document_id}:${ref.page_index}`

// 기본 순서: 놓은 문서 순서, 그 안에서는 쪽 번호 순서.
export function defaultOrder(docs: Doc[], selected: Set<string>): Ref[] {
  const order: Ref[] = []
  for (const doc of docs) {
    for (const page of doc.pages) {
      const ref = { document_id: doc.id, page_index: page.index }
      if (selected.has(key(ref))) order.push(ref)
    }
  }
  return order
}

// 선택이 바뀌었을 때의 결과 순서. 사람이 순서를 손대지 않았으면 기본 순서 그대로,
// 손댔으면 그 순서를 지키고 — 빠진 쪽은 빼고, 새로 고른 쪽은 **같은 문서의 쪽들 곁에** 끼운다.
export function syncOrder(order: Ref[], docs: Doc[], selected: Set<string>, handmade: boolean): Ref[] {
  if (!handmade) return defaultOrder(docs, selected)
  const kept = order.filter((ref) => selected.has(key(ref)))
  const present = new Set(kept.map(key))
  for (const ref of defaultOrder(docs, selected)) {
    if (present.has(key(ref))) continue
    // 같은 문서에서 이 쪽보다 앞 번호인 쪽 중 마지막 것 바로 뒤, 없으면 같은 문서의 첫 쪽 앞, 그것도 없으면 끝.
    let at = -1
    kept.forEach((other, position) => {
      if (other.document_id === ref.document_id && other.page_index < ref.page_index) at = position + 1
    })
    if (at < 0) {
      const first = kept.findIndex((other) => other.document_id === ref.document_id)
      at = first >= 0 ? first : kept.length
    }
    kept.splice(at, 0, ref)
    present.add(key(ref))
  }
  return kept
}

export function move(order: Ref[], from: number, to: number): Ref[] {
  if (from === to || from < 0 || to < 0 || from >= order.length || to >= order.length) return order
  const next = [...order]
  const [ref] = next.splice(from, 1)
  next.splice(to, 0, ref)
  return next
}

// 고른 쪽(0부터)을 사람이 쓰는 범위 글로: [0,1,2,4,7,8,9] 10쪽 → "1-3, 5, 8-". 전부면 "전체", 없으면 "".
export function formatRanges(indices: number[], count: number): string {
  const sorted = [...new Set(indices)].sort((a, b) => a - b)
  if (!sorted.length) return ''
  if (sorted.length === count) return '전체'
  const parts: string[] = []
  let start = sorted[0]
  let previous = start
  for (const index of [...sorted.slice(1), Infinity]) {
    if (index === previous + 1) { previous = index; continue }
    if (start === previous) parts.push(String(start + 1))
    else if (previous === count - 1) parts.push(`${start + 1}-`)
    else parts.push(`${start + 1}-${previous + 1}`)
    start = previous = index
  }
  return parts.join(', ')
}

// 기본 순서와 같은가 — `순서 되돌리기` 는 다를 때만 보인다.
export function isDefault(order: Ref[], docs: Doc[]): boolean {
  const selected = new Set(order.map(key))
  const expected = defaultOrder(docs, selected)
  return expected.length === order.length && expected.every((ref, index) => key(ref) === key(order[index]))
}
