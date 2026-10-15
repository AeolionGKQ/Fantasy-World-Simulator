import { useCallback } from "react";

/**
 * Callback ref that focuses the element when it mounts, without scrolling it into view.
 * Use instead of `autoFocus`, which scrolls the page to the field when a wizard step mounts.
 * Works for fields that appear later too (e.g. a custom-value input revealed by a choice).
 */
export function useAutoFocus<T extends HTMLElement>() {
  return useCallback((node: T | null) => {
    node?.focus({ preventScroll: true });
  }, []);
}
