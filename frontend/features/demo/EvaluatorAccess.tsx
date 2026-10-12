"use client";

/**
 * Evaluator access (ADR-029), API mode only: a control in the demo entry header.
 *
 * Public visitors see an "Evaluator access" button; judges open it and enter the code they were
 * given (or open a link with ?access=…, which is removed from the address bar before it is sent,
 * and the dialog then confirms the result). With access on, the button becomes a green
 * "Evaluator access · until …" chip that reopens the dialog to stop using the code. The page never
 * shows or stores the code itself, only the tier and the expiry date.
 *
 * `prompt` (the landing page, every visit): the dialog opens by itself for public visitors, offering
 * the code or "Continue without evaluator access" with the public daily limits spelled out.
 * `variant="band"` (inside a company, next to Demo tools): a "Public demo · limits" button, or the
 * evaluator chip, whose dialog shows this run's use of each daily limit and when it resets.
 */
import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Dialog, ErrorNotice } from "@/components/ui";
import { useCommand, useResource, useRuntime } from "@/lib/preview/client-context";
import { resetTime } from "@/lib/limits";
import type { AccessInfo, DemoUsage } from "@/types/contracts";

const KIND_LABEL: Record<string, string> = {
  TUTOR_TURN: "Assistant messages (all AI assistants)",
  VOICE_LISTEN: "Voice input",
  VOICE_SPEECH: "Replies read aloud",
};

/** One line per daily limit; with a run open, how much of it this run has used. */
export function UsageList({ usage }: { usage: DemoUsage }) {
  const capped = usage.items.filter((i) => i.limit);
  if (!capped.length) return <p className="small muted">No daily limits are set on this server.</p>;
  return (
    <ul className="usage-list" data-testid="usage-list">
      {capped.map((i) => (
        <li key={i.kind}>
          <span>{KIND_LABEL[i.kind] ?? i.kind}</span>
          <b>{usage.run_open && i.used !== null ? `${i.used} / ${i.limit}` : `${i.limit} a day`}</b>
          {i.shared_full && <small className="usage-full">Today&apos;s shared limit is used up</small>}
        </li>
      ))}
    </ul>
  );
}

/** The last valid day. Codes run to the end of a UTC day, so the date is shown in UTC (otherwise
 * "through 31 Oct" would read "until 1 Nov" east of UTC). */
export function accessUntil(info: AccessInfo | undefined | null): string {
  if (!info?.expires_at) return "";
  return new Date(info.expires_at).toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
}

/** Reads ?access=… once and removes it from the URL so the code isn't left in history or shared links. */
function takeCodeFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  const url = new URL(window.location.href);
  const code = url.searchParams.get("access");
  if (!code) return null;
  url.searchParams.delete("access");
  window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
  return code;
}

