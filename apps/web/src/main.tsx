import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
// Serif for story and world-lore reading only (V-04). Bundled locally; unicode-range subsets are
// downloaded only for characters a page actually shows, and only on pages that use --font-reading.
import "@fontsource/noto-serif-sc/400.css";
import "@fontsource/noto-serif-sc/700.css";
import App from "./app/App";
import "./styles/index.css";

// A data router (rather than <BrowserRouter>) is required for view-transition navigations,
// navigate(..., { flushSync }) and <ScrollRestoration>. App keeps its own <Routes>.
const router = createBrowserRouter([{ path: "*", element: <App /> }]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
