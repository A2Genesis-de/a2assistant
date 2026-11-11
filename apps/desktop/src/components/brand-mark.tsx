import { cn } from '@/lib/utils'

const MARK_VIEW_BOX = '0 0 100 100'

const MARK_PATHS = [
  'M50 0L0.3 99.4L38.4 63.4L50 40.7L61.5 63.4L99.6 99.4Z',
  'M12.1 92.8L54.8 78.7L81 87L61.4 71.2L40.5 68.8Z'
] as const

function BrandGlyph({ className, ...props }: React.ComponentProps<'svg'>) {
  return (
    <svg
      aria-hidden="true"
      className={cn('shrink-0', className)}
      fill="currentColor"
      focusable="false"
      viewBox={MARK_VIEW_BOX}
      {...props}
    >
      {MARK_PATHS.map(path => (
        <path d={path} key={path} />
      ))}
    </svg>
  )
}

export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'inline-flex size-14 shrink-0 items-center justify-center rounded-[28%] bg-foreground text-background',
        className
      )}
      {...props}
    >
      <BrandGlyph className="size-[56%] -translate-y-[3%]" />
    </span>
  )
}
