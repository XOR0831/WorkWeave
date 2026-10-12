"use client";

import { useSyncExternalStore } from "react";

/**
 * Light / dark switch. Until someone chooses, the page follows the device setting (prefers-color-scheme);
 * a choice sets data-theme on <html> and is remembered in this browser only. THEME_SCRIPT applies a
 * remembered choice before the first paint, so the page doesn't flash the other theme.
 */
export const THEME_KEY = "workweave-theme";
type Theme = "light" | "dark";

export const THEME_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

function subscribe(listener: () => void) {
  listeners.add(listener);
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  media?.addEventListener?.("change", listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    media?.removeEventListener?.("change", listener);
    window.removeEventListener("storage", listener);
  };
}

function current(): Theme {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* storage blocked: the choice lasts for this page only */
  }
  emit();
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, current, () => null);
  if (theme === null) return null; // not known until the page runs in the browser
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" className="btn btn-small theme-toggle" onClick={() => setTheme(next)} aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      <span aria-hidden="true">{next === "dark" ? "☾" : "☀"}</span> {next === "dark" ? "Dark" : "Light"}
    </button>
  );
}
