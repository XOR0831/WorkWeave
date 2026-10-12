/**
 * Echo filter for voice interruption on speakers.
 *
 * While a reply is read aloud, the microphone can pick the tutor's own voice back up. Treat speech
 * as the learner barging in only when the transcript contains a run of consecutive words that are
 * NOT in the reply being spoken (default: two). The tutor's echo is made of the reply's own words,
 * so it doesn't trigger an interruption.
 */
const words = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^\p{L}\p{N}'\s]/gu, " ")
    .split(/\s+/)
    .filter(Boolean);

export function isBargeIn(transcript: string, replyText: string, minNovelWords = 2): boolean {
  const reply = new Set(words(replyText));
  let run = 0;
  for (const w of words(transcript)) {
    run = reply.has(w) ? 0 : run + 1;
    if (run >= minNovelWords) return true;
  }
  return false;
}
