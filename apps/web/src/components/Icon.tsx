import type { ReactNode } from "react";

export type IconName = "menu" | "plus" | "settings" | "upload" | "download" | "edit" | "trash" | "close"
  | "quill" | "info" | "alert" | "sparkle" | "bag" | "people" | "book" | "compass";

const paths: Record<IconName, ReactNode> = {
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  plus: <path d="M12 5v14M5 12h14" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
  upload: <><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" /><path d="M5 14v5h14v-5" /></>,
  download: <><path d="M12 4v12m0 0 4.5-4.5M12 16l-4.5-4.5" /><path d="M5 19h14" /></>,
  edit: <><path d="m4 20 4.2-1 10.6-10.6-3.2-3.2L5 15.8 4 20Z" /><path d="m13.8 7 3.2 3.2" /></>,
  trash: <><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7" /><path d="M10 11v5m4-5v5" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  /* Story not started yet: a writing quill. */
  quill: <><path d="M19.5 4.5C12 5.5 7 10.5 6.5 17.5" /><path d="M19.5 4.5c-.5 7-5.5 12-13 13" /><path d="M4 20l9.5-9.5" /></>,
  /* Notice bar: information / problem. */
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 7.5v.01" /></>,
  alert: <><path d="M12 3.8 2.6 20h18.8L12 3.8Z" /><path d="M12 10v4.5M12 17.4v.01" /></>,
  /* Something is being generated. */
  sparkle: <><path d="M11 3c.7 4.6 2.9 6.8 7.5 7.5-4.6.7-6.8 2.9-7.5 7.5-.7-4.6-2.9-6.8-7.5-7.5C8.1 9.8 10.3 7.6 11 3Z" /><path d="M19 15v5M16.5 17.5h5" /></>,
  /* Empty states: inventory, bonds, journal, page not found. */
  bag: <><path d="M5 8.5h14l-1.2 11.5H6.2L5 8.5Z" /><path d="M9 8.5V7a3 3 0 0 1 6 0v1.5" /></>,
  people: <><circle cx="9" cy="8.5" r="3" /><path d="M3.5 19.5c.6-3.3 2.7-5.2 5.5-5.2s4.9 1.9 5.5 5.2" /><circle cx="16.5" cy="9.5" r="2.4" /><path d="M16 14.4c2.5-.2 4.2 1.5 4.6 4.6" /></>,
  book: <><path d="M3.5 5.5c3-1 6-.8 8.5 1 2.5-1.8 5.5-2 8.5-1V19c-3-1-6-.8-8.5 1-2.5-1.8-5.5-2-8.5-1Z" /><path d="M12 6.5V20" /></>,
  compass: <><circle cx="12" cy="12" r="9" /><path d="m15.8 8.2-2.4 5.2-5.2 2.4 2.4-5.2 5.2-2.4Z" /></>,
};

export function Icon({ name }: { name: IconName }) {
  return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}
