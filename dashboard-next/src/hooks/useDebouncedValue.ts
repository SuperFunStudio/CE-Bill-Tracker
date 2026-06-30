'use client';
import { useEffect, useState } from 'react';

/** Returns `value` after it has stopped changing for `delayMs` — so type-as-you-go inputs don't
 *  fire a network request on every keystroke. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
