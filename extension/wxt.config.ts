import { defineConfig } from "wxt";

// Two builds from one source tree (Chrome MV3, Firefox MV3). Permissions are
// deliberately minimal. `debugger` is NOT requested here — it is an optional
// permission requested at first use, with a plain-English explanation, only
// for the opt-in remote-hand CAPTCHA relay (see lib/relay.ts). JobPilot never
// solves a challenge; the relay only carries a human's real input.
export default defineConfig({
  srcDir: "src",
  // MV3 for both Chrome and Firefox (Firefox 115+/ESR supports MV3). The
  // background is an event page under MV3; the keepalive alarm handles the
  // Chromium service-worker lifecycle.
  manifestVersion: 3,
  manifest: ({ browser }) => ({
    name: "JobPilot",
    description:
      "Fills employer application forms in your own browser with your own answers. A human decides every CAPTCHA.",
    version: "0.1.0",
    permissions: ["storage", "activeTab", "scripting", "notifications", "tabs"],
    optional_permissions: ["debugger"],
    host_permissions: ["<all_urls>"],
    action: { default_title: "JobPilot", default_popup: "popup.html" },
    ...(browser === "firefox"
      ? {
          browser_specific_settings: {
            gecko: { id: "jobpilot@localhost", strict_min_version: "115.0" },
          },
        }
      : {}),
  }),
  runner: { disabled: true },
});
