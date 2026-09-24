import assert from 'node:assert/strict'
import { test } from 'node:test'
import { defaultOrder, formatRanges, isDefault, key, move, syncOrder, type Doc } from './merging.ts'

const doc = (id: string, count: number): Doc => ({
  id, name: `${id}.pdf`, page_count: count,
  pages: Array.from({ length: count }, (_, index) => ({ index, width: 720, height: 540 })),
})
const docs = [doc('a', 3), doc('b', 2)]
const all = new Set(defaultOrder(docs, new Set(['a:0', 'a:1', 'a:2', 'b:0', 'b:1'])).map(key))
const keys = (refs: { document_id: string; page_index: number }[]) => refs.map(key)

test('기본은 모든 쪽, 놓은 순서', () => {
  assert.deepEqual(keys(defaultOrder(docs, all)), ['a:0', 'a:1', 'a:2', 'b:0', 'b:1'])
})

test('순서를 손대지 않았으면 선택만 따라간다', () => {
  const selected = new Set(['b:1', 'a:2'])
  assert.deepEqual(keys(syncOrder([], docs, selected, false)), ['a:2', 'b:1'])
})

test('손댄 순서는 지키고, 새로 고른 쪽은 같은 문서 곁에 끼운다', () => {
  const handmade = [{ document_id: 'b', page_index: 0 }, { document_id: 'a', page_index: 0 }, { document_id: 'a', page_index: 2 }]
  const selected = new Set(['b:0', 'a:0', 'a:1', 'a:2'])
  assert.deepEqual(keys(syncOrder(handmade, docs, selected, true)), ['b:0', 'a:0', 'a:1', 'a:2'])
  const dropped = syncOrder(handmade, docs, new Set(['b:0', 'a:2']), true)
  assert.deepEqual(keys(dropped), ['b:0', 'a:2'])
})

test('쪽을 끌어 옮긴다', () => {
  const order = defaultOrder(docs, all)
  assert.deepEqual(keys(move(order, 4, 0)), ['b:1', 'a:0', 'a:1', 'a:2', 'b:0'])
  assert.equal(move(order, 1, 1), order)
  assert.equal(isDefault(order, docs), true)
  assert.equal(isDefault(move(order, 4, 0), docs), false)
})

test('고른 쪽을 범위 글로 적는다', () => {
  assert.equal(formatRanges([0, 1, 2, 4, 7, 8, 9], 10), '1-3, 5, 8-')
  assert.equal(formatRanges([0, 1, 2], 3), '전체')
  assert.equal(formatRanges([], 3), '')
  assert.equal(formatRanges([1], 3), '2')
  assert.equal(formatRanges([0, 1, 3], 5), '1-2, 4')
})
