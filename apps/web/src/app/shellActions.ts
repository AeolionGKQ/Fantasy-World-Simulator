/** Callbacks the app shell hands to routed pages. */
export interface ShellActions {
  refreshSaves: () => Promise<void>;
  setNotice: (notice: string) => void;
}
