import { saveFile } from "../../platform/native";

/** Save a blob: the browser's normal download flow, or the system "save as" picker in the Android app. False when cancelled. */
export function downloadBlob(blob: Blob, filename: string): Promise<boolean> {
  return saveFile(blob, filename);
}
