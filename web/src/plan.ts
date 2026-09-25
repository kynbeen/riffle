// 쪽 대응 고치기(명세 2026-09-24-01 작업 단위 4b — `다른 쪽`). 화면과 떨어진 순수 함수라 node 로 시험한다.
//
// 한 줄(slot)은 옛 쪽(source)과 새 쪽(target)의 짝이다. 한쪽이 없으면 그쪽에만 있는 쪽이다.
// 줄의 순서가 곧 결과 문서의 쪽 순서다.

export interface Slot {
  source_index: number | null
  target_index: number | null
}

export interface Reassigned {
  slots: Slot[]
  // t2 를 차지하던 옛 쪽. 조용히 다른 새 쪽으로 옮기지 않는다 — 짝 없는 옛 쪽으로 돌려 사람이 보게 한다.
  displaced: number | null
}

// 옛 `source` 쪽의 필기를 새 `target` 쪽에 얹는다. **새 쪽의 순서는 그대로다** — 옛 필기가 어느 새 쪽에
// 얹힐지만 바뀐다. `source` 가 떠난 새 쪽은 필기 없는 새 쪽이 된다.
export function reassign(slots: Slot[], source: number, target: number): Reassigned {
  const from = slots.findIndex((slot) => slot.source_index === source)
  const to = slots.findIndex((slot) => slot.target_index === target)
  if (from < 0 || to < 0) throw new Error('없는 쪽입니다.')
  if (from === to) return { slots, displaced: null }

  const next = slots.map((slot) => ({ ...slot }))
  const displaced = next[to].source_index
  next[to].source_index = source
  next[from].source_index = null            // 떠난 자리: 새 쪽만 남거나(필기 없는 새 쪽), 아무것도 안 남는다
  if (displaced !== null) {
    // 밀려난 옛 쪽은 바로 뒤에 짝 없는 옛 쪽으로 둔다 — 필기가 없어도 옛 쪽째 남는다(합집합, 명세 2026-09-25-01).
    next.splice(to + 1, 0, { source_index: displaced, target_index: null })
  }
  return { slots: next.filter((slot) => slot.source_index !== null || slot.target_index !== null), displaced }
}

// 옛 쪽 자리에서 가장 가까운 새 쪽. `다른 쪽` 띠를 여기서 시작한다 — 1쪽부터 훑게 하지 않는다.
export function nearTarget(slots: Slot[], source: number): number | null {
  const at = slots.findIndex((slot) => slot.source_index === source)
  if (at < 0) return null
  for (let step = 0; step < slots.length; step += 1) {
    for (const index of [at + step, at - step]) {
      const target = slots[index]?.target_index
      if (target !== undefined && target !== null) return target
    }
  }
  return null
}

// 옛 쪽 → 지금 짝지어진 새 쪽(없으면 null).
export function targetOf(slots: Slot[], source: number): number | null {
  return slots.find((slot) => slot.source_index === source)?.target_index ?? null
}
