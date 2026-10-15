import { useEffect, useState } from "react";

/**
 * Keeps the last non-empty value rendered for `exitMs` after it is cleared, so an element can play
 * its exit animation (`leaving`) before it unmounts.
 */
export function usePresence<T>(value: T | null | undefined, exitMs = 160) {
  const [current, setCurrent] = useState<T | null>(value ?? null);
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    if (value) {
      setCurrent(value);
      setLeaving(false);
      return;
    }
    setLeaving(true);
    const timer = window.setTimeout(() => {
      setCurrent(null);
      setLeaving(false);
    }, exitMs);
    return () => window.clearTimeout(timer);
  }, [value, exitMs]);
  return { current, leaving };
}
