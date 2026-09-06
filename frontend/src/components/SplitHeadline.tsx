interface SplitHeadlineProps {
  lead: string
  trail: string
  as?: 'h1' | 'h2' | 'h3'
  className?: string
}

/**
 * PRD 10.3 signature move: one headline split between white and gray, so the
 * gray clause reads as the subordinate thought. Used instead of bold or colour.
 */
export function SplitHeadline({
  lead,
  trail,
  as: Tag = 'h1',
  className = '',
}: SplitHeadlineProps) {
  const size =
    Tag === 'h1' ? 'text-display' : Tag === 'h2' ? 'text-h2' : 'text-h3'

  return (
    <Tag className={`${size} font-sans ${className}`}>
      <span className="text-text-primary">{lead}</span>{' '}
      <span className="text-text-secondary">{trail}</span>
    </Tag>
  )
}
