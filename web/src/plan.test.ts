import assert from 'node:assert/strict'
import { test } from 'node:test'
import { nearTarget, reassign, targetOf, type Slot } from './plan.ts'

const pair = (source: number | null, target: number | null): Slot => ({ source_index: source, target_index: target })
const targets = (slots: Slot[]) => slots.map((slot) => slot.target_index).filter((t) => t !== null)

test('다른 쪽 띠는 옛 쪽 자리에서 가장 가까운 새 쪽에서 시작한다', () => {
  const slots = [pair(0, 0), pair(1, 1), pair(2, null), pair(null, 2), pair(3, 3)]
  assert.equal(nearTarget(slots, 2), 2)          // 앞뒤가 같은 거리면 뒤쪽 — 실측에서 순서가 바뀐 쪽은 뒤로 갔다
  assert.equal(nearTarget([pair(0, 0), pair(1, null), pair(2, null), pair(3, 3)], 2), 3)
  assert.equal(nearTarget([pair(0, null), pair(1, null), pair(null, 5)], 0), 5)
  assert.equal(nearTarget([pair(0, null)], 0), null)
})

test('짝을 바꿔도 새 쪽 순서는 그대로다', () => {
  const slots = [pair(0, 0), pair(1, 1), pair(2, 2), pair(3, 3)]
  const { slots: next, displaced } = reassign(slots, 1, 3)
  assert.deepEqual(targets(next), [0, 1, 2, 3])
  assert.equal(targetOf(next, 1), 3)
  assert.equal(displaced, 3)
  assert.deepEqual(next, [pair(0, 0), pair(null, 1), pair(2, 2), pair(1, 3), pair(3, null)])
})

test('밀려난 옛 쪽은 짝 없는 옛 쪽이 된다 — 조용히 다른 새 쪽으로 가지 않는다', () => {
  const { slots: next } = reassign([pair(0, 0), pair(1, 1)], 0, 1)
  assert.equal(targetOf(next, 1), null)
  assert.equal(targetOf(next, 0), 1)
})

test('짝 없던 옛 쪽을 새로 생긴 쪽에 얹으면 빈 줄이 남지 않는다', () => {
  const slots = [pair(0, 0), pair(1, null), pair(null, 1), pair(2, 2)]
  const { slots: next, displaced } = reassign(slots, 1, 1)
  assert.equal(displaced, null)
  assert.deepEqual(next, [pair(0, 0), pair(1, 1), pair(2, 2)])
})

test('모든 옛 쪽과 새 쪽이 정확히 한 번씩 남는다', () => {
  const slots = [pair(0, 0), pair(1, 1), pair(2, null), pair(null, 2), pair(3, 3)]
  const { slots: next } = reassign(reassign(slots, 3, 0).slots, 2, 3)
  const sources = next.map((slot) => slot.source_index).filter((s) => s !== null).sort()
  assert.deepEqual(sources, [0, 1, 2, 3])
  assert.deepEqual(targets(next), [0, 1, 2, 3])
})

test('같은 짝을 고르면 아무것도 바뀌지 않는다', () => {
  const slots = [pair(0, 0)]
  assert.equal(reassign(slots, 0, 0).slots, slots)
})
