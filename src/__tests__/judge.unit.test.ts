import { describe, it, expect, vi, beforeEach } from "vitest";
import { LLMJudge, type JudgeAction, type JudgeState } from "../judge.js";
import Anthropic from "@anthropic-ai/sdk";

// ---------------------------------------------------------------------------
// Helpers: create a mock Anthropic client whose messages.create resolves to
// a canned action. We swap the behaviour per-test via `mockAction`.
// ---------------------------------------------------------------------------

let mockAction: JudgeAction = "IGNORE";

function makeMockClient(): Anthropic {
  return {
    messages: {
      create: vi.fn(async () => ({
        content: [{ type: "text", text: JSON.stringify({ action: mockAction }) }],
      })),
    },
  } as unknown as Anthropic;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("LLMJudge state machine", () => {
  let client: Anthropic;
  let judge: LLMJudge;

  beforeEach(() => {
    client = makeMockClient();
    judge = new LLMJudge(client);
    mockAction = "IGNORE"; // default
  });

  // --- initial state ---

  it("starts in IDLE state", () => {
    expect(judge.getState()).toBe("IDLE");
  });

  // --- IDLE transitions ---

  it("transitions to PLANNING when inbound FORWARD received in IDLE", async () => {
    mockAction = "FORWARD";
    const result = await judge.classify("plan dinner", "inbound");
    expect(result).toBe("FORWARD");
    expect(judge.getState()).toBe("PLANNING");
  });

  it("stays IDLE when IGNORE received in IDLE", async () => {
    mockAction = "IGNORE";
    const result = await judge.classify("hey whats up", "inbound");
    expect(result).toBe("IGNORE");
    expect(judge.getState()).toBe("IDLE");
  });

  // --- PLANNING transitions ---

  it("stays in PLANNING when FORWARD received in PLANNING", async () => {
    judge.setState("PLANNING");
    mockAction = "FORWARD";
    const result = await judge.classify("I'm free after 7pm", "inbound");
    expect(result).toBe("FORWARD");
    expect(judge.getState()).toBe("PLANNING");
  });

  it("stays in PLANNING when IGNORE received in PLANNING", async () => {
    judge.setState("PLANNING");
    mockAction = "IGNORE";
    const result = await judge.classify("lol did you see that meme?", "inbound");
    expect(result).toBe("IGNORE");
    expect(judge.getState()).toBe("PLANNING");
  });

  it("transitions back to IDLE on CONCLUDE", async () => {
    judge.setState("PLANNING");
    mockAction = "CONCLUDE";
    const result = await judge.classify("All booked! Confirmation #R7234", "outbound");
    expect(result).toBe("CONCLUDE");
    expect(judge.getState()).toBe("IDLE");
  });

  // --- getState / setState ---

  it("getState() returns correct state after manual setState()", () => {
    expect(judge.getState()).toBe("IDLE");
    judge.setState("PLANNING");
    expect(judge.getState()).toBe("PLANNING");
    judge.setState("IDLE");
    expect(judge.getState()).toBe("IDLE");
  });

  // --- applyTransition edge cases ---

  it("CONCLUDE while IDLE does NOT change state (stays IDLE)", () => {
    judge.applyTransition("CONCLUDE");
    expect(judge.getState()).toBe("IDLE");
  });

  it("IGNORE while IDLE keeps state IDLE", () => {
    judge.applyTransition("IGNORE");
    expect(judge.getState()).toBe("IDLE");
  });

  it("FORWARD while PLANNING keeps state PLANNING", () => {
    judge.setState("PLANNING");
    judge.applyTransition("FORWARD");
    expect(judge.getState()).toBe("PLANNING");
  });

  // --- verify the mock client is called correctly ---

  it("passes direction and state to the LLM", async () => {
    mockAction = "IGNORE";
    await judge.classify("hello", "inbound");

    const createFn = (client.messages.create as ReturnType<typeof vi.fn>);
    expect(createFn).toHaveBeenCalledOnce();

    const callArgs = createFn.mock.calls[0][0];
    expect(callArgs.model).toBe("claude-haiku-4-5");
    expect(callArgs.max_tokens).toBe(50);
    expect(callArgs.messages[0].content).toContain("DIRECTION: inbound");
    expect(callArgs.messages[0].content).toContain("STATE: IDLE");
    expect(callArgs.messages[0].content).toContain("MESSAGE: hello");
  });

  it("sends PLANNING state when in planning mode", async () => {
    judge.setState("PLANNING");
    mockAction = "FORWARD";
    await judge.classify("Italian sounds great", "inbound");

    const createFn = (client.messages.create as ReturnType<typeof vi.fn>);
    const callArgs = createFn.mock.calls[0][0];
    expect(callArgs.messages[0].content).toContain("STATE: PLANNING");
  });
});
