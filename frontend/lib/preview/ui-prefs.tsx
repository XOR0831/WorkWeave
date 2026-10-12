"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

/** Reviewer-only presentation toggles. Not product preferences. */
interface UiPrefs {
  simulateVoice: boolean;
  setSimulateVoice(v: boolean): void;
}

const Ctx = createContext<UiPrefs>({ simulateVoice: false, setSimulateVoice: () => {} });

export function UiPrefsProvider({ children }: { children: ReactNode }) {
  const [simulateVoice, setSimulateVoice] = useState(false);
  return <Ctx.Provider value={{ simulateVoice, setSimulateVoice }}>{children}</Ctx.Provider>;
}

export const useUiPrefs = () => useContext(Ctx);
