import Link from "next/link";
import { BrandLockup } from "@/components/shell/Brand";

/** Root entry: points evaluators to the public synthetic demo. /app/ is reserved (ADR-024). */
export default function RootPage() {
  return (
    <div className="catalog-hero">
      <h1>
        <BrandLockup width={480} />
      </h1>
      <p className="muted">A workforce continuity platform for onboarding, daily work, shift handover and exit knowledge transfer.</p>
      <div className="row">
        <Link className="btn btn-primary" href="/demo/">
          Explore the synthetic demo
        </Link>
      </div>
      <p className="small muted">Sign-in for real organizations isn&apos;t part of this release.</p>
    </div>
  );
}
