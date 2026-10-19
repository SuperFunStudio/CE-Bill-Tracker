'use client';
import { useEffect, useState } from 'react';

/**
 * "tap" on touch-first devices, "click" elsewhere — for instructional copy ("tap a country to filter").
 * Starts as "click" so the static prerender is stable, then corrects after mount from the primary
 * pointer type (a coarse pointer = a finger).
 */
export function useTapOrClick(): 'tap' | 'click' {
  const [verb, setVerb] = useState<'tap' | 'click'>('click');
  useEffect(() => {
    if (window.matchMedia?.('(pointer: coarse)').matches) setVerb('tap');
  }, []);
  return verb;
}
