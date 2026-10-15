import { useCallback, useLayoutEffect, useRef } from "react";
import { useNavigate, type NavigateOptions, type To } from "react-router-dom";

/**
 * Which transition is running. motion.css reads it from <html data-vt> to decide which elements
 * get a view-transition-name, so names from different kinds of transition never collide.
 * No attribute means a route change started by React Router (Link/navigate with viewTransition).
 */
export type TransitionKind = "route" | "tab" | "step" | "turn" | "mode" | "world";
export type TransitionDirection = "forward" | "back";

let latest = 0;

export function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Runs `update` inside a view transition. `update` must change the DOM before it returns or
 * before its promise settles: wrap state changes in flushSync, or await a navigate() that uses
 * { flushSync: true }. Without browser support or with reduced motion it simply runs `update`.
 */
export function runViewTransition(kind: TransitionKind, update: () => void | Promise<void>, direction?: TransitionDirection) {
  if (typeof document.startViewTransition !== "function" || prefersReducedMotion()) {
    void update();
    return;
  }
  const root = document.documentElement;
  const id = ++latest;
  root.dataset.vt = kind;
  if (direction) root.dataset.vtDir = direction;
  else delete root.dataset.vtDir;
  const transition = document.startViewTransition(async () => { await update(); });
  // A newer transition skips this one; only the newest clears the attributes.
  void transition.finished.catch(() => undefined).finally(() => {
    if (id !== latest) return;
    delete root.dataset.vt;
    delete root.dataset.vtDir;
  });
}

/**
 * navigate() that animates the page change. Pass `direction` to run a directional "step" transition.
 * The returned function is stable. React Router's useNavigate() changes identity on every location
 * change inside descendant <Routes>, which made effects depending on it (the wizard's draft load)
 * re-run and re-show the loading state on every step.
 */
export function useAppNavigate() {
  const navigate = useNavigate();
  const latest = useRef(navigate);
  useLayoutEffect(() => { latest.current = navigate; }, [navigate]);
  return useCallback((to: To, options: NavigateOptions & { direction?: TransitionDirection } = {}) => {
    const { direction, ...rest } = options;
    if (direction) {
      runViewTransition("step", () => latest.current(to, { ...rest, flushSync: true }), direction);
      return;
    }
    void latest.current(to, { viewTransition: true, ...rest });
  }, []);
}
