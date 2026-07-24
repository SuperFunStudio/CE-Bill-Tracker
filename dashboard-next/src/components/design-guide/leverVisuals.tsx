import type { SVGProps } from 'react';
import {
  RecycleIcon,
  LoopIcon,
  WrenchIcon,
  FeatherIcon,
  LeafIcon,
  FlaskIcon,
  BanIcon,
  PackageIcon,
  LabelIcon,
} from '@/components/ui/icons';

// One monochrome line icon per design lever — the same mark on every screen size (no emoji swap),
// so the cards keep the editorial "Gazette" voice on mobile and desktop alike.
type LeverIcon = (props: SVGProps<SVGSVGElement>) => JSX.Element;

export const LEVER_ICONS: Record<string, LeverIcon> = {
  reuse_refill: LoopIcon,
  repairability_durability: WrenchIcon,
  source_reduction: FeatherIcon,
  design_for_recycling: RecycleIcon,
  recycled_content: PackageIcon,
  compostability: LeafIcon,
  material_restriction: BanIcon,
  toxics_elimination: FlaskIcon,
  labeling_marking: LabelIcon,
};

export function leverIcon(lever: string): LeverIcon {
  return LEVER_ICONS[lever] ?? PackageIcon;
}

/** The principle's line mark, used on both faces of the card and in the grid. */
export function PrincipleIcon({ lever, className = '' }: { lever: string; className?: string }) {
  const Icon = leverIcon(lever);
  return <Icon className={className} aria-hidden />;
}
