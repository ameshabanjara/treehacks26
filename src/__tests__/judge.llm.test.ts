/**
 * LLM Classification Tests (Live Claude API)
 *
 * These tests hit the real Claude Haiku API to validate that the Judge system
 * prompt correctly classifies a curated set of messages. They require a valid
 * ANTHROPIC_API_KEY in the environment (or .env file).
 *
 * Run with:  npm run test:llm
 *
 * Accuracy target: >= 16/18 (89%)
 */

import { describe, it, expect, beforeAll } from "vitest";
import { config } from "dotenv";
import Anthropic from "@anthropic-ai/sdk";
import { LLMJudge, type JudgeAction, type JudgeState } from "../judge.js";

// Load .env so ANTHROPIC_API_KEY is available
config();

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

let client: Anthropic;
let judge: LLMJudge;

beforeAll(() => {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error(
      "ANTHROPIC_API_KEY is required. Set it in your .env file to run LLM tests.",
    );
  }
  client = new Anthropic({ apiKey });
  judge = new LLMJudge(client);
});

/** Helper: classify in a specific state, then reset state for the next test. */
async function classifyInState(
  message: string,
  direction: "inbound" | "outbound",
  state: JudgeState,
): Promise<JudgeAction> {
  judge.setState(state);
  // Call callLLM directly so we don't mutate state between tests
  return judge.callLLM(message, direction);
}

// ---------------------------------------------------------------------------
// Inbound + IDLE: Should the Judge activate planning?
// ---------------------------------------------------------------------------

