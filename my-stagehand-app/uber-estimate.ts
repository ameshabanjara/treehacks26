import "dotenv/config";
import { Stagehand } from "@browserbasehq/stagehand";

type EstimateInput = {
  origin: string;
  destination: string;
};

type RideEstimate = {
  service: string;
  price: string;
  duration: string;
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
  const stdin = await readStdin();
  if (!stdin.trim()) {
    console.error("No JSON provided. Pipe JSON with origin, destination.");
    process.exit(1);
  }

  const { origin, destination } = JSON.parse(stdin) as EstimateInput;

  console.info("Launching browser with Uber auth context...");
  const stagehand = new Stagehand({
    env: "BROWSERBASE",
    model: "anthropic/claude-sonnet-4-20250514",
    // disableAPI: true,
    browserbaseSessionCreateParams: {
      projectId: process.env.BROWSERBASE_PROJECT_ID!,
      browserSettings: {
        context: {
          id: process.env.BROWSERBASE_UBER_CONTEXT_ID!,
          persist: false,
        },
      },
    },
  });

  await stagehand.init();
  const page = stagehand.context.pages()[0];
  console.info("Connected!");

  // Navigate to Uber price estimate page and fill in locations
  await page.goto("https://www.uber.com/global/en/price-estimate/");
  await page.waitForLoadState("networkidle");

  // Helper: press a key via CDP
  const pressKey = async (key: string, code: string, keyCode: number) => {
    await page.sendCDP("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode: keyCode, nativeVirtualKeyCode: keyCode });
    await page.sendCDP("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: keyCode, nativeVirtualKeyCode: keyCode });
  };

  // Enter pickup location
  await stagehand.act(`click the pickup location input field`);
  await stagehand.act(`type "${origin}" into the pickup location input`);
  await new Promise((resolve) => setTimeout(resolve, 2000));
  // Press ArrowDown then Enter to select first suggestion (avoids twoStep issues)
  // await pressKey("ArrowDown", "ArrowDown", 40);
  await new Promise((resolve) => setTimeout(resolve, 300));
  await pressKey("Enter", "Enter", 13);
  await new Promise((resolve) => setTimeout(resolve, 2000));

  // Enter destination
  await stagehand.act(`click the destination or dropoff location input field`);
  await stagehand.act(`type "${destination}" into the destination input`);
  await new Promise((resolve) => setTimeout(resolve, 2000));
  // Press ArrowDown then Enter to select first suggestion
  // await pressKey("ArrowDown", "ArrowDown", 40);
  await new Promise((resolve) => setTimeout(resolve, 300));
  await pressKey("Enter", "Enter", 13);
  await new Promise((resolve) => setTimeout(resolve, 2000));

  // Click "See prices" — this navigates to m.uber.com
  await stagehand.act(`click the "See prices" button`);

  // Wait for m.uber.com to load and ride options to render
  await new Promise((resolve) => setTimeout(resolve, 12000));

  // Extract all ride options with prices
  let estimates: RideEstimate[] = [];
  try {
    const extracted = await stagehand.extract(
      "Extract all available Uber ride options. For each option, get: the service name (e.g. UberX, Comfort, UberXL, Black), the price or price range, and the estimated trip duration. Return as an array of objects with keys: service, price, duration."
    );
    if (Array.isArray(extracted)) {
      estimates = extracted as RideEstimate[];
    } else if (typeof extracted === "object" && extracted !== null) {
      const vals = Object.values(extracted);
      for (const val of vals) {
        // Handle stringified JSON array (e.g. {"extraction": "[...]"})
        if (typeof val === "string") {
          try {
            const parsed = JSON.parse(val);
            if (Array.isArray(parsed)) {
              estimates = parsed as RideEstimate[];
              break;
            }
          } catch { /* not JSON, skip */ }
        } else if (Array.isArray(val)) {
          estimates = val as RideEstimate[];
          break;
        }
      }
    }
  } catch (err) {
    console.error("Extract failed:", err);
  }

  const result = {
    success: true,
    origin,
    destination,
    estimates,
  };

  console.log(JSON.stringify(result));
  console.info("Done!");

  await stagehand.close();
}

main().catch((err) => {
  const errorResult = {
    success: false,
    error: String(err),
    estimates: [],
  };
  console.log(JSON.stringify(errorResult));
  console.error(err);
  process.exit(1);
});
