"use client";

/**
 * Optional page tours (owner, 2026-10-11). The first time a persona opens a module in a demo run, a
 * short offer appears at the top of the page: take the tour or skip it. Either choice is remembered
 * for that run and persona in this browser, so a fresh demo (a new run) offers it again. "Page tour"
 * in the top bar replays it any time. The tour dims the page, outlines one part at a time and explains
 * it; Esc or "End tour" stops it. Nothing here touches the backend.
 */
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRuntime, useSession } from "@/lib/preview/client-context";
import { TOURS, type TourKey, type TourStep } from "./tours";

const REPLAY = "ww:tour-replay";
/** The tour in progress. Kept outside React state: the page's layout can re-mount this component
 * while its data loads, and a running tour must survive that. */
let active: TourKey | null = null;

function storageKey(workspace: string, persona: string, tour: TourKey) {
  return `ww.tour.v1.${workspace}.${persona}.${tour}`;
}

/** "seen" when the offer was answered; unknown storage counts as seen, so the offer never nags. */
function seen(key: string): boolean {
  try {
    return window.localStorage.getItem(key) !== null;
  } catch {
    return true;
  }
}

function remember(key: string, value: "TAKEN" | "SKIPPED"): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* not remembered: the offer may appear again */
  }
}

/** Asks the tour on the current page to start (the top bar's "Page tour" button). */
export function replayTour(): void {
  window.dispatchEvent(new Event(REPLAY));
}

export function ModuleTour({ tour }: { tour: TourKey }) {
  const { session } = useSession();
  const key = session ? storageKey(session.workspace_id, session.persona.employee_id, tour) : null;
  const [offer, setOffer] = useState(false);
  const [running, setRunningState] = useState(() => active === tour);
  const setRunning = useCallback(
    (on: boolean) => {
      active = on ? tour : null;
      setRunningState(on);
    },
    [tour],
  );
  const def = TOURS[tour];

  useEffect(() => {
    if (!key) return;
    const t = setTimeout(() => setOffer(!seen(key)), 0); // after mount: storage isn't read during render
    return () => clearTimeout(t);
  }, [key]);

  useEffect(() => {
    const start = () => {
      setOffer(false);
      setRunning(true);
    };
    window.addEventListener(REPLAY, start);
    return () => window.removeEventListener(REPLAY, start);
  }, [setRunning]);

  const answer = (value: "TAKEN" | "SKIPPED") => {
    if (key) remember(key, value);
    setOffer(false);
    if (value === "TAKEN") setRunning(true);
  };

  return (
    <>
      {offer && (
        <div className="tour-offer" role="region" aria-label={`${def.name} tour`} data-testid="tour-offer">
          <div>
            <b>New to {def.name}?</b>
            <span className="small"> A short tour shows what each part of this page is for. It&apos;s optional.</span>
          </div>
          <div className="row">
            <button className="btn btn-small btn-primary" onClick={() => answer("TAKEN")}>
              Take the tour
            </button>
            <button className="btn btn-small" onClick={() => answer("SKIPPED")}>
              Skip tour
            </button>
          </div>
        </div>
      )}
      {running && <TourOverlay name={def.name} steps={def.steps} onEnd={() => setRunning(false)} />}
    </>
  );
}

type Rect = { top: number; left: number; width: number; height: number };
const PAD = 6;
const GAP = 12;
const CARD_W = 340;

