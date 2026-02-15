import "dotenv/config";
import { IMessageSDK } from "@photon-ai/imessage-kit";

const GROUP_CHAT_ID = process.env.GROUP_CHAT_ID;
const POKE_CONTACT_ID = process.env.POKE_CONTACT_ID; // Poke's phone number or email

if (!GROUP_CHAT_ID) {
  console.error(
    "Missing GROUP_CHAT_ID in .env. Run `npx tsx watch-imessage.ts` to find your group chat ID."
  );
  process.exit(1);
}

if (!POKE_CONTACT_ID) {
  console.error(
    "Missing POKE_CONTACT_ID in .env. This is Poke's phone number (e.g. +1234567890)."
  );
  process.exit(1);
}

// excludeOwnMessages: false — we need to see ALL messages including
// Poke's DM replies. We filter manually in the watcher using isFromMe.
const sdk = new IMessageSDK({
  watcher: {
    pollInterval: 2000,
    excludeOwnMessages: false,
  },
});

async function sendToGroup(text: string): Promise<void> {
  // AppleScript needs "iMessage;+;chat..." format, DB gives "chat..."
  const sendId = GROUP_CHAT_ID!.startsWith("chat")
    ? `iMessage;+;${GROUP_CHAT_ID}`
    : GROUP_CHAT_ID!;
  await sdk.send(sendId, text);
  console.log(`[Kaden → GC] ${text}`);
}

async function sendToPoke(text: string): Promise<void> {
  await sdk.send(POKE_CONTACT_ID!, text);
  console.log(`[Kaden → Poke DM] ${text.slice(0, 80)}...`);
}

export { sdk, sendToGroup, sendToPoke, GROUP_CHAT_ID, POKE_CONTACT_ID };
