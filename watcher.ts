import "dotenv/config";
import { sdk, sendToGroup, sendToPoke, GROUP_CHAT_ID, POKE_CONTACT_ID } from "./group-chat.js";

// ── Rolling buffer of group chat messages ───────────────────────

const messageBuffer: { sender: string; text: string }[] = [];
const MAX_BUFFER = 20;

// ── Loop prevention ─────────────────────────────────────────────
// Track messages we recently sent so we don't echo them back.
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
// Poke's DM chatId is something like "iMessage;-;+1234567890"
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

  // Debug: log every message so we can see chatId format
  // console.log(`[DEBUG] chatId="${msg.chatId}" sender="${msg.sender}" isFromMe=${msg.isFromMe} text="${msg.text.slice(0, 60)}"`);

  // ── ROUTE 1: Group chat message from a friend ────────────────
  // Forward to Poke so it can think + call MCP tools
  if (msg.chatId === GROUP_CHAT_ID && !msg.isFromMe) {
    console.log(`[GC ←] ${msg.sender}: ${msg.text}`);

    messageBuffer.push({ sender: msg.sender, text: msg.text });
    while (messageBuffer.length > MAX_BUFFER) {
      messageBuffer.shift();
    }

    const transcript = messageBuffer
      .map((m) => `${m.sender}: ${m.text}`)
      .join("\n");

    const pokeMessage =
      `You are Kaden, a chill friend in a group chat helping plan outings. ` +
      `Here's the latest group chat conversation:\n\n${transcript}\n\n` +
      `The most recent message is from ${msg.sender}: "${msg.text}"\n\n` +
      `Respond naturally as Kaden. If they're planning something, help coordinate. ` +
      `If you have enough info (food type, time, area), use your restaurant search tools. ` +
      `Keep it casual and short — you're texting friends, not writing an email.`;

    markAsSent(pokeMessage);
    console.log(`[Poke →] Forwarding ${messageBuffer.length} msgs to Poke...`);
    await sendToPoke(pokeMessage);
    return;
  }

  // ── ROUTE 2: Poke's DM response → relay to group chat ───────
  // Poke thought about it, maybe called MCP tools, and replied in DM.
  // We take that response and post it to the group as Kaden.
  if (isPokeDM(msg.chatId) && !msg.isFromMe) {
    console.log(`[Poke ←] ${msg.text.slice(0, 100)}...`);

    if (wasSentByUs(msg.text)) {
      console.log(`[Skip] Echo of our own message`);
      return;
    }

    markAsSent(msg.text);
    await sendToGroup(msg.text);
    return;
  }

  // ── ROUTE 3: Our own messages → ignore (loop prevention) ────
  if (msg.isFromMe) {
    return;
  }
}

// ── Main ────────────────────────────────────────────────────────

async function main() {
  console.log("Starting Kaden (Photon ↔ Poke bridge)...\n");
  console.log(`[Config] Group chat: ${GROUP_CHAT_ID}`);
  console.log(`[Config] Poke contact: ${POKE_CONTACT_ID}`);
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
