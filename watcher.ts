import "dotenv/config";
import { Poke } from "poke";
import { sdk, GROUP_CHAT_ID } from "./group-chat.js";

const poke = new Poke(); // reads POKE_API_KEY from env

const messageBuffer: { sender: string; text: string }[] = [];
const MAX_BUFFER = 20;

async function handleMessage(msg: {
  sender: string;
  text: string;
  chatId: string;
}) {
  // Only process messages from the target group chat
  if (msg.chatId !== GROUP_CHAT_ID) return;
  if (!msg.text || msg.text.trim() === "") return;

  console.log(`[GC] ${msg.sender}: ${msg.text}`);

  // Add to rolling buffer
  messageBuffer.push({ sender: msg.sender, text: msg.text });
  while (messageBuffer.length > MAX_BUFFER) {
    messageBuffer.shift();
  }

  // Forward the conversation to Poke via DM
  const transcript = messageBuffer
    .map((m) => `${m.sender}: ${m.text}`)
    .join("\n");

  const pokeMessage = `Here's the latest from the group chat:\n\n${transcript}\n\nThis is the most recent message: "${msg.text}" from ${msg.sender}`;

  console.log(`[Poke → DM] Forwarding ${messageBuffer.length} messages to Poke...`);
  await poke.sendMessage(pokeMessage);
  console.log(`[Poke → DM] Sent.`);
}

async function main() {
  console.log("Starting Photon → Poke bridge...\n");
  console.log(`[Photon] Watching group chat: ${GROUP_CHAT_ID}`);
  console.log("[Photon] Waiting for messages...\n");

  await sdk.startWatching({
    onGroupMessage: handleMessage,
    onError: (error) => {
      console.error("[Photon error]", error);
    },
  });
}

process.on("SIGINT", async () => {
  console.log("\nShutting down...");
  await sdk.stopWatching();
  await sdk.close();
  process.exit(0);
});

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
