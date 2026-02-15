import "dotenv/config";
import Browserbase from "@browserbasehq/sdk";
import { Stagehand } from "@browserbasehq/stagehand";
import * as readline from "readline";

function waitForEnter(prompt: string): Promise<void> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(prompt, () => {
      rl.close();
      resolve();
    });
  });
}

async function main() {
  const projectId = process.env.BROWSERBASE_PROJECT_ID!;
  const apiKey = process.env.BROWSERBASE_API_KEY!;

  const anthropicKey = process.env.ANTHROPIC_API_KEY;

  if (!projectId || !apiKey) {
    console.error("Missing BROWSERBASE_PROJECT_ID or BROWSERBASE_API_KEY in .env");
    process.exit(1);
  }
  if (!anthropicKey) {
    console.error("Missing ANTHROPIC_API_KEY in .env");
    process.exit(1);
  }

  console.log("Creating a new Browserbase context for Uber login...\n");

  const bb = new Browserbase({ apiKey });
  const context = await bb.contexts.create({ projectId });
  const contextId = context.id;

  console.log(`Context created: ${contextId}\n`);
  console.log("Launching browser session with persist=true...\n");

  const stagehand = new Stagehand({
    env: "BROWSERBASE",
    model: "anthropic/claude-3-5-sonnet-latest",
    disableAPI: true,
    browserbaseSessionCreateParams: {
      projectId,
      browserSettings: {
        context: {
          id: contextId,
          persist: true,
        },
      },
    },
  });

  await stagehand.init();
  const page = stagehand.context.pages()[0];

  // Navigate to Uber so user can log in
  await page.goto("https://www.uber.com");
  await page.waitForLoadState("networkidle");

  console.log("=".repeat(60));
  console.log("Browser is open at uber.com");
  console.log("");
  console.log("Go to the Browserbase dashboard to access the live view:");
  console.log("  https://www.browserbase.com/sessions");
  console.log("");
  console.log("Log into your Uber account in the browser, then come");
  console.log("back here and press Enter to save the session.");
  console.log("=".repeat(60));

  await waitForEnter("\nPress Enter after you've logged into Uber... ");

  console.log("\nClosing session and persisting cookies...");
  await stagehand.close();

  // Wait for context to persist
  await new Promise((resolve) => setTimeout(resolve, 5000));

  console.log("\n" + "=".repeat(60));
  console.log("Done! Add this to your my-stagehand-app/.env file:\n");
  console.log(`BROWSERBASE_UBER_CONTEXT_ID="${contextId}"`);
  console.log("=".repeat(60));
}

main().catch((err) => {
  console.error("Setup failed:", err);
  process.exit(1);
});
