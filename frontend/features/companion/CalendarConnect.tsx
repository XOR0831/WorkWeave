"use client";

import { useEffect, useRef, useState } from "react";
import { useClient } from "@/lib/preview/client-context";

const POLL_MS = 2000;
const GIVE_UP_MS = 3 * 60 * 1000;

/**
 * "Connect Google Calendar" under the reply that needed it (ADR-034). Browsers only allow a popup
 * opened by a click, so the sign-in opens from this button. The page then checks the connection every
 * few seconds; once it is connected the popup closes and the question is asked again.
 */
export function CalendarConnect({ connect, onConnected }: { connect: { connect_url: string; retry_text: string }; onConnected: (retryText: string) => void }) {
  const client = useClient();
  const [phase, setPhase] = useState<"idle" | "waiting" | "blocked" | "unfinished" | "timeout">("idle");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const popup = useRef<Window | null>(null);

  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };
  useEffect(() => stop, []);

  const start = () => {
    stop();
    popup.current = window.open(connect.connect_url, "ww-google-calendar", "popup,width=520,height=680");
    setPhase(popup.current ? "waiting" : "blocked");
    const since = Date.now();
    timer.current = setInterval(() => {
      void client
        .getCalendarStatus()
        .then((st) => {
          if (st.connected) {
            stop();
            popup.current?.close();
            setPhase("idle");
            onConnected(connect.retry_text);
          } else if (popup.current?.closed) {
            stop();
            setPhase("unfinished");
          } else if (Date.now() - since > GIVE_UP_MS) {
            stop();
            setPhase("timeout");
          }
        })
        .catch(() => undefined); // a missed check is retried on the next tick
    }, POLL_MS);
  };

  return (
    <div className="notice notice-info" role="note" style={{ margin: "0 14px" }} data-testid="calendar-connect">
      <span className="notice-title">Connect Google Calendar</span>
      <span>
        {phase === "waiting"
          ? "Finish signing in to Google in the window that opened. I'll ask again as soon as it's connected."
          : phase === "blocked"
            ? "Your browser blocked the sign-in window. Open it here instead; I'll ask again once it's connected."
            : phase === "unfinished"
              ? "The sign-in window was closed before Google Calendar was connected."
              : phase === "timeout"
                ? "Google Calendar still isn't connected."
                : "Sign in with the Google account set up for this demo."}
      </span>
      <span className="row" style={{ marginTop: 8 }}>
        {phase === "blocked" ? (
          <a className="btn btn-small btn-primary" href={connect.connect_url} target="_blank" rel="noopener noreferrer">
            Open Google sign-in
          </a>
        ) : (
          <button className="btn btn-small btn-primary" disabled={phase === "waiting"} onClick={start}>
            {phase === "waiting" ? "Waiting for Google…" : phase === "idle" ? "Connect Google Calendar" : "Try again"}
          </button>
        )}
      </span>
    </div>
  );
}
