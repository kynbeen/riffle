// 확인할 쪽의 이유 — 서버(riffle/review.py)는 종류만 보내고, 사람이 읽는 말은 여기 한 곳에 둔다(원칙 8).

export type Reason = 'panel_ink' | 'old_only' | 'different' | 'duplicate' | 'alignment'

export const REASON_WORDS: Record<Reason, { title: string; detail: string }> = {
  panel_ink: {
    title: '손필기가 필기 칸 위에 있습니다',
    detail: '필기본을 다시 만들며 칸의 글이 바뀌었을 수 있습니다. 손필기가 엉뚱한 글 위에 얹히지 않았는지 봐 주세요.',
  },
  old_only: {
    title: '새 PDF에 없는 쪽입니다',
    // 빼기를 권하지 않는다 — 빼면 이 쪽의 손필기가 결과에 들어가지 않는다(원칙 7, 명세 2026-09-25-01).
    detail: '필기를 잃지 않게 옛 쪽째 남깁니다. 새 PDF에 같은 쪽이 있으면 「다른 쪽」에서 골라 주세요. 필기가 그 쪽에 얹힙니다.',
  },
  different: {
    title: '비슷하지만 달라진 곳이 있습니다',
    detail: '같은 쪽으로 보고 짝지었지만 확신이 없습니다. 필기가 제자리에 있는지 봐 주세요.',
  },
  duplicate: {
    title: '새 PDF에 똑같은 쪽이 하나 더 있습니다',
    detail: '어느 쪽에 옮길지 확신이 없습니다. 이 짝이 맞는지 봐 주세요.',
  },
  alignment: {
    title: '쪽 안 내용의 자리가 많이 달라졌습니다',
    detail: '필기 위치를 새 쪽에 맞춰 옮겼습니다. 제자리에 있는지 봐 주세요.',
  },
}

export interface ReviewItem {
  slot: number
  source_index: number | null
  target_index: number | null
  reason: Reason
  candidate?: number    // 닮았지만 애매한 새 쪽 — 카드에 나란히 보인다
  closest?: number      // 후보도 없을 때 새 PDF 에서 가장 닮은 쪽 — `다른 쪽` 띠의 시작점일 뿐
}

export interface ReviewSummary {
  matched: number
  automatic: number
  attention: number
  new_pages: number
  kept_old: number      // 새 PDF 에 없어 옛 쪽째 남기는 쪽(필기 없는 쪽 포함)
  kept_blank: number    // 그중 필기가 없는 쪽
  result_pages: number
  moved: number         // 새 판에서 순서가 바뀌어 다시 짝지은 옛 쪽
}

export interface Review {
  items: ReviewItem[]
  blank_sources: number[]
  moved_sources: number[]
  summary: ReviewSummary
}

// 머리 한 줄이 결론이다(명세 「필기 옮기기」).
export function headline(summary: ReviewSummary, open: number): string {
  if (summary.attention === 0) return `${summary.result_pages}쪽을 모두 자동으로 맞췄습니다.`
  if (open === 0) return `${summary.automatic}쪽은 자동으로 맞췄고, ${summary.attention}쪽은 봐 주셨습니다.`
  return `${summary.automatic}쪽은 자동으로 맞췄습니다. ${open}쪽만 봐 주세요.`
}

// 짝 후보 카드 — 새 PDF에 없는 옛 쪽과 닮았지만 확신이 없는 새 쪽을 나란히 보일 때.
export function candidateWords(target: number): { title: string; detail: string } {
  return {
    title: '같은 쪽일까요?',
    detail: `새 ${target + 1}쪽이 이 쪽과 닮았지만 확신이 없습니다. 같은 쪽이면 필기를 새 ${target + 1}쪽에 얹습니다.`,
  }
}

// 헤드라인 아래 작은 글 — 사람이 따로 할 일은 없지만 알아 두면 좋은 것.
export function footnotes(summary: ReviewSummary): string[] {
  const notes: string[] = []
  if (summary.moved) notes.push(`새 판에서 순서가 바뀐 ${summary.moved}쪽은 필기를 새 자리로 옮겼습니다.`)
  if (summary.new_pages) notes.push(`새 PDF에서 새로 생긴 ${summary.new_pages}쪽은 필기 없이 들어갑니다.`)
  // 합집합 — 새 판에 없는 옛 쪽은 필기가 없어도 제자리에 남긴다(명세 2026-09-25-01).
  if (summary.kept_blank) notes.push(`새 PDF에 없는 옛 쪽 ${summary.kept_blank}쪽은 필기가 없어도 제자리에 남겼습니다.`)
  return notes
}
