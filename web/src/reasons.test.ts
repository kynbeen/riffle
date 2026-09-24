import assert from 'node:assert/strict'
import { test } from 'node:test'
import { footnotes, headline, REASON_WORDS } from './reasons.ts'

const summary = { matched: 95, automatic: 93, attention: 2, new_pages: 1, kept_old: 0, omitted: 3, result_pages: 96 }

test('확인할 쪽이 있으면 몇 쪽만 보면 되는지 말한다', () => {
  assert.equal(headline(summary, 2), '93쪽은 자동으로 맞췄습니다. 2쪽만 봐 주세요.')
  assert.equal(headline(summary, 0), '93쪽은 자동으로 맞췄고, 2쪽은 봐 주셨습니다.')
})

test('확인할 쪽이 없으면 모두 맞췄다고만 말한다', () => {
  assert.equal(headline({ ...summary, attention: 0 }, 0), '96쪽을 모두 자동으로 맞췄습니다.')
})

test('새 쪽과 뺀 쪽은 할 일 없이 알리기만 한다', () => {
  assert.deepEqual(footnotes(summary), [
    '새 PDF에서 새로 생긴 1쪽은 필기 없이 들어갑니다.',
    '필기가 없는 옛 쪽 3쪽은 뺐습니다.',
  ])
})

test('이유 문장에 숫자·내부 용어가 없다', () => {
  for (const words of Object.values(REASON_WORDS)) {
    const text = words.title + words.detail
    assert.doesNotMatch(text, /\d|mm|배율|margin|distance|slot|sdocx/i)
  }
})
