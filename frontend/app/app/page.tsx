import { BrandLockup } from "@/components/shell/Brand";

/**
 * Reserved future authenticated entry for real organization users (ADR-024).
 * Intentionally no login form, no demo catalog, no synthetic personas and no reset controls.
 */
export default function AppEntryReservedPage() {
  return (
    <div className="state">
      <BrandLockup width={360} />
      <h2>Organization sign-in isn&apos;t available yet</h2>
      <p>This entry is reserved for real organization users with verified identity. It isn&apos;t part of this release, and it doesn&apos;t use demo companies or personas.</p>
    </div>
  );
}
