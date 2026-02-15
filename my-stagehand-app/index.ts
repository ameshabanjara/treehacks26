import "dotenv/config";
import { Stagehand } from "@browserbasehq/stagehand";

type BookingInput = {
  url: string;
  time_text: string;
  party_size: number;
};

async function readStdin(): Promise<string> {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
  });
}

async function main() {
  console.info("Launching browser...");
  const stagehand = new Stagehand({
    env: "LOCAL",
    modelApiKey: process.env.GOOGLE_API_KEY,
    model: "gemini-2.0-flash",
  });

  await stagehand.init();

  const page = stagehand.context.pages()[0];

  console.info("Connected!");

  const stdin = await readStdin();
  if (!stdin.trim()) {
    console.error(
      "No JSON provided. Pipe JSON with url, time_text, party_size."
    );
    await stagehand.close();
    process.exit(1);
  }

  const { url, time_text, party_size } = JSON.parse(stdin) as BookingInput;

  await new Promise((resolve) => setTimeout(resolve, 1000));

  await page.goto(url);
  await page.waitForLoadState("networkidle");
  await stagehand.act(`zoom to 60%`);
  await stagehand.observe("find the view full availability button");
  await stagehand.act(`select party size ${party_size}`);
  await stagehand.observe("find the view full availability button");
  await stagehand.act("click the view full availability button");
  await stagehand.act(`click the ${time_text} button`);
  await stagehand.observe("find the phone number input box");
  await stagehand.act("click the phone number input box");
  await stagehand.observe("fill in the phone number 1234567890");
  await stagehand.act("click the complete reservation button");
  await stagehand.observe("find the phone continue box");
  await stagehand.act("fill in the code 6093333333");
  await stagehand.act("click the continue button");

  console.info("Success!");

  console.info("Waiting 30 seconds before closing...");
  await new Promise((resolve) => setTimeout(resolve, 30000));

  await stagehand.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
