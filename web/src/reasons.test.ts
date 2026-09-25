import assert from 'node:assert/strict'
import { test } from 'node:test'
import { candidateWords, footnotes, headline, REASON_WORDS } from './reasons.ts'

const summary = { matched: 95, automatic: 93, attention: 2, new_pages: 1, kept_old: 3, kept_blank: 3, result_pages: 99, moved: 0 }

test('확인할 쪽이 있으면 몇 쪽만 보면 되는지 말한다', () => {
  assert.equal(headline(summary, 2), '93쪽은 자동으로 맞췄습니다. 2쪽만 봐 주세요.')
  assert.equal(headline(summary, 0), '93쪽은 자동으로 맞췄고, 2쪽은 봐 주셨습니다.')
})

test('확인할 쪽이 없으면 모두 맞췄다고만 말한다', () => {
  assert.equal(headline({ ...summary, attention: 0 }, 0), '99쪽을 모두 자동으로 맞췄습니다.')
})

test('새 쪽과 필기 없이 남긴 옛 쪽은 할 일 없이 알리기만 한다', () => {
  assert.deepEqual(footnotes(summary), [
    { text: '새 PDF에서 새로 생긴 1쪽은 필기 없이 들어갑니다.', filter: 'new' },
    { text: '새 PDF에 없는 옛 쪽 3쪽은 필기가 없어도 제자리에 남겼습니다.', filter: 'kept' },
  ])
})

test('순서가 바뀐 쪽은 옮겼다고 알리기만 한다', () => {
  assert.deepEqual(footnotes({ ...summary, new_pages: 0, kept_blank: 0, moved: 2 }),
    [{ text: '새 판에서 순서가 바뀐 2쪽은 필기를 새 자리로 옮겼습니다.', filter: 'moved' }])
})

test('짝 후보 카드는 몇 번째 새 쪽인지 사람 쪽 번호로 말한다', () => {
  assert.equal(candidateWords(24).detail, '새 25쪽이 이 쪽과 닮았지만 확신이 없습니다. 같은 쪽이면 필기를 새 25쪽에 얹습니다.')
  assert.doesNotMatch(candidateWords(24).title + candidateWords(24).detail, /빼도|빼세요/)
})

test('어떤 이유 문장도 빼기를 권하지 않는다 — 빼면 손필기가 결과에서 빠진다', () => {
  for (const words of Object.values(REASON_WORDS)) {
    assert.doesNotMatch(words.title + words.detail, /빼도|빼세요|빼 주세요/)
  }
})

test('이유 문장에 숫자·내부 용어가 없다', () => {
  for (const words of Object.values(REASON_WORDS)) {
    const text = words.title + words.detail
    assert.doesNotMatch(text, /\d|mm|배율|margin|distance|slot|sdocx/i)
  }
})
