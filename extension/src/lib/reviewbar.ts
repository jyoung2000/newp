// The in-page approve/edit/skip bar for Review mode, and the halt banner for
// challenges. Shares JobPilot's design language (Inter, deep-blue accent,
// hairline borders, backdrop blur, 12–16px radii). Rendered in a shadow root
// so the host page's CSS can't touch it.

const STYLE = `
:host { all: initial; }
.jp-root {
  position: fixed; z-index: 2147483647;
  font-family: Inter, -apple-system, "SF Pro Text", system-ui, sans-serif;
  color: #0b1220;
}
.jp-bar {
  right: 20px; bottom: 20px; width: 360px; max-width: calc(100vw - 40px);
  position: fixed;
  background: rgba(255,255,255,0.86); backdrop-filter: blur(16px);
  border: 1px solid rgba(15,23,42,0.10); border-radius: 16px;
  box-shadow: 0 10px 40px rgba(2,6,23,0.18); overflow: hidden;
}
@media (prefers-color-scheme: dark) {
  .jp-bar { background: rgba(17,24,39,0.90); color: #e5e7eb; border-color: rgba(255,255,255,0.08); }
  .jp-field-value { color: #e5e7eb; }
  .jp-input { background:#0b1220; color:#e5e7eb; border-color: rgba(255,255,255,0.14); }
}
.jp-head { display:flex; align-items:center; gap:8px; padding:12px 16px; border-bottom:1px solid rgba(15,23,42,0.08); font-weight:600; font-size:13px; letter-spacing:-0.01em; }
.jp-dot { width:8px; height:8px; border-radius:50%; background:#2563eb; }
.jp-body { padding:14px 16px; max-height: 46vh; overflow-y:auto; }
.jp-field-label { font-size:12px; color:#64748b; margin-bottom:2px; }
.jp-field-value { font-size:14px; font-weight:500; word-break:break-word; }
.jp-src { font-size:11px; color:#2563eb; margin-top:2px; }
.jp-input { width:100%; box-sizing:border-box; margin-top:6px; padding:8px 10px; border:1px solid rgba(15,23,42,0.16); border-radius:10px; font-size:14px; font-family:inherit; }
.jp-actions { display:flex; gap:8px; padding:12px 16px; border-top:1px solid rgba(15,23,42,0.08); }
.jp-btn { flex:1; padding:9px 12px; border-radius:10px; border:1px solid transparent; font-size:13px; font-weight:600; cursor:pointer; transition:all 150ms ease; font-family:inherit; }
.jp-btn-primary { background:#2563eb; color:white; }
.jp-btn-primary:hover { background:#1d4ed8; }
.jp-btn-ghost { background:transparent; border-color:rgba(15,23,42,0.16); color:inherit; }
.jp-btn-ghost:hover { background:rgba(15,23,42,0.05); }
.jp-count { font-size:12px; color:#64748b; margin-left:auto; font-weight:400; }
.jp-kbd { font-size:10px; opacity:0.6; margin-left:4px; }
.jp-halt {
  left:50%; top:20px; transform:translateX(-50%); position:fixed;
  width: 460px; max-width: calc(100vw - 40px);
  background: rgba(255,251,235,0.96); backdrop-filter: blur(16px);
  border:1px solid #f59e0b; border-radius:16px; box-shadow:0 10px 40px rgba(2,6,23,0.2);
  padding:16px 18px;
}
@media (prefers-color-scheme: dark) {
  .jp-halt { background: rgba(69,52,10,0.95); color:#fde68a; }
}
.jp-halt-title { font-weight:700; font-size:14px; display:flex; gap:8px; align-items:center; }
.jp-halt-body { font-size:13px; line-height:1.5; margin-top:8px; }
.jp-badge { display:inline-block; font-size:11px; font-weight:600; padding:2px 8px; border-radius:999px; background:#dbeafe; color:#1d4ed8; }
`;

export interface ReviewItem {
  ref: string;
  label: string;
  value: string;
  source: string;
  editable: boolean;
}

type ReviewDecision =
  | { action: "approve" }
  | { action: "skip" }
  | { action: "edit"; values: Record<string, string> };

let container: HTMLElement | null = null;

function mount(): ShadowRoot {
  if (!container) {
    container = document.createElement("div");
    container.id = "jobpilot-overlay-root";
    document.documentElement.appendChild(container);
  }
  let shadow = container.shadowRoot;
  if (!shadow) {
    shadow = container.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = STYLE;
    shadow.appendChild(style);
  }
  // Clear previous content but keep the style.
  Array.from(shadow.children).forEach((c) => {
    if (c.tagName !== "STYLE") c.remove();
  });
  return shadow;
}