describe("LLM Judge classification (live API)", { timeout: 30_000 }, () => {
  describe("inbound + IDLE", () => {
    it('ignores casual chit-chat: "Hey guys whats up"', async () => {
      const result = await classifyInState("Hey guys whats up", "inbound", "IDLE");
      expect(result).toBe("IGNORE");
    });

    it('ignores casual chit-chat: "lol that\'s hilarious"', async () => {
      const result = await classifyInState("lol that's hilarious", "inbound", "IDLE");
      expect(result).toBe("IGNORE");
    });

    it('ignores casual chit-chat: "anyone seen the new marvel movie?"', async () => {
      const result = await classifyInState(
        "anyone seen the new marvel movie?",
        "inbound",
        "IDLE",
      );
      expect(result).toBe("IGNORE");
    });

    it('detects planning intent: "Hey, help us plan dinner this Saturday"', async () => {
      const result = await classifyInState(
        "Hey, help us plan dinner this Saturday",
        "inbound",
        "IDLE",
      );
      expect(result).toBe("FORWARD");
    });

    it('detects planning intent: "let\'s plan something fun this weekend"', async () => {
      const result = await classifyInState(
        "let's plan something fun this weekend",
        "inbound",
        "IDLE",
      );
      expect(result).toBe("FORWARD");
    });

    it('detects planning intent: "we should do a trip to tahoe next month"', async () => {
      const result = await classifyInState(
        "we should do a trip to tahoe next month",
        "inbound",
        "IDLE",
      );
      expect(result).toBe("FORWARD");
    });
  });

  // ---------------------------------------------------------------------------
  // Inbound + PLANNING: Is this relevant to the active plan?
  // ---------------------------------------------------------------------------

  describe("inbound + PLANNING", () => {
    it('forwards availability: "I\'m free after 7pm"', async () => {
      const result = await classifyInState("I'm free after 7pm", "inbound", "PLANNING");
      expect(result).toBe("FORWARD");
    });

    it('forwards preference: "Italian sounds great!"', async () => {
      const result = await classifyInState(
        "Italian sounds great!",
        "inbound",
        "PLANNING",
      );
      expect(result).toBe("FORWARD");
    });

    it('forwards vote: "+1 for Rosa\'s"', async () => {
      const result = await classifyInState("+1 for Rosa's", "inbound", "PLANNING");
      expect(result).toBe("FORWARD");
    });

    it('forwards schedule adjustment: "Can\'t do Saturday, Sunday works"', async () => {
      const result = await classifyInState(
        "Can't do Saturday, Sunday works",
        "inbound",
        "PLANNING",
      );
      expect(result).toBe("FORWARD");
    });

    it('ignores off-topic: "lol did you see that meme?"', async () => {
      const result = await classifyInState(
        "lol did you see that meme?",
        "inbound",
        "PLANNING",
      );
      expect(result).toBe("IGNORE");
    });

    it('ignores off-topic: "totally unrelated but check this out"', async () => {
      const result = await classifyInState(
        "totally unrelated but check this out",
        "inbound",
        "PLANNING",
      );
      expect(result).toBe("IGNORE");
    });
  });

  // ---------------------------------------------------------------------------
  // Outbound + PLANNING: Is Poke done?
  // ---------------------------------------------------------------------------

  describe("outbound + PLANNING", () => {
    it('forwards question: "What kind of food are we thinking?"', async () => {
      const result = await classifyInState(
        "What kind of food are we thinking?",
        "outbound",
        "PLANNING",
      );
      expect(result).toBe("FORWARD");
    });

    it('forwards options: "Here are 3 options: 1) Rosa\'s..."', async () => {
      const result = await classifyInState(
        "Here are 3 options: 1) Rosa's Italian Kitchen 2) Bella Notte 3) Lucia's Trattoria",
        "outbound",
        "PLANNING",
      );
      expect(result).toBe("FORWARD");
    });

    it('forwards vote tally: "Rosa\'s has the most votes. Should I book it?"', async () => {
      const result = await classifyInState(
        "Rosa's has the most votes. Should I book it?",
        "outbound",
        "PLANNING",
      );
      expect(result).toBe("FORWARD");
    });

    it('concludes on booking: "All booked! Rosa\'s at 7pm, party of 4. Confirmation #R7234"', async () => {
      const result = await classifyInState(
        "All booked! Rosa's at 7pm, party of 4. Confirmation #R7234",
        "outbound",
        "PLANNING",
      );
      expect(result).toBe("CONCLUDE");
    });

    it('concludes on finalization: "All set! Here\'s the plan: Rosa\'s Italian..."', async () => {
      const result = await classifyInState(
        "All set! Here's the plan: Rosa's Italian Kitchen, Saturday at 7pm, party of 4.",
        "outbound",
        "PLANNING",
      );
      expect(result).toBe("CONCLUDE");
    });

    it('concludes on reservation confirmed: "Reservation confirmed! See you there"', async () => {
      const result = await classifyInState(
        "Reservation confirmed! See you there",
        "outbound",
        "PLANNING",
      );
      expect(result).toBe("CONCLUDE");
    });
  });

  // ---------------------------------------------------------------------------
  // Integration Smoke Test: Full Lifecycle
  // ---------------------------------------------------------------------------

  describe("Judge full lifecycle", () => {
    it("IDLE -> detect plan -> PLANNING -> process messages -> CONCLUDE -> IDLE", async () => {
      // Use a fresh judge instance for the lifecycle test
      const lifecycleJudge = new LLMJudge(client);

      // 1. Start idle, ignore chit-chat
      expect(lifecycleJudge.getState()).toBe("IDLE");
      expect(await lifecycleJudge.classify("hey whats up", "inbound")).toBe("IGNORE");
      expect(lifecycleJudge.getState()).toBe("IDLE");

      // 2. Detect planning intent -> transitions to PLANNING
      expect(
        await lifecycleJudge.classify("let's plan dinner saturday", "inbound"),
      ).toBe("FORWARD");
      expect(lifecycleJudge.getState()).toBe("PLANNING");

      // 3. Forward planning-relevant messages -> stays in PLANNING
      expect(await lifecycleJudge.classify("I want Italian", "inbound")).toBe(
        "FORWARD",
      );
      expect(lifecycleJudge.getState()).toBe("PLANNING");

      // 4. Forward intermediate Poke response -> stays in PLANNING
      expect(
        await lifecycleJudge.classify(
          "Here are some options: 1) Rosa's Italian Kitchen 2) Thai Basil 3) Sushi Zen",
          "outbound",
        ),
      ).toBe("FORWARD");
      expect(lifecycleJudge.getState()).toBe("PLANNING");

      // 5. Detect conclusion -> transitions back to IDLE
      expect(
        await lifecycleJudge.classify(
          "All booked! Rosa's at 7pm, party of 4. Confirmation #R7234",
          "outbound",
        ),
      ).toBe("CONCLUDE");
      expect(lifecycleJudge.getState()).toBe("IDLE");
    });
  });
});
