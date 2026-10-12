"use client";

import { useSyncExternalStore } from "react";

/**
 * Current location.search as an external store: static-export safe (no Suspense boundary,
 * empty during prerender) and updates on back/forward navigation.
 */
function subscribe(cb: () => void) {
  window.addEventListener("popstate", cb);
  return () => window.removeEventListener("popstate", cb);
}

export function useSearch(): URLSearchParams | null {
  const raw = useSyncExternalStore(
    subscribe,
    () => window.location.search,
    () => null,
  );
  return raw === null ? null : new URLSearchParams(raw);
}

/** Public catalog selector keys only; never authority (ADR-024). */
export function companyEntryHref(company_key: string, scenario: string) {
  return `/demo/company/?company_key=${encodeURIComponent(company_key)}&scenario=${encodeURIComponent(scenario)}`;
}
