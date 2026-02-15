import "dotenv/config";
import { IMessageSDK } from "@photon-ai/imessage-kit";

const GROUP_CHAT_ID = process.env.GROUP_CHAT_ID;

if (!GROUP_CHAT_ID) {
  console.error(
    "Missing GROUP_CHAT_ID in .env. Run `npx tsx watch-imessage.ts` to find your group chat ID."
  );
  process.exit(1);
}

const sdk = new IMessageSDK({
  watcher: {
    pollInterval: 2000,
    excludeOwnMessages: true,
  },
});

async function sendToGroup(text: string): Promise<void> {
  await sdk.send(GROUP_CHAT_ID!, text);
  console.log(`[Kaden → group] ${text}`);
}

export { sdk, sendToGroup, GROUP_CHAT_ID };
