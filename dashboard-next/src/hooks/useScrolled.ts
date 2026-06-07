'use client';
import { useEffect, useState } from 'react';

/**
 * True once the app's scroll container (the <main> element, which owns the scroll —
 * falling back to the window) has scrolled past `threshold` pixels.
 */
export function useScrolled(threshold = 140): boolean {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const main = document.querySelector('main');
    const target: HTMLElement | Window = main ?? window;
    const read = () => (main ? main.scrollTop : window.scrollY);
    const onScroll = () => setScrolled(read() > threshold);
    onScroll();
    target.addEventListener('scroll', onScroll, { passive: true });
    return () => target.removeEventListener('scroll', onScroll);
  }, [threshold]);

  return scrolled;
}
