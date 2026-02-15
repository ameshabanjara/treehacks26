import "dotenv/config";
import Anthropic from "@anthropic-ai/sdk";
import { LLMJudge } from "./src/judge.js";
import { sdk, sendToGroup, sendToPoke, GROUP_CHAT_ID, POKE_CONTACT_ID } from "./group-chat.js";

// ── Init ────────────────────────────────────────────────────────

const anthropic = new Anthropic();
const judge = new LLMJudge(anthropic);

const messageBuffer: { sender: string; text: string }[] = [];
const MAX_BUFFER = 20;
const SYSTEM_PROMPT =
  `You are Kaden, a chill friend in a group chat helping plan outings. ` +
  `I'll forward you messages from the group chat as they come in. ` +
  `Respond naturally as Kaden. If they're planning something, help coordinate. ` +
  `If you have enough info (food type, time, area), use your restaurant search tools. ` +
  `Keep it casual and short — you're texting friends, not writing an email.`;


// ── Loop prevention ─────────────────────────────────────────────

const recentlySent = new Set<string>();

function markAsSent(text: string) {
  const key = text.trim().slice(0, 100);
  recentlySent.add(key);
  setTimeout(() => recentlySent.delete(key), 10_000);
}

function wasSentByUs(text: string): boolean {
  const key = text.trim().slice(0, 100);
  return recentlySent.has(key);
}

// ── Poke DM detection ───────────────────────────────────────────

function isPokeDM(chatId: string): boolean {
  if (!POKE_CONTACT_ID) return false;
  return chatId.includes(POKE_CONTACT_ID);
}

// ── Message routing ─────────────────────────────────────────────

async function handleMessage(msg: {
  sender: string;
  text: string | null;
  chatId: string;
  isFromMe: boolean;
}) {
  if (!msg.text || msg.text.trim() === "") return;

  // ── Our own messages → ignore (loop prevention) ──────────────
  if (msg.isFromMe) return;

  // ── ROUTE 1: Group chat message (inbound) ────────────────────
  if (msg.chatId === GROUP_CHAT_ID) {
    console.log(`[GC ←] ${msg.sender}: ${msg.text}`);

    messageBuffer.push({ sender: msg.sender, text: msg.text });
    while (messageBuffer.length > MAX_BUFFER) {
      messageBuffer.shift();
    }

    // Judge: only forward planning-relevant messages
    const action = await judge.classify(msg.text, "inbound");
    console.log(`[Judge] ${action} (state: ${judge.getState()})`);
    if (action === "IGNORE") return;

    // Forward full buffer to Poke
    const transcript = messageBuffer
      .map((m) => `${m.sender}: ${m.text}`)
      .join("\n");

    const pokeMessage =
      `Here's the latest group chat conversation:\n\n${transcript}\n\n` +
      `The most recent message is from ${msg.sender}: "${msg.text}"`;

    markAsSent(pokeMessage);
    console.log(`[Poke →] Forwarding ${messageBuffer.length} msgs to Poke...`);
    await sendToPoke(pokeMessage);
    return;
  }

  // ── ROUTE 2: Poke DM response (outbound) ─────────────────────
  if (isPokeDM(msg.chatId)) {
    console.log(`[Poke ←] ${msg.text.slice(0, 100)}...`);

    if (wasSentByUs(msg.text)) {
      console.log(`[Skip] Echo of our own message`);
      return;
    }

    // TODO: re-enable judge here to detect CONCLUDE
    // const action = await judge.classify(msg.text, "outbound");
    // if (action === "IGNORE") return;

    markAsSent(msg.text);
    await sendToGroup(msg.text);
    return;
  }
}

// ── Main ────────────────────────────────────────────────────────

async function main() {
  console.log("Starting Kaden (Photon ↔ Poke bridge)...\n");
  console.log(`[Config] Group chat: ${GROUP_CHAT_ID}`);
  console.log(`[Config] Poke contact: ${POKE_CONTACT_ID}`);
  console.log("[Judge] ENABLED — filtering inbound group chat messages");

  // Send system prompt to Poke immediately on startup
  markAsSent(SYSTEM_PROMPT);
  await sendToPoke(SYSTEM_PROMPT);
  console.log("[Poke →] System prompt sent");

  console.log("[Photon] Watching all messages...\n");

  await sdk.startWatching({
    onMessage: handleMessage,
    onError: (error) => {
      console.error("[Photon error]", error);
    },
  });
}

process.on("SIGINT", async () => {
  console.log("\nShutting down Kaden...");
  await sdk.stopWatching();
  await sdk.close();
  process.exit(0);
});

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
