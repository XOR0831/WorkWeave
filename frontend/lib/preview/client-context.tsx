"use client";

/**
 * React bindings for the WorkWeave client.
 *
 * Screens consume `useClient()` typed as WorkWeaveClient. Only the Review tools drawer
 * uses `usePreviewControls()`. Data is always fetched after mount so the static export's
 * prerendered HTML (loading states) matches the first client render.
 */
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import type { WorkWeaveClient } from "@/lib/clients/WorkWeaveClient";
import type { ClientRuntime } from "@/lib/clients/runtime";
import { PreviewClient, type PreviewControls } from "@/lib/clients/preview/PreviewClient";
import { createHttpClient } from "@/lib/clients/http/HttpClient";
import { WorkWeaveError, type ApiError, type DemoSession, type Persona } from "@/types/contracts";

/** Build-time mode: "http" uses the WorkWeave API; anything else is the labelled UI preview. */
export const CLIENT_MODE: "preview" | "http" = process.env.NEXT_PUBLIC_WORKWEAVE_MODE === "http" ? "http" : "preview";

interface Ctx {
  client: ClientRuntime;
  version: number;
  session: DemoSession | null;
  personas: Persona[];
  ready: boolean;
}

const ClientContext = createContext<Ctx | null>(null);

let singleton: ClientRuntime | null = null;
function getClient(): ClientRuntime {
  if (!singleton) singleton = CLIENT_MODE === "http" ? createHttpClient() : new PreviewClient();
  return singleton;
}

export function ClientProvider({ children }: { children: ReactNode }) {
  const [client] = useState(getClient);
  const version = useSyncExternalStore(client.subscribe, () => client.getVersion(), () => 0);
  // false during static prerender and hydration, true afterwards (no mismatch).
  const hydrated = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const ready = hydrated && client.isLoaded();
  const session = ready ? client.peekSession() : null;
  const personas = useMemo(() => {
    if (!ready || !session) return [];
    return client.peekPersonas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, session?.scenario.key, version]);
  return <ClientContext.Provider value={{ client, version, session, personas, ready }}>{children}</ClientContext.Provider>;
}

const noopSubscribe = () => () => {};

function useCtx() {
  const c = useContext(ClientContext);
  if (!c) throw new Error("ClientProvider missing");
  return c;
}

export function useClient(): WorkWeaveClient {
  return useCtx().client;
}

/** Preview-only controls (failure injection, reset, shift advance). Null outside preview mode. */
export function usePreviewControls(): (PreviewControls & { unreadCount(): number; hasWorkspace(k: string): boolean }) | null {
  const c = useCtx().client;
  return c.mode === "preview" ? (c as unknown as PreviewControls & { unreadCount(): number; hasWorkspace(k: string): boolean }) : null;
}

/** The runtime client, for the shell's mode-specific notices. */
export function useRuntime(): ClientRuntime {
  return useCtx().client;
}

export function useSession() {
  const { session, personas, ready, version } = useCtx();
  const nameOf = useCallback(
    (id?: string) => {
      const p = personas.find((x) => x.employee_id === id);
      return p ? `${p.first_name} ${p.last_name}` : "Unassigned";
    },
    [personas],
  );
  return { session, personas, ready, nameOf, version };
}

export function toApiError(e: unknown): ApiError {
  if (e instanceof WorkWeaveError) return e.error;
  return { code: "DEPENDENCY_UNAVAILABLE", message: e instanceof Error ? e.message : "Something went wrong.", retryable: true };
}

/**
 * Loads a resource after mount and refreshes it silently when preview state changes.
 */
export function useResource<T>(fetcher: (c: WorkWeaveClient) => Promise<T>, deps: unknown[] = []) {
  const { client, version, ready } = useCtx();
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  useLayoutEffect(() => {
    fetcherRef.current = fetcher;
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!ready) return;
    let alive = true;
    fetcherRef
      .current(client)
      .then((d) => {
        if (!alive) return;
        setData(d);
        setError(null);
      })
      .catch((e) => alive && setError(toApiError(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, ready, version, nonce, ...deps]);

  const reload = useCallback(() => {
    setLoading(true);
    setNonce((n) => n + 1);
  }, []);
  return { data, error, loading: loading && data === undefined, reload };
}

let keySeq = 0;
export const newKey = (prefix = "cmd") => `${prefix}-${Date.now().toString(36)}-${(keySeq += 1)}`;

/**
 * Runs a command with pending/error state. The same idempotency key is reused on retry
 * until the command succeeds (07-api-contracts: retry returns the committed result).
 */
export function useCommand() {
  const client = useClient();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const keyRef = useRef<string | null>(null);
  const inFlight = useRef(false);
  const run = useCallback(
    async <T,>(fn: (c: WorkWeaveClient, idempotency_key: string) => Promise<T>): Promise<T | undefined> => {
      // One command at a time per control: a second click before re-render must not submit a stale revision.
      if (inFlight.current) return undefined;
      inFlight.current = true;
      keyRef.current ??= newKey();
      setPending(true);
      setError(null);
      try {
        const r = await fn(client, keyRef.current);
        keyRef.current = null;
        // Let the refreshed resource render before the control re-enables.
        await new Promise((res) => setTimeout(res, 60));
        return r;
      } catch (e) {
        setError(toApiError(e));
        return undefined;
      } finally {
        inFlight.current = false;
        setPending(false);
      }
    },
    [client],
  );
  return { run, pending, error, clearError: () => setError(null) };
}
