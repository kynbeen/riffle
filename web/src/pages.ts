// 모든 쪽 보기 — 결과의 쪽마다 무엇인지 가른다(명세 2026-09-25-01 단위 3). 화면과 떨어진 순수 함수라 node 로 시험한다.
// 격자의 표시·걸러 보기·요약 숫자가 모두 여기서 나온다 — 같은 것을 두 곳에서 세면 어긋난다(원칙 8).

import type { Slot } from './plan.ts'

export type Mark = 'open' | 'ok' | 'excluded'

export type PageKind =
  | 'auto'        // 기계가 자신 있게 맞춤 — 표시 없음
  | 'moved'       // 새 판에서 순서가 바뀌어 다시 짝지음
  | 'merged'      // 옛 쪽 여럿의 필기를 이 새 쪽 하나에 모음(필기본 반복 수가 줄어서)
  | 'relocated'   // 필기 칸에 쓴 손필기를 새 칸의 빈자리로 옮김
  | 'new'         // 새로 생긴 쪽 — 필기 없이 들어감
  | 'kept'        // 새 PDF에 없는 옛 쪽 — 옛 쪽째 남김
  | 'kept_blank'  // 그중 필기가 없는 쪽
  | 'watch'       // 아직 안 본 카드
  | 'checked'     // 카드를 봄
  | 'chosen'      // 사람이 직접 짝을 고름
  | 'excluded'    // 사람이 뺌 — 원래 자리에 접힌 줄로

export interface Context {
  reasons: Record<number, unknown>
  marks: Record<number, Mark>
  chosen: Set<number>
  blank: Set<number>
  moved: Set<number>
  relocated?: Set<number>      // 칸 손필기를 여백으로 옮긴 새 쪽
}

export function kindOf(slot: Slot, context: Context): PageKind {
  const s = slot.source_index
  if (s === null) return 'new'
  // 사람이 뺀 쪽·직접 고른 짝은 카드에 올랐든 아니든(모든 쪽 보기에서 고친 것) 사람 쪽이 이긴다(원칙 7).
  if (context.marks[s] === 'excluded') return 'excluded'
  if (context.chosen.has(s)) return 'chosen'
  if (s in context.reasons) {
    const mark = context.marks[s]
    if (mark === 'ok') return slot.target_index === null ? (context.blank.has(s) ? 'kept_blank' : 'kept') : 'checked'
    return 'watch'
  }
  if (slot.target_index === null) return context.blank.has(s) ? 'kept_blank' : 'kept'
  if (context.moved.has(s)) return 'moved'
  if (slot.merged?.length) return 'merged'
  return context.relocated?.has(slot.target_index) ? 'relocated' : 'auto'
}

// 연결 보기의 옛 쪽 하나. 함께 얹힌 옛 쪽을 따로 뺄 수 있다 — 그 옛 쪽만 `뺐습니다`.
export function oldKind(source: number, slot: Slot, context: Context): PageKind {
  if (context.marks[source] === 'excluded') return 'excluded'
  return kindOf(slot, context)
}

export const KIND_WORDS: Record<PageKind, string> = {
  auto: '',
  moved: '순서 바뀜',
  merged: '여러 쪽 모음',
  relocated: '칸 필기 옮김',
  new: '새로 생긴 쪽 · 필기 없음',
  kept: '옛 쪽째 남김',
  kept_blank: '옛 쪽째 남김 · 필기 없음',
  watch: '볼 쪽',
  checked: '확인함',
  chosen: '직접 고름',
  excluded: '뺐습니다',
}

// 걸러 보기. 요약 숫자가 곧 거르는 단추다 — 숫자가 0인 것은 단추도 없다.
export type Filter = 'all' | 'watch' | 'new' | 'kept' | 'moved' | 'merged' | 'relocated' | 'chosen' | 'excluded'

export const FILTER_WORDS: Record<Filter, string> = {
  all: '전체',
  watch: '볼 쪽',
  new: '새로 생긴 쪽',
  kept: '옛 쪽째 남김',
  moved: '순서 바뀜',
  merged: '여러 쪽 모음',
  relocated: '칸 필기 옮김',
  chosen: '직접 고친 쪽',
  excluded: '뺀 쪽',
}

export function matches(kind: PageKind, filter: Filter): boolean {
  if (filter === 'all') return true
  if (filter === 'kept') return kind === 'kept' || kind === 'kept_blank'
  return kind === filter
}

export function countFilters(kinds: PageKind[]): Record<Filter, number> {
  const filters = Object.keys(FILTER_WORDS) as Filter[]
  return Object.fromEntries(filters.map((filter) => [
    filter,
    filter === 'all' ? kinds.filter((kind) => kind !== 'excluded').length : kinds.filter((kind) => matches(kind, filter)).length,
  ])) as Record<Filter, number>
}
