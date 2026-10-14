import type { ReactNode } from "react";

export function GameEmpty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="game-empty"><span aria-hidden="true">◇</span><h3>{title}</h3><p>{children}</p></div>;
}
