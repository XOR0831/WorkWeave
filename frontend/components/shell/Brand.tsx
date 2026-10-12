import Image from "next/image";

/**
 * Approved WorkWeave brand placements (docs/29-brand-identity.md).
 *
 * public/brand/*.png are byte-identical copies of the owner-supplied exports (SHA-256 checked).
 * They are never cropped, recoloured or redrawn. No dark-background lockup has been supplied:
 * on dark surfaces the icon sits directly on the surface (logos are exempt from WCAG contrast;
 * the product name beside it is live text), and the horizontal lockup, whose lettering is dark,
 * is replaced by the icon with a live-text wordmark and tagline (CLAUDE.md text-only fallback).
 */
export const TAGLINE = "Weaving Knowledge Into Every Work";

/** Compact header brand: approved WW icon (decorative) + product name as text. */
export function BrandHeader() {
  return (
    <span className="brand-inner">
      <Image className="brand-icon" src="/brand/workweave-icon.png" alt="" width={56} height={28} priority unoptimized />
      <span className="brand-name">
        <span className="brand-name-work">Work</span>Weave
      </span>
    </span>
  );
}

/** Hero lockup: approved horizontal logo on light surfaces; icon + live-text wordmark on dark. */
export function BrandLockup({ width = 440 }: { width?: number }) {
  const height = Math.round((width * 724) / 2172);
  return (
    <span className="brand-lockup">
      <Image
        className="brand-lockup-img lockup-light"
        src="/brand/workweave-horizontal-logo.png"
        alt={`WorkWeave: ${TAGLINE}`}
        width={width}
        height={height}
        style={{ width: `min(${width}px, 100%)`, height: "auto" }}
        priority
        unoptimized
      />
      <span className="lockup-dark" role="img" aria-label={`WorkWeave: ${TAGLINE}`}>
        <Image className="lockup-dark-icon" src="/brand/workweave-icon.png" alt="" width={Math.round(width * 0.3)} height={Math.round(width * 0.15)} unoptimized />
        <span className="lockup-dark-text" aria-hidden="true">
          <span className="brand-name lockup-dark-name">
            <span className="brand-name-work">Work</span>Weave
          </span>
          <span className="lockup-dark-tagline">{TAGLINE}</span>
        </span>
      </span>
    </span>
  );
}
