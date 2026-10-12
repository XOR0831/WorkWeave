import type { WorkWeaveClient } from "./WorkWeaveClient";
import type { ApiError, DemoSession, Persona } from "@/types/contracts";

/**
 * What the React shell needs beyond WorkWeaveClient: a synchronous view of the current
 * session for rendering, and change notifications. Both PreviewClient and HttpClient provide it.
 */
export interface ClientRuntime extends WorkWeaveClient {
  /** "preview": labelled browser-only fixtures. "http": the WorkWeave API (database-backed slices). */
  readonly mode: "preview" | "http";
  subscribe(fn: () => void): () => void;
  getVersion(): number;
  /** False until the first session lookup finished (HTTP mode loads it after mount). */
  isLoaded(): boolean;
  /** Set when the first session lookup failed, e.g. the API isn't reachable. */
  loadError(): ApiError | null;
  peekSession(): DemoSession | null;
  peekPersonas(): Persona[];
  unreadCount(): number;
}
