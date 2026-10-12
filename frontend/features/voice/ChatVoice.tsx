"use client";

/**
 * Voice for the handover copilot and Exit KT conversations (ADR-045): the Companion's transport, as
 * a drop-in. Tap-to-talk (or opt-in hands-free) fills the composer; the assistant's saved replies can
 * be read aloud, new replies only, never history on opening. Transcripts are sent as text; audio is
 * never stored. Preferences are the same per-browser voice settings as onboarding and the Companion.
 */
import { useState } from "react";
import { Composer } from "@/components/chat";
import { useClient, useResource, useRuntime } from "@/lib/preview/client-context";
import { VoiceComposer } from "@/features/onboarding/VoiceComposer";
import { useReadAloud, type SpeakableMessage } from "@/features/companion/useReadAloud";
import { LiveListener, MicCapture, type ListenMode, type VoiceGrant } from "@/lib/voice/live-listener";
import { playCue, prefersQuiet } from "@/lib/voice/cues";
import { micPermission } from "@/lib/voice/mic-permission";
import { SPEEDS, loadPrefs, savePrefs, type VoicePrefs } from "@/lib/voice/prefs";
import { resetTime } from "@/lib/limits";
import type { WorkWeaveClient } from "@/lib/clients/WorkWeaveClient";
import type { PcmStream } from "@/lib/voice/stream-player";

export interface ChatVoiceChannel {
  grant: (c: WorkWeaveClient, mode: ListenMode) => Promise<VoiceGrant>;
  speech: (c: WorkWeaveClient, message_id: string) => Promise<PcmStream>;
}

export const HANDOVER_VOICE: ChatVoiceChannel = { grant: (c, m) => c.getHandoverVoiceListenGrant(m), speech: (c, id) => c.streamHandoverReplySpeech(id) };
export const KT_VOICE: ChatVoiceChannel = { grant: (c, m) => c.getKtVoiceListenGrant(m), speech: (c, id) => c.streamKtReplySpeech(id) };

/** The assistant's own saved replies (engine answers), never the person's words or system notices. */
const engineReply = (m: SpeakableMessage) => m.sender === "AI";

export function useChatVoice(opts: { channel: ChatVoiceChannel; conversationId: string | undefined; messages: SpeakableMessage[] | undefined; enabled?: boolean }) {
  const client = useClient();
  const api = useRuntime().mode === "http";
  const caps = useResource((c) => (api ? c.getCapabilities() : Promise.resolve(null)), [api]);
  const available = api && caps.data?.voice_adapter === "AVAILABLE";
  const [prefs, setPrefs] = useState<VoicePrefs>(() => loadPrefs(prefersQuiet()));
  const updatePrefs = (patch: Partial<VoicePrefs>) => setPrefs(savePrefs(patch, prefersQuiet()));
  const voice = useReadAloud({
    client,
    enabled: api && (opts.enabled ?? true),
    sessionId: opts.conversationId,
    transcript: opts.messages,
    readAloud: prefs.readAloud,
    voiceAvailable: available,
    capsLoading: caps.loading,
    speed: prefs.speed,
    stream: (id) => opts.channel.speech(client, id),
    isReply: engineReply,
    opening: false,
  });
  return { api, client, available, capsLoading: caps.loading, prefs, updatePrefs, voice, channel: opts.channel };
}

export type ChatVoice = ReturnType<typeof useChatVoice>;

/** "Listen" / "Stop" under an assistant reply. */
export function ListenButton({ cv, m }: { cv: ChatVoice; m: SpeakableMessage }) {
  const { voice } = cv;
  if (!cv.available || voice.limit || !engineReply(m)) return null;
  const on = voice.speaking && voice.speakingId === m.message_id;
  return (
    <button className="link-btn" onClick={() => (on ? voice.stop() : void voice.play(m))} aria-label={on ? "Stop reading this reply" : "Listen to this reply"}>
      {on ? "Stop" : "Listen"}
    </button>
  );
}

/** Read-aloud switch, voice interrupt, speed, and plain limit/error lines. */
export function ReadAloudControls({ cv }: { cv: ChatVoice }) {
  const { voice, prefs, updatePrefs, available } = cv;
  if (!cv.api) return null;
  return (
    <div className="row" style={{ gap: 12, padding: "0 14px", flexWrap: "wrap" }}>
      <label className="small row" style={{ gap: 6 }}>
        <input type="checkbox" role="switch" checked={prefs.readAloud && !voice.limit} disabled={!available || Boolean(voice.limit)} onChange={(e) => updatePrefs({ readAloud: e.target.checked })} />
        Read replies aloud
      </label>
      <label className="small row" style={{ gap: 6 }} title="Speaking over a reply stops it. Works best with headphones; on speakers the reply can occasionally interrupt itself.">
        <input type="checkbox" role="switch" checked={prefs.voiceInterrupt} disabled={!available || !prefs.readAloud} onChange={(e) => updatePrefs({ voiceInterrupt: e.target.checked })} />
        Interrupt by voice
      </label>
      <label className="small row" style={{ gap: 6 }}>
        Speed
        <select value={prefs.speed} disabled={!available} onChange={(e) => updatePrefs({ speed: Number(e.target.value) as VoicePrefs["speed"] })}>
          {SPEEDS.map((x) => (
            <option key={x} value={x}>
              {x}×
            </option>
          ))}
        </select>
      </label>
      {voice.speaking && (
        <button className="btn btn-small" onClick={voice.stop}>
          Stop reading
        </button>
      )}
      {voice.limit && available && (
        <span className="small muted" role="status">
          Replies are text-only for now: reading aloud has reached its {voice.limit.scope === "RUN" ? "limit for this demo workspace" : "shared demo limit"} today. Back at {resetTime(voice.limit.resets_at)}.
        </span>
      )}
      {voice.error && !voice.limit && (
        <span className="small" role="alert">
          {voice.error}
        </span>
      )}
    </div>
  );
}

/** The composer with tap-to-talk in API mode; the plain composer in the preview. */
export function ChatVoiceComposer({
  cv,
  label,
  onSend,
  pending,
  placeholder,
  disabled,
}: {
  cv: ChatVoice;
  label: string;
  onSend: (text: string, kind: "TEXT" | "VOICE_TRANSCRIPT") => Promise<boolean>;
  pending?: boolean;
  placeholder?: string;
  disabled?: boolean;
}) {
  const { voice, prefs, updatePrefs } = cv;
  if (!cv.api) return <Composer label={label} onSend={onSend} pending={pending} placeholder={placeholder} disabled={disabled} />;
  return (
    <VoiceComposer
      label={label}
      onSend={onSend}
      pending={pending}
      disabled={disabled}
      placeholder={placeholder}
      voiceAvailable={cv.available}
      unavailableReason={cv.capsLoading ? "Checking voice…" : "Voice isn't configured on this server."}
      speaking={voice.speaking}
      speakingText={voice.speakingText}
      voiceInterrupt={prefs.voiceInterrupt}
      onInterrupt={voice.stop}
      prefs={prefs}
      onPrefsChange={updatePrefs}
      playCue={playCue}
      micPermission={micPermission}
      getGrant={(mode) => cv.channel.grant(cv.client, mode)}
      createListener={(grant, events) => new LiveListener(grant, events, { audio: new MicCapture() })}
    />
  );
}
