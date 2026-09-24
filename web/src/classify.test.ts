// node --test 로 돈다(Node 24 가 타입을 벗겨 바로 읽는다). tests/test_new_ui.py 가 부른다.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { decide, kindOf } from './classify.ts'

const f = (name: string) => ({ name })

test('필기 파일 하나와 PDF 하나면 필기 옮기기', () => {
  const result = decide([], [f('옛 필기.sdocx'), f('새 족첵.PDF')])
  assert.equal(result.kind, 'handwriting')
  if (result.kind === 'handwriting') {
    assert.equal(result.source.name, '옛 필기.sdocx')
    assert.equal(result.target.name, '새 족첵.PDF')
  }
})

test('PDF 둘 이상이면 문서 합치기', () => {
  const result = decide([], [f('a.pdf'), f('b.pdf'), f('c.pdf')])
  assert.equal(result.kind, 'merge')
  if (result.kind === 'merge') assert.equal(result.pdfs.length, 3)
})

test('필기 파일 하나만이면 새 PDF 를 기다린다', () => {
  const result = decide([], [f('x.goodnotes')])
  assert.equal(result.kind, 'wait')
  if (result.kind === 'wait') assert.match(result.message, /새 PDF를 놓으세요/)
})

test('PDF 하나만이면 둘 다 받을 수 있다고 말하며 기다린다', () => {
  const result = decide([], [f('x.pdf')])
  assert.equal(result.kind, 'wait')
  if (result.kind === 'wait') assert.match(result.message, /필기 파일을 함께 놓으면.*PDF를 더 놓으면/)
})

test('그 밖의 조합은 무엇이 안 되는지 말하고, 기다리던 파일은 그대로 둔다', () => {
  const held = [f('a.pdf')]
  const twoNotes = decide([], [f('a.sdocx'), f('b.notewise')])
  assert.equal(twoNotes.kind, 'reject')
  const unknown = decide(held, [f('memo.docx')])
  assert.equal(unknown.kind, 'reject')
  if (unknown.kind === 'reject') {
    assert.deepEqual(unknown.held, held)
    assert.match(unknown.message, /memo\.docx/)
  }
  const tooManyTargets = decide([], [f('a.sdocx'), f('b.pdf'), f('c.pdf')])
  assert.equal(tooManyTargets.kind, 'reject')
})

test('따로 놓아도 모아서 정한다', () => {
  const first = decide([], [f('옛.notewise')])
  assert.equal(first.kind, 'wait')
  if (first.kind !== 'wait') return
  const second = decide(first.held, [f('새.pdf')])
  assert.equal(second.kind, 'handwriting')
})

test('확장자로 종류를 안다', () => {
  assert.equal(kindOf('A.SDOCX'), 'handwriting')
  assert.equal(kindOf('b.pdf'), 'pdf')
  assert.equal(kindOf('c.png'), 'other')
})
