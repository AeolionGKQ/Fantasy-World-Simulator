import { useState, type ImgHTMLAttributes } from "react";

/** <img> that fades in once it has loaded instead of painting in abruptly (motion.css `.fade-image`). */
export function FadeImage({ className = "", onLoad, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState(false);
  return (
    <img
      {...props}
      className={`fade-image ${loaded ? "loaded" : ""} ${className}`.trim()}
      onLoad={(event) => { setLoaded(true); onLoad?.(event); }}
    />
  );
}
