import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type DependencyList } from "react";

interface IndicatorBox { x: number; y: number; width: number; height: number; visible: boolean }

/**
 * Positions one highlight element over the item matching `selector` inside the container, so the
 * highlight slides between items instead of jumping. The container must be the items' offsetParent
 * (position: relative) and the indicator must be absolutely positioned at its top-left.
 * The first placement does not animate; later moves do (CSS on `.animate`).
 */
export function useSlidingIndicator<T extends HTMLElement>(selector: string, deps: DependencyList) {
  const containerRef = useRef<T>(null);
  const [box, setBox] = useState<IndicatorBox | null>(null);
  const [animate, setAnimate] = useState(false);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const measure = () => {
      const item = container.querySelector<HTMLElement>(selector);
      if (!item) {
        // Keep the last position so the next appearance fades in place rather than sliding from 0.
        setBox((previous) => (previous ? { ...previous, visible: false } : null));
        return;
      }
      setBox({ x: item.offsetLeft, y: item.offsetTop, width: item.offsetWidth, height: item.offsetHeight, visible: true });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!box?.visible || animate) return;
    const frame = requestAnimationFrame(() => setAnimate(true));
    return () => cancelAnimationFrame(frame);
  }, [box, animate]);

  const style: CSSProperties | undefined = box
    ? { width: box.width, height: box.height, transform: `translate(${box.x}px, ${box.y}px)` }
    : undefined;
  const className = [box?.visible ? "visible" : "", animate ? "animate" : ""].filter(Boolean).join(" ");
  return { containerRef, indicator: { style, className } };
}
