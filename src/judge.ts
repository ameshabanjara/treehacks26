import Anthropic from "@anthropic-ai/sdk";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type JudgeState = "IDLE" | "PLANNING";
export type JudgeAction = "FORWARD" | "IGNORE" | "CONCLUDE";
export type MessageDirection = "inbound" | "outbound";

// ---------------------------------------------------------------------------
// System Prompt
// ---------------------------------------------------------------------------

export const JUDGE_SYSTEM_PROMPT = `You are a message routing classifier for a group chat planning bot.

You will receive a message along with two pieces of context:
- DIRECTION: "inbound" (message from group chat) or "outbound" (response from planning agent)
- STATE: "IDLE" (no active planning) or "PLANNING" (currently coordinating a plan)

Your job is to decide what to do with the message. Respond with ONLY a JSON object.

Rules:
- If DIRECTION=inbound and STATE=IDLE:
  Return {"action": "FORWARD"} if the message is asking to plan an activity (dinner, trip, hangout, etc.)
  Return {"action": "IGNORE"} for normal chit-chat or anything not planning-related

- If DIRECTION=inbound and STATE=PLANNING:
  Return {"action": "FORWARD"} if the message is relevant to the active plan (preferences, votes, availability, confirmations, reactions)
  Return {"action": "IGNORE"} if completely off-topic

- If DIRECTION=outbound (STATE is always PLANNING):
  Return {"action": "FORWARD"} if the agent is still asking questions, presenting options, or gathering info
  Return {"action": "CONCLUDE"} if the agent has finalized the plan (confirmed booking, final itinerary, "all set!" type message)`;

// ---------------------------------------------------------------------------
// LLM Judge Class
// ---------------------------------------------------------------------------

export class LLMJudge {
  private state: JudgeState = "IDLE";
  private client: Anthropic;

  constructor(client: Anthropic) {
    this.client = client;
  }

  /** Get the current state of the Judge state machine. */
  getState(): JudgeState {
    return this.state;
  }

  /** Manually set the state (useful for testing). */
  setState(state: JudgeState): void {
    this.state = state;
  }

  /**
   * Classify a message and update internal state accordingly.
   *
   * @param message  - The raw message text
   * @param direction - "inbound" (from group chat) or "outbound" (from Poke agent)
   * @returns The action: "FORWARD", "IGNORE", or "CONCLUDE"
   */
  async classify(
    message: string,
    direction: MessageDirection,
  ): Promise<JudgeAction> {
    const action = await this.callLLM(message, direction);
    this.applyTransition(action);
    return action;
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  /**
   * Call Claude Haiku to classify the message.
   * Exposed as a separate method so it can be mocked in unit tests.
   */
  async callLLM(
    message: string,
    direction: MessageDirection,
  ): Promise<JudgeAction> {
    const response = await this.client.messages.create({
      model: "claude-haiku-4-5",
      max_tokens: 50,
      system: JUDGE_SYSTEM_PROMPT,
      messages: [
        {
          role: "user",
          content: `DIRECTION: ${direction}\nSTATE: ${this.state}\n\nMESSAGE: ${message}`,
        },
      ],
    });

    const raw =
      response.content[0].type === "text" ? response.content[0].text.trim() : "";

    // Haiku 4.5 sometimes wraps JSON in markdown code fences or adds extra text.
    // Extract the first JSON object we find.
    const jsonMatch = raw.match(/\{[^}]*\}/);
    if (!jsonMatch) {
      throw new Error(`LLM Judge returned unparseable response: ${raw}`);
    }

    const parsed = JSON.parse(jsonMatch[0]);
    return parsed.action as JudgeAction;
  }

  /**
   * Apply the state machine transition based on the action.
   *
   * Transitions:
   *   IDLE   + FORWARD  -> PLANNING
   *   PLANNING + CONCLUDE -> IDLE
   *   Everything else     -> no change
   */
  applyTransition(action: JudgeAction): void {
    if (this.state === "IDLE" && action === "FORWARD") {
      this.state = "PLANNING";
    } else if (this.state === "PLANNING" && action === "CONCLUDE") {
      this.state = "IDLE";
    }
    // IGNORE or FORWARD-while-PLANNING: state stays the same
  }
}
