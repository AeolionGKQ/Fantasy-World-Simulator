import type { ReactNode } from "react";
import { Icon, type IconName } from "../../../components/Icon";

/** Empty game tab: an icon for what the tab collects, a title and one line of guidance. */
export function GameEmpty({ title, icon, children }: { title: string; icon: IconName; children: ReactNode }) {
  return <div className="game-empty"><span className="glyph-badge" aria-hidden="true"><Icon name={icon} /></span><h3>{title}</h3><p>{children}</p></div>;
}