export function clearOverlay(): void {
  if (container?.shadowRoot) {
    Array.from(container.shadowRoot.children).forEach((c) => {
      if (c.tagName !== "STYLE") c.remove();
    });
  }
}

// Highlight a chosen value in-page with a subtle outline.
export function highlight(el: HTMLElement, kind: "ok" | "human"): void {
  el.style.outline = kind === "ok" ? "2px solid #2563eb" : "2px solid #f59e0b";
  el.style.outlineOffset = "1px";
  el.style.borderRadius = "6px";
}

export function showReviewBar(items: ReviewItem[]): Promise<ReviewDecision> {
  const shadow = mount();
  const root = document.createElement("div");
  root.className = "jp-root";
  const edits: Record<string, string> = {};

  const inputs = items
    .map((item, i) => {
      edits[item.ref] = item.value;
      const inputId = `jp-in-${i}`;
      return `
      <div style="margin-bottom:12px" data-item="${i}">
        <div class="jp-field-label">${escapeHtml(item.label)}</div>
        ${
          item.editable
            ? `<input class="jp-input" id="${inputId}" data-ref="${item.ref}" value="${escapeAttr(item.value)}"/>`
            : `<div class="jp-field-value">${escapeHtml(item.value)}</div>`
        }
        <div class="jp-src">${escapeHtml(item.source)}</div>
      </div>`;
    })
    .join("");

  root.innerHTML = `
    <div class="jp-bar" role="dialog" aria-label="JobPilot review">
      <div class="jp-head"><span class="jp-dot"></span> Review before submitting
        <span class="jp-count">${items.length} field${items.length === 1 ? "" : "s"}</span>
      </div>
      <div class="jp-body">${inputs}</div>
      <div class="jp-actions">
        <button class="jp-btn jp-btn-ghost" data-act="skip">Skip<span class="jp-kbd">s</span></button>
        <button class="jp-btn jp-btn-ghost" data-act="edit">Save edits<span class="jp-kbd">e</span></button>
        <button class="jp-btn jp-btn-primary" data-act="approve">Approve &amp; submit<span class="jp-kbd">a</span></button>
      </div>
    </div>`;
  shadow.appendChild(root);

  return new Promise<ReviewDecision>((resolve) => {
    const collectEdits = () => {
      root.querySelectorAll<HTMLInputElement>("input[data-ref]").forEach((inp) => {
        edits[inp.getAttribute("data-ref")!] = inp.value;
      });
      return { ...edits };
    };
    const finish = (decision: ReviewDecision) => {
      document.removeEventListener("keydown", onKey, true);
      clearOverlay();
      resolve(decision);
    };
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "a") finish({ action: "approve" });
      else if (e.key === "s") finish({ action: "skip" });
      else if (e.key === "e") finish({ action: "edit", values: collectEdits() });
    };
    root.querySelectorAll<HTMLButtonElement>("button[data-act]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const act = btn.getAttribute("data-act");
        if (act === "approve") finish({ action: "approve" });
        else if (act === "skip") finish({ action: "skip" });
        else finish({ action: "edit", values: collectEdits() });
      });
    });
    document.addEventListener("keydown", onKey, true);
  });
}

// The challenge halt banner — no answer box, ever. It tells the human that
// this interaction is theirs, in the real page.
export function showChallengeHalt(detail: string): void {
  const shadow = mount();
  const root = document.createElement("div");
  root.className = "jp-root";
  root.innerHTML = `
    <div class="jp-halt" role="alert">
      <div class="jp-halt-title">🖐️ Over to you — this one needs a human</div>
      <div class="jp-halt-body">
        This site is asking to confirm a person is here. <b>JobPilot paused and will
        not touch this challenge.</b> Please complete it yourself in this page, then
        JobPilot checks it is cleared and continues.
        <div style="margin-top:8px"><span class="jp-badge">${escapeHtml(detail)}</span></div>
      </div>
    </div>`;
  shadow.appendChild(root);
}

export function showToast(message: string): void {
  const shadow = mount();
  const root = document.createElement("div");
  root.className = "jp-root";
  root.innerHTML = `<div class="jp-bar" style="padding:12px 16px"><div class="jp-head" style="border:none;padding:0"><span class="jp-dot"></span> ${escapeHtml(
    message,
  )}</div></div>`;
  shadow.appendChild(root);
  setTimeout(() => clearOverlay(), 3500);
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}
function escapeAttr(s: string): string {
  return escapeHtml(s).replace(/\n/g, " ");
}
