import { App } from "@capacitor/app";
import { Capacitor, registerPlugin } from "@capacitor/core";

/**
 * The Android app (Capacitor) has no HTTP server: API calls go to the in-process Python backend
 * through the native Backend plugin, and files are saved through the system file picker. In a
 * browser every function here falls back to the normal web behaviour.
 */
interface BackendPlugin {
  request(options: { method: string; path: string; headers: Record<string, string>; body?: string }): Promise<{
    status: number;
    headers: Record<string, string>;
    body?: string;
    bodyBase64?: string;
  }>;
  stageFile(options: { data: string }): Promise<{ id: string }>;
  saveFile(options: { id: string; filename: string; mimeType: string }): Promise<{ saved: boolean }>;
}

const Backend = registerPlugin<BackendPlugin>("Backend");

export const isNativeApp = Capacitor.isNativePlatform();

function abortError() {
  return new DOMException("The operation was aborted.", "AbortError");
}

function base64ToBytes(text: string) {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function blobToBase64(blob: Blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(binary);
}

/** fetch() for same-origin API paths; returns a real Response so callers need no changes. */
export async function platformFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!isNativeApp) return fetch(path, init);
  const signal = init.signal;
  if (signal?.aborted) throw abortError();
  const headers: Record<string, string> = {};
  new Headers(init.headers).forEach((value, key) => { headers[key] = value; });
  const body = init.body == null ? undefined
    : typeof init.body === "string" ? init.body : await new Response(init.body).text();
  const call = Backend.request({ method: (init.method ?? "GET").toUpperCase(), path, headers, body });
  // The native call cannot be cancelled; an abort only stops waiting for it, as with fetch.
  const result = await (signal ? Promise.race([call, new Promise<never>((_, reject) => {
    signal.addEventListener("abort", () => reject(abortError()), { once: true });
  })]) : call);
  const payload = result.status === 204 || result.status === 205 ? null
    : result.bodyBase64 !== undefined ? base64ToBytes(result.bodyBase64) : result.body ?? "";
  return new Response(payload, { status: result.status, headers: result.headers });
}

/** Save a file: the browser's download, or the system "save as" picker in the app. False when cancelled. */
export async function saveFile(blob: Blob, filename: string): Promise<boolean> {
  if (!isNativeApp) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    return true;
  }
  // Staged first: the picker call itself must stay small (see BackendPlugin.stageFile).
  const { id } = await Backend.stageFile({ data: await blobToBase64(blob) });
  const result = await Backend.saveFile({ id, filename, mimeType: blob.type || "application/octet-stream" });
  return result.saved;
}

/**
 * Android back button: close the open dialog first, then go back a page; on the first page the
 * app moves to the background instead of closing, so a story job keeps running.
 */
export function installBackButton() {
  if (!isNativeApp) return;
  void App.addListener("backButton", ({ canGoBack }) => {
    const dialogs = document.querySelectorAll<HTMLDialogElement>("dialog[open]");
    const dialog = dialogs[dialogs.length - 1];
    if (dialog) {
      // Same path as pressing Esc, so the dialog's own close handling and animation run.
      if (dialog.dispatchEvent(new Event("cancel", { cancelable: true }))) dialog.close();
      return;
    }
    if (canGoBack && window.history.length > 1 && window.location.pathname !== "/") window.history.back();
    else void App.minimizeApp();
  });
}
