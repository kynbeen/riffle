// 연결 보기의 줄 배치(명세 2026-09-25-03). 왼쪽에 옛 파일의 모든 쪽을 옛 순서대로, 오른쪽에 새 파일의 모든 쪽을
// 새 순서대로 놓고, 짝끼리 선으로 잇는다. 화면과 떨어진 순수 함수라 node 로 시험한다.
//
// 두 세로 띠가 **함께 흐르게** 줄(band)로 묶는다. 한 줄에는 새 쪽 하나와, 그 새 쪽에 필기를 얹는 옛 쪽 중 옛 순서로
// 바로 이어지는 것들이 같은 높이에 온다 — 대부분의 선은 가로로 곧다. 새 판에서 순서가 바뀐 쪽만 선이 비스듬히
// 건너간다. 그래서 "어디가 어디로 갔는지"가 한눈에 보인다(요청 7).

import { sourcesOf, type Slot } from './plan.ts'

export interface Band {
  olds: number[]           // 이 줄 왼쪽의 옛 쪽들(옛 순서)
  target: number | null    // 이 줄 오른쪽의 새 쪽
}

export interface Link {
  old: number
  target: number
}

export function links(slots: Slot[]): Link[] {
  return slots.flatMap((slot) => slot.target_index === null ? []
    : sourcesOf(slot).map((old) => ({ old, target: slot.target_index! })))
}

export function bands(slots: Slot[], sourceCount: number, targetCount: number): Band[] {
  const feeding = new Map<number, number[]>()          // 새 쪽 → 필기를 얹는 옛 쪽들
  for (const { old, target } of links(slots)) feeding.set(target, [...(feeding.get(target) ?? []), old])
  const out: Band[] = []
  let next = 0                                          // 아직 줄에 넣지 않은 첫 옛 쪽
  for (let target = 0; target < targetCount; target += 1) {
    const olds = (feeding.get(target) ?? []).filter((old) => old >= next).sort((a, b) => a - b)
    if (!olds.length) {
      out.push({ olds: [], target })
      continue
    }
    // 이 새 쪽의 옛 쪽보다 앞선 옛 쪽은 혼자 한 줄씩 — 다른 새 쪽으로 갔거나(선이 건너간다) 결과에 없다.
    for (; next < olds[0]; next += 1) out.push({ olds: [next], target: null })
    // 옛 순서로 바로 이어지는 것까지만 이 줄에. 사이에 끼인 다른 옛 쪽이 있으면 나머지는 제 자리에서 선으로 온다.
    const run = [olds[0]]
    while (olds.includes(run[run.length - 1] + 1)) run.push(run[run.length - 1] + 1)
    out.push({ olds: run, target })
    next = run[run.length - 1] + 1
  }
  for (; next < sourceCount; next += 1) out.push({ olds: [next], target: null })
  return out
}
