import { useState } from "react";
import { mediaPictureSources, type MediaPaths } from "../types";

/** World artwork with portrait/landscape sources; falls back to a titled placeholder when missing. */
export function ResponsiveArtwork({ item, alt, kind }: { item: MediaPaths; alt: string; kind: "种族" | "地点" | "势力" }) {
  const [imageAvailable, setImageAvailable] = useState(true);
  const sources = mediaPictureSources(item);
  return (
    <figure className="responsive-artwork">
      {imageAvailable ? (
        <picture>
          {sources.map((source) => <source key={source.media} media={source.media} srcSet={source.srcSet} />)}
          <img src={item.image_landscape_path} alt={alt} onError={() => setImageAvailable(false)} />
        </picture>
      ) : (
        <div className="responsive-artwork-placeholder" role="img" aria-label={`${alt}占位，图片尚未提供`}>
          <span aria-hidden="true">◇</span>
          <strong>{alt.replace(`${kind}设定图`, "")}</strong>
          <small>{kind}设定图待补充</small>
        </div>
      )}
    </figure>
  );
}
