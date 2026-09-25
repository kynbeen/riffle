import type { ReactNode } from 'react'

// 한 번 묻는 창. 안전한 쪽(`cancel`)에 먼저 초점이 가고, Esc 도 그쪽이다(원칙 3·6).
export default function Sheet({ title, children, cancel, confirm, onCancel, onConfirm }: {
  title: string; children: ReactNode; cancel: string; confirm: string
  onCancel: () => void; onConfirm: () => void
}) {
  return (
    <div className="sheet-backdrop" role="dialog" aria-modal="true" aria-label={title}
      onKeyDown={(event) => { if (event.key === 'Escape') onCancel() }}>
      <div className="sheet">
        <div className="t-title">{title}</div>
        <div className="t-body">{children}</div>
        <div className="sheet-actions">
          <button className="button quiet" autoFocus onClick={onCancel}>{cancel}</button>
          <button className="button" onClick={onConfirm}>{confirm}</button>
        </div>
      </div>
    </div>
  )
}
