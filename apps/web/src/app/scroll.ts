import { prefersReducedMotion } from "./viewTransition";

/**
 * If the element's top has scrolled above the sticky toolbar, scrolls it back to just below it.
 * Use "instant" inside a view transition update so the new snapshot is taken at the final position.
 */
export function scrollIntoViewIfAbove(selector: string, behavior: "instant" | "smooth" = "instant") {
  const element = document.querySelector<HTMLElement>(selector);
  if (!element) return;
  const toolbar = document.querySelector<HTMLElement>(".toolbar")?.offsetHeight ?? 0;
  const top = element.getBoundingClientRect().top;
  if (top >= toolbar) return;
  window.scrollTo({ top: window.scrollY + top - toolbar - 16, behavior: behavior === "smooth" && !prefersReducedMotion() ? "smooth" : "instant" });
}
