// Parser for the one string that links this browser to a JobPilot server.
//
// Format (mirrored by backend/app/services/link_code.py — the two must agree,
// and tests/test_link_code.py pins the shape):
//
//   JP1-<base64url of {"u": "<app url>", "c": "<code>"}>
//
// Pairing needs a server URL and a pairing code. Asking a person for both,
// separately, put the harder half on them: the URL that works is whichever
// origin their browser already reached the app on, and "localhost" is right
// only when the browser and server are the same machine. Carrying it inside
// the code removes the question.
//
// A bare 6-digit code is still accepted so an old code, or one read off a
// phone screen, keeps working — the caller supplies the URL in that case.

const PREFIX = "JP1-";

export interface LinkTarget {
  serverUrl: string;
  code: string;
}

function b64urlDecode(text: string): string {
  const padded = text + "=".repeat((4 - (text.length % 4)) % 4);
  const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  // The payload is JSON with a URL and digits in it — decode as UTF-8 rather
  // than assuming latin1, so a hostname with non-ASCII characters survives.
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/** Parse a pasted link code. Returns null when it isn't one. */
export function parseLinkCode(input: string): LinkTarget | null {
  const text = input.trim();
  if (!text.startsWith(PREFIX)) return null;
  let data: unknown;
  try {
    data = JSON.parse(b64urlDecode(text.slice(PREFIX.length)));
  } catch {
    return null;
  }
  if (!data || typeof data !== "object") return null;
  const { u, c } = data as { u?: unknown; c?: unknown };
  if (typeof u !== "string" || typeof c !== "string" || !u || !c) return null;
  // Only ever an http(s) origin: a link code should not be able to point the
  // extension at a javascript: or data: URL.
  let url: URL;
  try {
    url = new URL(u);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  return { serverUrl: u.replace(/\/$/, ""), code: c };
}

/**
 * Work out what the user pasted. A full link code carries its own server URL;
 * a bare code falls back to the one already stored.
 */
export function resolvePasted(input: string, fallbackUrl: string): LinkTarget | null {
  const parsed = parseLinkCode(input);
  if (parsed) return parsed;
  const digits = input.trim().replace(/\s+/g, "");
  if (/^\d{6}$/.test(digits) && fallbackUrl) {
    return { serverUrl: fallbackUrl.replace(/\/$/, ""), code: digits };
  }
  return null;
}
