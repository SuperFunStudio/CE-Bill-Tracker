'use client';
import { useEffect, useState } from 'react';

/**
 * Types phrases out one character at a time as a search box's placeholder. Shared by the two surfaces
 * that host the ask bar: the homepage (rotating example questions — a hint that the bar answers real
 * questions, not just keyword filters) and /ask (the same examples when idle, and the working narration
 * below while a question is in flight).
 *
 * Runs only while `active`. Types with an eased, human rhythm, holds long enough to read, then the whole
 * line vanishes at once (no backspacing). In idle mode a cursor blinks for a beat before the next phrase;
 * in `working` mode the next line starts immediately and holds for less time — a pause with an empty box
 * would read as "stalled" when the point is to show that something is happening.
 *
 * Returns the display string (typed text + cursor); '' when idle so the caller can fall back to a static
 * placeholder. `phrases` must be a stable reference (a module-level constant) — the typing effect keys
 * off its identity and restarts when it changes.
 */
export function useTypedPlaceholder(phrases: string[], active: boolean, working = false): string {
  const [text, setText] = useState('');
  const [cursorOn, setCursorOn] = useState(true);
  useEffect(() => {
    if (!active) { setText(''); setCursorOn(true); return; }
    const holdMs = working ? 1500 : 3000;
    let phrase = 0, char = 0;
    let timer: ReturnType<typeof setTimeout>;
    // Ease-out per-character delay: a touch deliberate at the start of a question, quickening as it
    // flows, with an extra beat after punctuation. Reads as typed by a person, not a metronome.
    const charDelay = (s: string, i: number) => {
      const prev = s[i - 1];
      if (prev === ',') return 240;
      if (prev === '.' || prev === '?') return 300;
      const p = i / s.length;              // 0 → 1 across the question
      const ease = 1 - 0.6 * p * (2 - p);  // ease-out: ~1.0 early → ~0.4 late
      return 34 + 46 * ease;               // ~80ms at the start → ~52ms by the end
    };
    const typeNext = () => {
      const current = phrases[phrase % phrases.length];
      char++;
      setText(current.slice(0, char));
      if (char >= current.length) { timer = setTimeout(vanish, holdMs); return; }
      timer = setTimeout(typeNext, charDelay(current, char));
    };
    const vanish = () => {                                  // clear the whole line at once
      setText('');
      if (working) { phrase++; char = 0; timer = setTimeout(typeNext, 260); return; }
      blink(0);
    };
    const blink = (n: number) => {
      if (n >= 3) {                                         // ~3 toggles, then the next phrase
        setCursorOn(true);
        phrase++; char = 0;
        timer = setTimeout(typeNext, 260);
        return;
      }
      setCursorOn(c => !c);
      timer = setTimeout(() => blink(n + 1), 420);
    };
    timer = setTimeout(typeNext, 650);
    return () => clearTimeout(timer);
  }, [active, phrases, working]);
  // Cursor stays solid while typing/holding; the blink state only toggles in the gap between phrases.
  // A figure space (U+2007) for the "off" frame keeps the placeholder width steady.
  return active ? text + (cursorOn ? '▏' : ' ') : '';
}

/**
 * What the answer is actually doing while the reader waits — a deep read of up to 100 full bill texts
 * runs the better part of a minute, and a frozen "Thinking…" for that long reads as broken. Module scope
 * so the identity is stable across renders.
 */
export const WORKING_PHRASES = [
  'Flipping through pages…',
  'Reviewing relevant statutes…',
  'Checking sources…',
  'Comparing across the corpus…',
  'Identifying trends…',
  'Distilling detailed answers…',
  'Synthesizing a comprehensive response…',
];
