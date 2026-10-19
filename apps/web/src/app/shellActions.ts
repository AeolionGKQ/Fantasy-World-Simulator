/** Callbacks the app shell hands to routed pages. */
export interface ShellActions {
  refreshSaves: () => Promise<void>;
  /** Re-reads the model service status shown at the bottom of the sidebar. */
  refreshServiceStatus: () => Promise<void>;
}
