"use client";

import { useEffect, useRef, useState } from "react";
import { ReplySpeaker } from "@/lib/voice/live-listener";
import { limitOf } from "@/lib/limits";
import type { WorkWeaveClient } from "@/lib/clients/WorkWeaveClient";
import type { PcmStream } from "@/lib/voice/stream-player";
import type { ApiError, LimitInfo, WorkMessage } from "@/types/contracts";

/** The opening brief of a work session is read once in this tab; a reload never replays it. */
const BRIEF = "ww.voice.companion-brief";

function briefRead(sessionId: string): boolean {
  try {
    return window.sessionStorage.getItem(BRIEF) === sessionId;
  } catch {
    return true; // storage unavailable: never read history aloud automatically
  }
}

function markBriefRead(sessionId: string): void {
  try {
    window.sessionStorage.setItem(BRIEF, sessionId);
  } catch {
    /* the brief simply isn't remembered */
  }
}

/** Browsers block sound until someone has interacted with the page (e.g. a hard reload). */
function soundAllowed(): boolean {
  const ua = (navigator as Navigator & { userActivation?: { hasBeenActive: boolean } }).userActivation;
  return ua ? ua.hasBeenActive : true;
}

type Reply = Pick<WorkMessage, "message_id" | "text">;
/** Any conversation's messages: what the hook needs to pick the replies to read. */
export type SpeakableMessage = Pick<WorkMessage, "message_id" | "text"> & { sender: string; provenance?: string };

const companionReply = (m: SpeakableMessage) => m.sender === "AI" && (m.provenance === "WORK_ENGINE" || m.provenance === "BACKEND_RECORD");

/**
 * Work Companion read-aloud (API mode), the same behaviour as onboarding's tutor (ADR-034):
 * new replies from the AI engine are read when "Read replies aloud" is on, including the session's
 * opening brief the first time it appears. History already on screen at a reload is never replayed.
 * If the browser hasn't allowed sound yet, the brief waits for a tap instead of playing silently.
 * Other conversations (ADR-045: handover copilot, Exit KT copilot and interview) pass their own
 * `stream`, which replies count (`isReply`) and `opening: false` (nothing is read on opening).
 */
export function useReadAloud(opts: {
  client: WorkWeaveClient;
  enabled: boolean;
  sessionId: string | undefined;
  transcript: SpeakableMessage[] | undefined;
  readAloud: boolean;
  voiceAvailable: boolean;
  capsLoading: boolean;
  speed: number;
  stream?: (message_id: string) => Promise<PcmStream>;
  isReply?: (m: SpeakableMessage) => boolean;
  /** Read a brand-new session's opening brief (the Companion's). */
  opening?: boolean;
}) {
  const { client, enabled, sessionId, transcript, readAloud, voiceAvailable, capsLoading, speed, isReply = companionReply, opening = true } = opts;
  const stream = opts.stream ?? ((id: string) => client.streamWorkReplySpeech(id));
  const [speaking, setSpeaking] = useState(false);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const [speakingText, setSpeakingText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState<LimitInfo | null>(null);
  const [briefWaiting, setBriefWaiting] = useState<Reply | null>(null);
  const speaker = useRef<ReplySpeaker | null>(null);
  const lastSpoken = useRef<string | null | undefined>(undefined);
  const freshBrief = useRef<string | null>(null);

  const stop = () => {
    speaker.current?.stop();
    setSpeaking(false);
    setSpeakingId(null);
  };

  const play = (reply: Reply) => {
    speaker.current ??= new ReplySpeaker();
    const sp = speaker.current;
    return stream(reply.message_id)
      .then((stream) => {
        setBriefWaiting(null);
        return sp.playStream(
          stream,
          {
            start: () => {
              setError(null);
              setSpeakingId(reply.message_id);
              setSpeakingText(reply.text);
              setSpeaking(true);
            },
            done: () => {
              setSpeaking(false);
              setSpeakingId(null);
            },
          },
          speed,
        );
      })
      .catch((e: { error?: ApiError }) => {
        setSpeaking(false);
        setSpeakingId(null);
        const hit = limitOf(e.error, "VOICE_SPEECH");
        if (hit) setLimit(hit);
        else setError(e.error?.message ?? "The reply couldn't be read aloud.");
      });
  };

  // The engine's replies and the companion's own notices ("Ticket #910 was assigned to you").
  const replies = (transcript ?? []).filter(isReply);
  const lastReply = replies[replies.length - 1];
  const canSpeak = enabled && readAloud && voiceAvailable && !limit;

  const seenSession = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!enabled || !transcript || !sessionId) return;
    if (seenSession.current !== sessionId) {
      // Another conversation (e.g. a different interview): what's already in it is history, not new.
      seenSession.current = sessionId;
      lastSpoken.current = undefined;
    }
    if (lastSpoken.current === undefined) {
      lastSpoken.current = lastReply?.message_id ?? null;
      // A brand-new session shows only the brief: read it once, the first time it appears in this tab.
      if (opening && lastReply && !transcript.some((m) => m.sender === "EMPLOYEE") && !briefRead(sessionId)) freshBrief.current = lastReply.message_id;
    }
    if (freshBrief.current && !capsLoading) {
      const id = freshBrief.current;
      freshBrief.current = null;
      markBriefRead(sessionId);
      if (lastReply?.message_id === id && canSpeak) {
        if (soundAllowed()) void play(lastReply);
        else void Promise.resolve(lastReply).then(setBriefWaiting); // after this render, like a play would
      }
      return;
    }
    if (!lastReply || lastReply.message_id === lastSpoken.current) return;
    lastSpoken.current = lastReply.message_id;
    if (canSpeak) void play(lastReply);
    else void Promise.resolve(null).then(setBriefWaiting); // a newer reply replaces the waiting brief
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, sessionId, transcript, lastReply?.message_id, canSpeak, capsLoading]);
  useEffect(() => () => speaker.current?.stop(), []);
  useEffect(() => speaker.current?.setRate(speed), [speed]);

  return { speaking, speakingId, speakingText, error, limit, briefWaiting, lastReply, play, stop };
}
