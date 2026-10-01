import { ScanLine } from 'lucide-react'

interface BrandMarkProps {
  inverted?: boolean
  compact?: boolean
}

export function BrandMark({ inverted = false, compact = false }: BrandMarkProps) {
  return (
    <span className={`brand-mark${inverted ? ' brand-mark-inverted' : ''}${compact ? ' brand-mark-compact' : ''}`}>
      <span className="brand-mark-icon" aria-hidden="true">
        <ScanLine size={compact ? 17 : 20} strokeWidth={1.8} />
      </span>
      <span className="brand-mark-name">
        2DAP<span>-3SPRO</span>
      </span>
    </span>
  )
}