function KeyIcon() {
  return (
    <svg className="access-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
      <circle cx="8" cy="15" r="4" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M11 12 20 3M16 7l3 3M14 9l2 2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function EvaluatorAccess({ variant = "entry", prompt = false }: { variant?: "entry" | "band"; prompt?: boolean }) {
  const api = useRuntime().mode === "http";
  if (!api) return null;
  return <AccessControl variant={variant} prompt={prompt} />;
}

function AccessControl({ variant, prompt }: { variant: "entry" | "band"; prompt: boolean }) {
  const id = useId();
  const router = useRouter();
  const access = useResource((c) => c.getAccess());
  const cmd = useCommand();
  const [open, setOpen] = useState(false);
  // The limits shown in the dialog, re-read each time it opens.
  const usage = useResource((c) => (open ? c.getDemoUsage() : Promise.resolve(null)), [open, access.data?.tier]);
  // The landing page asks every time it opens, unless access is already on or a code link is being used.
  const [prompting, setPrompting] = useState(false);
  const [code, setCode] = useState("");
  const [justEnabled, setJustEnabled] = useState(false);
  // A code from ?access=… taken from the URL once; kept until its redeem actually starts.
  const linked = useRef<string | null | undefined>(undefined);

  const redeem = async (value: string) => {
    const r = await cmd.run((c) => c.redeemAccessCode(value));
    if (r) {
      setCode("");
      setJustEnabled(true);
      access.reload();
    }
    setOpen(true); // confirm success, or show what went wrong
  };

  useEffect(() => {
    if (linked.current === undefined) linked.current = takeCodeFromUrl();
    const value = linked.current;
    if (!value) return;
    // Started from a timer (not synchronously in the effect); a re-run before it fires reschedules it.
    const t = setTimeout(() => {
      linked.current = null;
      void redeem(value);
    }, 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const info = access.data;
  const on = info?.tier === "EVALUATOR";
  useEffect(() => {
    if (!prompt || access.loading || on || linked.current) return;
    const t = setTimeout(() => {
      setPrompting(true);
      setOpen(true);
    }, 0);
    return () => clearTimeout(t);
  }, [prompt, access.loading, on]);
  const close = () => {
    setOpen(false);
    setJustEnabled(false);
    setPrompting(false);
    cmd.clearError();
  };
  // From the landing prompt, either choice goes on to the company catalog.
  const proceed = () => {
    const from = prompting;
    close();
    if (from) router.push("/demo/");
  };
  const band = variant === "band";

  return (
    <>
      {band ? (
        <button className="band-btn band-limits" onClick={() => setOpen(true)} aria-haspopup="dialog" data-testid="demo-limits" disabled={access.loading}>
          {on && <span className="access-dot" aria-hidden="true" />}
          {on ? `Evaluator access · until ${accessUntil(info)}` : "Public demo · limits"}
        </button>
      ) : on ? (
        <button className="access-chip" onClick={() => setOpen(true)} data-testid="evaluator-access" aria-haspopup="dialog">
          <span className="access-dot" aria-hidden="true" />
          Evaluator access<span className="access-until"> · until {accessUntil(info)}</span>
        </button>
      ) : (
        <button className="btn btn-primary access-open" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-label="Evaluator access" disabled={access.loading}>
          <KeyIcon />
          <span className="access-label">
            Evaluator<span className="access-word"> access</span>
          </span>
        </button>
      )}
      <Dialog
        open={open}
        title={on ? "Evaluator access is on" : prompting ? "Do you have evaluator access?" : band ? "Public demo limits" : "Evaluator access"}
        onClose={close}
        footer={
          on ? (
            <>
              <button
                className="btn"
                disabled={cmd.pending}
                onClick={() =>
                  void cmd.run(async (c) => {
                    const r = await c.leaveAccess();
                    setJustEnabled(false);
                    access.reload();
                    return r;
                  })
                }
              >
                Stop using code
              </button>
              <button className="btn btn-primary" onClick={proceed}>
                {justEnabled && !band ? "Choose a company" : "Done"}
              </button>
            </>
          ) : (
            <>
              <button className="btn" type="button" onClick={proceed} data-testid={prompting ? "continue-public" : undefined}>
                {prompting ? "Continue without evaluator access" : band ? "Close" : "Cancel"}
              </button>
              <button className="btn btn-primary" type="submit" form={`${id}-form`} disabled={cmd.pending || !code.trim()}>
                {cmd.pending ? "Checking…" : "Use code"}
              </button>
            </>
          )
        }
      >
        {on ? (
          <div className="stack-s" data-testid="evaluator-access-on">
            <p>
              Your demo runs in this browser use the evaluator allowance: higher daily limits for judging, until <strong>{accessUntil(info)}</strong>.
            </p>
            <p className="small muted">Every company you open from here, including fresh demos, keeps this access. On another device, enter the code again.</p>
            {band && usage.data && <Limits usage={usage.data} />}
          </div>
        ) : (
          <form
            id={`${id}-form`}
            className="stack-s"
            onSubmit={(e) => {
              e.preventDefault();
              if (code.trim()) void redeem(code.trim());
            }}
          >
            {band && usage.data && <Limits usage={usage.data} />}
            <p className="small muted" id={`${id}-help`}>
              {prompting
                ? "If you're judging WorkWeave, enter the code you were given for higher daily limits."
                : "Judges get higher daily limits with the code they were given. Public visitors don't need one."}
            </p>
            <label htmlFor={`${id}-code`} className="small">
              Access code
            </label>
            <input
              id={`${id}-code`}
              type="text"
              className="access-input"
              aria-describedby={`${id}-help`}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="WW-XXXX-XXXX-XXXX-XXXX"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={64}
            />
            {prompting && (
              <div className="notice notice-info" role="note" data-testid="public-limits">
                <span className="notice-title">Continuing without a code</span>
                <span>The public demo has daily limits for each demo workspace:</span>
                {usage.data ? <UsageList usage={usage.data} /> : <span className="small muted">Loading the limits…</span>}
                <span className="small">
                  There&apos;s also a shared daily total for all public visitors. When a limit is reached, typing still works and everything you did is kept; limits reset at{" "}
                  {usage.data ? resetTime(usage.data.resets_at) : "midnight UTC"}.
                </span>
              </div>
            )}
          </form>
        )}
        {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      </Dialog>
    </>
  );
}

/** The limits section of the header dialog: this run's use, and when it resets. */
function Limits({ usage }: { usage: DemoUsage }) {
  return (
    <section className="stack-s" aria-label="Today's limits">
      <p className="small">
        <b>{usage.tier === "EVALUATOR" ? "Evaluator limits" : "Public demo limits"}</b>, {usage.run_open ? "used by this demo workspace today" : "per demo workspace each day"}:
      </p>
      <UsageList usage={usage} />
      <p className="small muted">Resets at {resetTime(usage.resets_at)}. Reaching a limit never loses your work; typing keeps working.</p>
    </section>
  );
}
