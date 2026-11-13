import { SiTelegram } from '@icons-pack/react-simple-icons'
import type { ComponentPropsWithoutRef, ComponentType, SVGProps } from 'react'
import { forwardRef, memo } from 'react'

import { AvatarChip } from '@/components/ui/avatar-chip'
import { Globe, Link as LinkIcon } from '@/lib/icons'

type IconKind = 'brand' | 'generic'

interface PlatformIconSpec {
  Icon?: ComponentType<SVGProps<SVGSVGElement>>
  color: string
  kind: IconKind
}

const PLATFORM_ICONS: Record<string, PlatformIconSpec> = {
  telegram: { Icon: SiTelegram, color: '#26A5E4', kind: 'brand' },
  webhook: { Icon: LinkIcon, color: '#71717A', kind: 'generic' },
  api_server: { Icon: Globe, color: '#64748B', kind: 'generic' }
}

interface PlatformAvatarProps extends Omit<ComponentPropsWithoutRef<'span'>, 'children'> {
  platformId: string
  platformName: string
}

// forwardRef + spreading ...rest is required so a wrapping <Tip> (Radix
// Tooltip's `asChild`) can actually attach its trigger: asChild clones this
// component and injects a ref plus pointer/focus/aria handlers onto it. A
// plain function component with no ref/rest forwarding drops all of that
// silently — the tooltip renders but never opens (#67500).
export const PlatformAvatar = memo(
  forwardRef<HTMLSpanElement, PlatformAvatarProps>(function PlatformAvatar(
    { className, platformId, platformName, ...rest },
    ref
  ) {
    return (
      <AvatarChip
        aria-hidden="true"
        brand={PLATFORM_ICONS[platformId]}
        className={className}
        name={platformName}
        ref={ref}
        {...rest}
      />
    )
  })
)
