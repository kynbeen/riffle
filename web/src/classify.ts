// 놓은 파일의 종류와 개수로 할 일을 정한다(명세 2026-09-24-01 「첫 화면」). 묻지 않는다.
// 화면과 떨어진 순수 함수라 node 로 바로 시험한다(classify.test.ts).

export type FileKind = 'handwriting' | 'pdf' | 'other'

export interface Named {
  name: string
}

export type Decision<T extends Named> =
  | { kind: 'handwriting'; source: T; target: T }
  | { kind: 'merge'; pdfs: T[] }
  | { kind: 'wait'; held: T[]; message: string }
  | { kind: 'reject'; held: T[]; message: string }

const HANDWRITING = ['.sdocx', '.notewise', '.goodnotes']

export function kindOf(name: string): FileKind {
  const lower = name.toLowerCase()
  if (HANDWRITING.some((suffix) => lower.endsWith(suffix))) return 'handwriting'
  if (lower.endsWith('.pdf')) return 'pdf'
  return 'other'
}

// `held` 는 앞서 놓아 기다리던 파일, `added` 는 방금 놓은 파일이다. 따로 놓아도 모아서 정한다.
// 받아들일 수 없는 조합이면 방금 놓은 것은 버리고 기다리던 것은 그대로 둔다.
export function decide<T extends Named>(held: T[], added: T[]): Decision<T> {
  const unknown = added.filter((file) => kindOf(file.name) === 'other')
  if (unknown.length) {
    return {
      kind: 'reject', held,
      message: `열 수 없는 파일입니다: ${unknown[0].name}. 필기 파일(Samsung Notes·Notewise·Goodnotes)이나 PDF를 놓아 주세요.`,
    }
  }
  const all = [...held, ...added]
  const handwriting = all.filter((file) => kindOf(file.name) === 'handwriting')
  const pdfs = all.filter((file) => kindOf(file.name) === 'pdf')

  if (handwriting.length > 1) {
    return { kind: 'reject', held, message: '필기 파일은 한 번에 하나만 옮길 수 있습니다. 하나만 놓아 주세요.' }
  }
  if (handwriting.length === 1) {
    if (pdfs.length === 1) return { kind: 'handwriting', source: handwriting[0], target: pdfs[0] }
    if (pdfs.length === 0) return { kind: 'wait', held: all, message: '필기를 옮길 새 PDF를 놓으세요.' }
    return { kind: 'reject', held, message: '필기는 PDF 하나로 옮깁니다. 새 PDF를 하나만 놓아 주세요.' }
  }
  if (pdfs.length >= 2) return { kind: 'merge', pdfs }
  if (pdfs.length === 1) {
    return { kind: 'wait', held: all, message: '필기 파일을 함께 놓으면 필기를 옮기고, PDF를 더 놓으면 합칩니다.' }
  }
  return { kind: 'wait', held: all, message: '' }
}
