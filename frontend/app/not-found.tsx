import Link from "next/link";

export default function NotFound() {
  return (
    <div className="state">
      <h2>This page doesn&apos;t exist</h2>
      <p>Check the address, or go back to the demo catalog.</p>
      <Link className="btn btn-primary" href="/demo/">
        Go to the catalog
      </Link>
    </div>
  );
}
