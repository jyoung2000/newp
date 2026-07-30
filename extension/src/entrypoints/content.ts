// Content script: runs a single application fill on the page the background
// navigated to. All challenge halts route to the human — never solved here.
import browser from "webextension-polyfill";
import { autofillThisPage } from "../lib/autofill";
import { extractJob } from "../lib/capture";
import { showToast } from "../lib/reviewbar";
import { challengeCleared, ChallengeHalt, clearOverlay, runFill, showChallengeHalt } from "../lib/fill";
import type { BackgroundToContent, NextJob } from "../lib/types";

export default defineContentScript({
  matches: ["<all_urls>"],
  runAt: "document_idle",
  async main() {
    let stopped = false;
    let currentJob: NextJob | null = null;

    browser.runtime.onMessage.addListener((raw: unknown): Promise<unknown> => {
      const msg = raw as BackgroundToContent | { type: string };
      if (msg.type === "bg.captureJob") {
        // The user clicked "Save this job" in the popup. Read-only: describe
        // the page they are already looking at, change nothing.
        return Promise.resolve({ ok: true, job: extractJob() });
      }
      if (msg.type === "bg.autofillNow") {
        // One-click / one-keystroke fill of this page. Independent of the
        // queue: no application, and it never submits.
        void autofillThisPage().catch((e: unknown) => {
          showToast(e instanceof Error ? e.message : "Autofill failed");
        });
        return Promise.resolve({ ok: true });
      }
      if (msg.type === "bg.fillJob") {
        currentJob = (msg as { job: NextJob }).job;
        stopped = false;
        void driveJob(currentJob);
      } else if (msg.type === "bg.stop") {
        stopped = true;
        clearOverlay();
      } else if (msg.type === "bg.interventionsAnswered" || msg.type === "bg.resume") {
        if (currentJob) void resumeAfterHuman(currentJob);
      }
      return Promise.resolve({ ok: true });
    });

    // Let the background know a page with the content script is live.
    void browser.runtime.sendMessage({ type: "content.ready", url: location.href });

    async function report(msg: unknown): Promise<void> {
      try {
        await browser.runtime.sendMessage(msg);
      } catch {
        /* background may be asleep; it re-polls */
      }
    }

    async function driveJob(job: NextJob): Promise<void> {
      try {
        const result = await runFill(job, () => stopped);
        await handleResult(job, result);
      } catch (e) {
        if (e instanceof ChallengeHalt) {
          await handleChallenge(job, e);
        } else {
          await report({
            type: "content.status",
            applicationId: job.application_id,
            status: "failed",
            error: e instanceof Error ? e.message : String(e),
          });
        }
      }
    }

    async function handleResult(
      job: NextJob,
      result: Awaited<ReturnType<typeof runFill>>,
    ): Promise<void> {
      switch (result.outcome) {
        case "needs_human":
          await report({
            type: "content.needsHuman",
            applicationId: job.application_id,
            items: result.interventions || [],
            reason: result.reason || "unknown_field",
          });
          break;
        case "stopped":
          break; // background already knows the run stopped
        case "drafted":
          await report({
            type: "content.status",
            applicationId: job.application_id,
            status: "drafted",
            reason: "draft-only mode",
          });
          break;
        case "submitted":
        case "submitted_unconfirmed":
          await report({
            type: "content.submitted",
            applicationId: job.application_id,
            confirmed: result.confirmed ?? false,
            snapshot: result.snapshot || {},
            screenshot: result.screenshot,
          });
          break;
      }
    }

    async function handleChallenge(job: NextJob, halt: ChallengeHalt): Promise<void> {
      // Halt everything, show the banner, and tell the background to raise a
      // challenge intervention. Software enters nothing further on this page.
      showChallengeHalt(halt.detail);
      await report({
        type: "content.challenge",
        applicationId: job.application_id,
        detail: halt.detail,
        kind: halt.kind,
      });
    }

    async function resumeAfterHuman(job: NextJob): Promise<void> {
      // Before resuming, verify the challenge is genuinely gone.
      if (!challengeCleared()) {
        showChallengeHalt("Challenge still present — please finish it, then resume.");
        return;
      }
      clearOverlay();
      await driveJob(job);
    }
  },
});
