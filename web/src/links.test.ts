import assert from 'node:assert/strict'
import { test } from 'node:test'
import { bands, links } from './links.ts'
import { reassign, toRows, withDropped, type Slot } from './plan.ts'

const pair = (source: number | null, target: number | null, merged?: number[]): Slot =>
  merged ? { source_index: source, target_index: target, merged } : { source_index: source, target_index: target }

test('반복 수가 줄면 옛 쪽 여럿이 한 줄에 모여 새 쪽 하나와 나란하다', () => {
  // 옛 1 2 2' 2'' 3 → 새 1 2 2' 3 (옛 1·2 가 새 1 로)
  const slots = [pair(0, 0), pair(1, 1, [2]), pair(3, 2), pair(4, 3)]
  assert.deepEqual(bands(slots, 5, 4), [
    { olds: [0], target: 0 }, { olds: [1, 2], target: 1 }, { olds: [3], target: 2 }, { olds: [4], target: 3 },
  ])
  assert.equal(links(slots).length, 5)
})

test('순서가 바뀐 쪽은 제 자리에 남고 선만 건너간다 — 두 띠 모두 제 순서다', () => {
  // 옛 0→새 0, 옛 1→새 2, 옛 2→새 1
  const slots = [pair(0, 0), pair(2, 1), pair(1, 2)]
  const laid = bands(slots, 3, 3)
  assert.deepEqual(laid.flatMap((band) => band.olds), [0, 1, 2])
  assert.deepEqual(laid.map((band) => band.target).filter((t) => t !== null), [0, 1, 2])
})

test('새로 생긴 쪽·빠진 옛 쪽도 제 순서의 자리에 한 줄씩', () => {
  const slots = [pair(0, 0), pair(null, 1), pair(1, null), pair(2, 2)]
  assert.deepEqual(bands(slots, 3, 3), [
    { olds: [0], target: 0 }, { olds: [], target: 1 }, { olds: [1], target: null }, { olds: [2], target: 2 },
  ])
})

test('함께 얹는 짝으로 옮기면 밀어내지 않는다(필기본끼리)', () => {
  const { slots, displaced } = reassign([pair(0, 0), pair(1, 1), pair(2, 2)], 2, 1, true)
  assert.equal(displaced, null)
  assert.deepEqual(slots, [pair(0, 0), pair(1, 1, [2]), pair(null, 2)])
  // 대표를 옮기면 함께 얹힌 옛 쪽이 대표가 된다
  const back = reassign(slots, 1, 2, true).slots
  assert.deepEqual(back, [pair(0, 0), pair(2, 1), pair(1, 2)])
})

test('뺀 옛 쪽은 원래 자리에 끼우고, 함께 얹힌 쪽을 빼도 새 쪽은 남는다', () => {
  const slots = withDropped([pair(0, 0), pair(2, 1, [3])], [1])
  assert.deepEqual(slots, [pair(0, 0), pair(1, null), pair(2, 1, [3])])
  const rows = toRows(slots, (s) => s === 1 || s === 2, () => true)
  assert.deepEqual(rows, [
    { source_index: 0, target_index: 0, confirmed: true, excluded: false },
    { source_index: 1, target_index: null, confirmed: true, excluded: true },
    { source_index: 3, target_index: 1, merged: [], confirmed: true, excluded: false },
    { source_index: 2, target_index: null, confirmed: true, excluded: true },
  ])
})
