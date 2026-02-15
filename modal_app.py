import modal
import json

app = modal.App("treehacks-mcp-server")

# Create Modal image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastmcp>=2.12.0", "uvicorn>=0.35.0", "fastapi[standard]")
    .run_commands(
        "apt-get update",
        "apt-get install -y curl gnupg chromium",
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
        "apt-get install -y nodejs"
    )
    .add_local_dir(
        "my-stagehand-app",
        remote_path="/root/my-stagehand-app",
        copy=True,
        ignore=["**/node_modules/**", ".git/**"],
    )
    .workdir("/root/my-stagehand-app")
    .run_commands("npm install")
)

@app.function(
    image=image,
    secrets=[modal.Secret.from_name("booking-secrets")],
    timeout=300,
)
def book_restaurant(
    url: str,
    time_text: str,
    party_size: int,
    phone: str | None = None,
    otp_code: str | None = None,
    skip_to_otp: bool | None = None,
):
    """
    Modal function that runs the Stagehand booking automation.
    """
    import subprocess
    import os
    
    payload = {
        "url": url,
        "time_text": time_text,
        "party_size": party_size,
        "phone": phone,
        "otp_code": otp_code,
        "skip_to_otp": skip_to_otp,
    }
    
    try:
        result = subprocess.run(
            ["node", "--import", "tsx", "index.ts"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=240,
            check=False,
            cwd="/root/my-stagehand-app",
            env={**os.environ, "CHROME_PATH": "/usr/bin/chromium"}
        )
        
        if result.returncode != 0:
            return {
                "status": "failed",
                "error": "booking_failed",
                "stderr": result.stderr[-2000:],
                "stdout": result.stdout[-2000:],
            }
        
        # Parse last JSON line from stdout
        lines = result.stdout.strip().split('\n')
        for line in reversed(lines):
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    return parsed
                return {"status": "success", "output": parsed}
            except:
                continue
        
        return {"status": "success", "output": result.stdout}
        
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": "timeout"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("booking-secrets")],
    timeout=300,
)
def run_uber_estimate(origin: str, destination: str):
    """
    Standalone Modal function for Uber price estimation.
    Runs Stagehand in Browserbase, returns structured estimates.
    Designed to be called via .spawn() for async execution.
    """
    import subprocess
    import os

    payload = {"origin": origin, "destination": destination}

    try:
        result = subprocess.run(
            ["node", "--import", "tsx", "uber-estimate.ts"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=240,
            check=False,
            cwd="/root/my-stagehand-app",
            env={**os.environ, "CHROME_PATH": "/usr/bin/chromium"},
        )

        if result.returncode != 0:
            return {
                "status": "failed",
                "error": "uber_estimate_failed",
                "stderr": result.stderr[-2000:],
                "stdout": result.stdout[-2000:],
            }

        # Parse last JSON line from stdout
        lines = result.stdout.strip().split("\n")
        for line in reversed(lines):
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    all_estimates = parsed.get("estimates", [])
                    keep = {"uberx", "uberxl", "share"}
                    filtered = [
                        e for e in all_estimates
                        if e.get("service", "").lower() in keep
                        and e.get("duration", "").lower() != "unavailable"
                    ]
                    parsed["estimates"] = filtered
                    return parsed
                return {"status": "success", "output": parsed}
            except Exception:
                continue

        return {"status": "success", "output": result.stdout}

    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": "timeout"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("booking-secrets")],
    timeout=600,
)
@modal.asgi_app()
def mcp_server():
    """
    MCP HTTP endpoint for Poke integration at /mcp path.
    """
    from fastmcp import FastMCP

    mcp = FastMCP("TreeHacks MCP")
    
    @mcp.tool(description="Start an async restaurant reservation booking. Returns a request_id immediately — use check_booking to poll for results.")
    def start_booking(
        url: str,
        time_text: str,
        party_size: int,
        phone: str | None = None,
        otp_code: str | None = None,
        skip_to_otp: bool | None = None,
    ) -> dict:
        """
        Kick off a restaurant reservation in the background. Returns instantly
        with a request_id. Call check_booking with that ID to get results.

        Args:
            url: OpenTable restaurant URL
            time_text: Desired time (e.g., "7:30 PM")
            party_size: Number of people
            phone: Phone number for reservation
            otp_code: OTP code if needed
            skip_to_otp: Whether to skip to OTP step
        """
        call = book_restaurant.spawn(url, time_text, party_size, phone, otp_code, skip_to_otp)
        return {
            "status": "processing",
            "request_id": call.object_id,
            "message": f"Booking started for {url} at {time_text} for {party_size}. Use check_booking with this request_id to get results.",
        }

    @mcp.tool(description="Check the status of a previously started restaurant booking. Pass the request_id from start_booking.")
    def check_booking(
        request_id: str,
    ) -> dict:
        """
        Poll for the result of an async restaurant booking.

        Args:
            request_id: The request_id returned by start_booking
        """
        fc = modal.FunctionCall.from_id(request_id)
        try:
            result = fc.get(timeout=0)
            return result
        except TimeoutError:
            return {
                "status": "processing",
                "request_id": request_id,
                "message": "Still running. Call check_booking again in a few seconds.",
            }
    
    @mcp.tool(description="Start an async Uber price estimate lookup. Returns a request_id immediately — use check_rideshare_estimate to poll for results.")
    def start_rideshare_estimate(
        origin: str,
        destination: str,
    ) -> dict:
        """
        Kick off an Uber price estimate in the background. Returns instantly
        with a request_id. Call check_rideshare_estimate with that ID to get results.

        Args:
            origin: Full pickup address/place name (e.g. "Soda Hall, Berkeley, CA")
            destination: Full dropoff address/place name (e.g. "Noodle Dynasty, Berkeley, CA")
        """
        call = run_uber_estimate.spawn(origin, destination)
        return {
            "status": "processing",
            "request_id": call.object_id,
            "message": f"Uber estimate started for {origin} → {destination}. Use check_rideshare_estimate with this request_id to get results.",
        }

    @mcp.tool(description="Check the status of a previously started Uber price estimate. Pass the request_id from start_rideshare_estimate.")
    def check_rideshare_estimate(
        request_id: str,
    ) -> dict:
        """
        Poll for the result of an async Uber price estimate.

        Args:
            request_id: The request_id returned by start_rideshare_estimate
        """
        fc = modal.FunctionCall.from_id(request_id)
        try:
            result = fc.get(timeout=0)
            return result
        except TimeoutError:
            return {
                "status": "processing",
                "request_id": request_id,
                "message": "Still running. Call check_rideshare_estimate again in a few seconds.",
            }

    # Get the MCP ASGI app - using 'streamable-http' transport which is more stable
    mcp_asgi = mcp.http_app(path="/mcp", stateless_http=True, transport="streamable-http")
    
    return mcp_asgi


if __name__ == "__main__":
    # For local testing
    print("Done")
