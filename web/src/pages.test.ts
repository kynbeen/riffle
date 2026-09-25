import assert from 'node:assert/strict'
import { test } from 'node:test'
import { countFilters, kindOf, matches, type Context } from './pages.ts'
import type { Slot } from './plan.ts'

const pair = (source: number | null, target: number | null): Slot => ({ source_index: source, target_index: target })

// 옛 0→새 0 자동 · 옛 1→새 2 순서 바뀜 · 새 1 새로 생김 · 옛 2 옛 쪽째(필기) · 옛 3 옛 쪽째(필기 없음) ·
// 옛 4→새 3 볼 쪽 · 옛 5→새 4 확인함 · 옛 6 뺌 · 옛 7→새 5 직접 고름
const slots = [pair(0, 0), pair(null, 1), pair(1, 2), pair(2, null), pair(3, null), pair(4, 3), pair(5, 4), pair(6, null), pair(7, 5)]
const context: Context = {
  reasons: { 4: 'different', 5: 'duplicate', 6: 'old_only', 7: 'old_only' },
  marks: { 4: 'open', 5: 'ok', 6: 'excluded', 7: 'ok' },
  chosen: new Set([7]),
  blank: new Set([3]),
  moved: new Set([1]),
}

test('쪽마다 무엇인지 하나로 가른다', () => {
  assert.deepEqual(slots.map((slot) => kindOf(slot, context)),
    ['auto', 'new', 'moved', 'kept', 'kept_blank', 'watch', 'checked', 'excluded', 'chosen'])
})

test('걸러 보기 숫자는 결과 쪽 수와 맞는다 — 뺀 쪽은 전체에 들지 않는다', () => {
  const counts = countFilters(slots.map((slot) => kindOf(slot, context)))
  assert.deepEqual(counts, { all: 8, watch: 1, new: 1, kept: 2, moved: 1, chosen: 1, excluded: 1 })
})

test('옛 쪽째 남김은 필기 없는 쪽도 함께 거른다', () => {
  assert.ok(matches('kept_blank', 'kept'))
  assert.ok(!matches('kept_blank', 'new'))
})

test('모든 쪽 보기에서 고친 자동 쪽도 사람 쪽 표시가 이긴다', () => {
  const edited = { ...context, marks: { ...context.marks, 0: 'excluded' as const }, chosen: new Set([7, 1]) }
  assert.equal(kindOf(pair(0, 0), edited), 'excluded')
  assert.equal(kindOf(pair(1, 2), edited), 'chosen')
})

test('카드에서 남기기로 정한 옛 쪽은 옛 쪽째 남김으로 센다', () => {
  assert.equal(kindOf(pair(6, null), { ...context, marks: { ...context.marks, 6: 'ok' } }), 'kept')
})