function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function TourOverlay({ name, steps: all, onEnd }: { name: string; steps: TourStep[]; onEnd: () => void }) {
  const id = useId();
  // Only the steps whose part of the page is actually shown (role, data and screen size vary). The
  // page may still be loading when the tour starts, so it waits briefly for its parts to appear.
  const [steps, setSteps] = useState<TourStep[] | null>(null);
  useEffect(() => {
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const pick = () => {
      const shown = all.filter((s) => !s.target || document.querySelector(s.target));
      if (shown.some((s) => s.target) || ++tries > 25) setSteps(shown);
      else timer = setTimeout(pick, 200);
    };
    timer = setTimeout(pick, 0);
    return () => clearTimeout(timer);
  }, [all]);
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const [cardH, setCardH] = useState(180);
  const card = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const opener = useRef<Element | null>(null);
  const preview = useRuntime().mode === "preview";
  const step = steps?.[i];
  const text = step && preview && step.preview ? step.preview : step; // what the card says

  const measure = useCallback(() => {
    const el = step?.target ? document.querySelector(step.target) : null;
    if (!el) return setRect(null);
    const r = el.getBoundingClientRect();
    setRect({ top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 });
  }, [step]);

  useEffect(() => {
    opener.current = document.activeElement;
    return () => (opener.current as HTMLElement | null)?.focus?.(); // back to where the tour started
  }, []);

  useLayoutEffect(() => {
    const el = step?.target ? document.querySelector(step.target) : null;
    el?.scrollIntoView({ block: "center", behavior: reducedMotion() ? "auto" : "smooth" });
    const frame = requestAnimationFrame(measure); // after the scroll starts; scrolling keeps it in place
    heading.current?.focus();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step, measure]);

  useLayoutEffect(() => {
    if (card.current) setCardH(card.current.offsetHeight);
  }, [i, rect]);

  const total = steps?.length ?? 0;
  const next = () => (i + 1 < total ? setI(i + 1) : onEnd());
  const back = () => setI(Math.max(0, i - 1));
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") onEnd();
    else if (e.key === "ArrowRight") next();
    else if (e.key === "ArrowLeft") back();
    else if (e.key === "Tab") {
      // Keep keyboard focus inside the tour card while it's open.
      const f = card.current?.querySelectorAll<HTMLElement>("button");
      if (!f?.length) return;
      const first = f[0]!, last = f[f.length - 1]!;
      const wrapTo = e.shiftKey && document.activeElement === first ? last : !e.shiftKey && document.activeElement === last ? first : null;
      if (wrapTo) {
        e.preventDefault();
        wrapTo.focus();
      }
    }
  };

  useEffect(() => {
    if (steps && !steps.length) onEnd(); // nothing of this tour is on the page right now
  }, [steps, onEnd]);
  if (!step) return null;

  // Below the outlined part if it fits, otherwise above, otherwise centred; small screens dock it at the bottom.
  const vw = window.innerWidth, vh = window.innerHeight;
  const narrow = vw < 640;
  let pos: React.CSSProperties;
  if (narrow) pos = { left: 16, right: 16, bottom: 16 };
  else if (!rect) pos = { left: Math.max(16, (vw - CARD_W) / 2), top: Math.max(16, (vh - cardH) / 2), width: CARD_W };
  else {
    const left = Math.min(Math.max(16, rect.left), vw - CARD_W - 16);
    const below = rect.top + rect.height + GAP;
    const above = rect.top - GAP - cardH;
    const besideTop = Math.min(Math.max(16, rect.top), vh - cardH - 16);
    if (below + cardH <= vh - 16) pos = { left, top: below, width: CARD_W };
    else if (above >= 16) pos = { left, top: above, width: CARD_W };
    // A part taller than the screen: put the card beside it rather than over it.
    else if (rect.left - GAP - CARD_W >= 16) pos = { left: rect.left - GAP - CARD_W, top: besideTop, width: CARD_W };
    else if (rect.left + rect.width + GAP + CARD_W <= vw - 16) pos = { left: rect.left + rect.width + GAP, top: besideTop, width: CARD_W };
    else pos = { left, top: Math.max(16, vh - cardH - 16), width: CARD_W };
  }

  return createPortal(
    <div className="tour-layer" onKeyDown={onKey}>
      {rect ? <div className="tour-spot" style={rect} aria-hidden="true" /> : <div className="tour-dim" aria-hidden="true" />}
      <div ref={card} className="tour-card" role="dialog" aria-modal="true" aria-labelledby={`${id}-t`} aria-describedby={`${id}-b`} style={pos}>
        <p className="tour-count small muted">
          {name} tour · {i + 1} of {total}
        </p>
        <h2 id={`${id}-t`} ref={heading} tabIndex={-1}>
          {text!.title}
        </h2>
        <p id={`${id}-b`}>{text!.body}</p>
        <div className="row-between">
          <button className="link-btn" onClick={onEnd}>
            End tour
          </button>
          <span className="row">
            {i > 0 && (
              <button className="btn btn-small" onClick={back}>
                Back
              </button>
            )}
            <button className="btn btn-small btn-primary" onClick={next}>
              {i + 1 < total ? "Next" : "Finish"}
            </button>
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
