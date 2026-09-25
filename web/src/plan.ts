// 쪽 짝 고치기(명세 2026-09-24-01 작업 단위 4b — `다른 쪽`). 화면과 떨어진 순수 함수라 node 로 시험한다.
//
// 한 줄(slot)은 옛 쪽(source)과 새 쪽(target)의 짝이다. 한쪽이 없으면 그쪽에만 있는 쪽이다. 줄의 순서가 곧 결과
// 문서의 쪽 순서다. Sleek 필기본의 반복 수가 줄면 옛 쪽 여럿의 필기가 새 쪽 하나에 모인다 — 대표 옛 쪽 말고
// 함께 얹는 옛 쪽은 `merged` 에 둔다(명세 2026-09-25-03).

export interface Slot {
  source_index: number | null
  target_index: number | null
  merged?: number[]
}

export interface Reassigned {
  slots: Slot[]
  // t2 를 차지하던 옛 쪽. 조용히 다른 새 쪽으로 옮기지 않는다 — 짝 없는 옛 쪽으로 돌려 사람이 보게 한다.
  displaced: number | null
}

// 이 줄에 필기를 얹는 옛 쪽 전부 — 대표가 맨 앞.
export function sourcesOf(slot: Slot): number[] {
  return slot.source_index === null ? [...(slot.merged ?? [])] : [slot.source_index, ...(slot.merged ?? [])]
}

// 옛 `source` 쪽의 필기를 새 `target` 쪽에 얹는다. **새 쪽의 순서는 그대로다** — 옛 필기가 어느 새 쪽에
// 얹힐지만 바뀐다. `source` 가 떠난 새 쪽은 (다른 옛 쪽이 함께 얹혀 있지 않으면) 필기 없는 새 쪽이 된다.
// `merge` 면(새 판이 정답인 필기본끼리) 그 새 쪽에 이미 옛 쪽이 있어도 밀어내지 않고 함께 얹는다.
export function reassign(slots: Slot[], source: number, target: number, merge = false): Reassigned {
  const from = slots.findIndex((slot) => sourcesOf(slot).includes(source))
  const to = slots.findIndex((slot) => slot.target_index === target)
  if (from < 0 || to < 0) throw new Error('없는 쪽입니다.')
  if (from === to) return { slots, displaced: null }

  const next = slots.map((slot) => ({ ...slot, merged: [...(slot.merged ?? [])] }))
  // 떠난 자리: 대표였으면 함께 얹힌 옛 쪽 중 첫째가 대표가 된다. 아무것도 안 남으면 새 쪽만 남거나 줄이 사라진다.
  const left = next[from]
  if (left.source_index === source) {
    left.source_index = left.merged!.length ? left.merged!.shift()! : null
  } else {
    left.merged = left.merged!.filter((item) => item !== source)
  }
  const arrive = next[to]
  let displaced: number | null = null
  if (arrive.source_index === null) {
    arrive.source_index = source
  } else if (merge) {
    const all = [arrive.source_index, ...arrive.merged!, source].sort((a, b) => a - b)
    arrive.source_index = all[0]
    arrive.merged = all.slice(1)
  } else {
    displaced = arrive.source_index
    arrive.source_index = source
    // 밀려난 옛 쪽은 바로 뒤에 짝 없는 옛 쪽으로 둔다 — 필기가 없어도 옛 쪽째 남는다(합집합, 명세 2026-09-25-01).
    next.splice(to + 1, 0, { source_index: displaced, target_index: null, merged: [] })
  }
  return { slots: tidy(next), displaced }
}

function tidy(slots: Slot[]): Slot[] {
  return slots
    .filter((slot) => slot.source_index !== null || slot.target_index !== null)
    .map((slot) => (slot.merged && slot.merged.length ? slot : { source_index: slot.source_index, target_index: slot.target_index }))
}

// 옛 쪽 자리에서 가장 가까운 새 쪽. `다른 쪽` 띠를 여기서 시작한다 — 1쪽부터 훑게 하지 않는다.
export function nearTarget(slots: Slot[], source: number): number | null {
  const at = slots.findIndex((slot) => sourcesOf(slot).includes(source))
  if (at < 0) return null
  for (let step = 0; step < slots.length; step += 1) {
    for (const index of [at + step, at - step]) {
      const target = slots[index]?.target_index
      if (target !== undefined && target !== null) return target
    }
  }
  return null
}

// 옛 쪽 → 지금 필기가 얹힌 새 쪽(없으면 null).
export function targetOf(slots: Slot[], source: number): number | null {
  return slots.find((slot) => sourcesOf(slot).includes(source))?.target_index ?? null
}

// 서버가 결과에서 뺀 옛 쪽(새 판에 없는 빈 쪽)을 원래 자리에 짝 없는 옛 쪽으로 끼운다 — 화면에서는 `뺀 쪽` 으로
// 보이고, `다시 넣기` 하면 옛 쪽째 남는다.
export function withDropped(slots: Slot[], dropped: number[]): Slot[] {
  const out = slots.map((slot) => ({ ...slot }))
  for (const source of [...dropped].sort((a, b) => a - b)) {
    let at = 0
    out.forEach((slot, index) => { if (sourcesOf(slot).some((other) => other < source)) at = index + 1 })
    out.splice(at, 0, { source_index: source, target_index: null })
  }
  return out
}

// 저장할 줄. `excluded(옛 쪽)` 이 참인 옛 쪽은 결과에서 뺀다. 함께 얹힌 옛 쪽을 빼도 새 쪽은 남는다 — 그 쪽에는
// 다른 옛 쪽의 필기가 있다. 대표 하나뿐인 줄을 빼면 지금처럼 새 쪽도 함께 빠진다.
export interface Row extends Slot { confirmed: boolean; excluded: boolean }

export function toRows(slots: Slot[], excluded: (source: number) => boolean, confirmed: (slot: Slot) => boolean): Row[] {
  const rows: Row[] = []
  for (const slot of slots) {
    const all = sourcesOf(slot)
    const kept = all.filter((source) => !excluded(source))
    const gone = all.filter((source) => excluded(source))
    if (all.length > 1 && kept.length > 0 && slot.target_index !== null) {
      rows.push({ source_index: kept[0], target_index: slot.target_index, merged: kept.slice(1),
                  confirmed: confirmed(slot), excluded: false })
      for (const source of gone) rows.push({ source_index: source, target_index: null, confirmed: true, excluded: true })
    } else {
      const drop = all.length > 0 && kept.length === 0
      rows.push({ source_index: slot.source_index, target_index: slot.target_index,
                  ...(slot.merged?.length ? { merged: slot.merged } : {}),
                  confirmed: confirmed(slot), excluded: drop })
    }
  }
  return rows
}
