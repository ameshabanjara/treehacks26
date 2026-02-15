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
            timeout=120,
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
    timeout=600,
)
@modal.asgi_app()
def mcp_server():
    """
    MCP HTTP endpoint for Poke integration at /mcp path.
    """
    from fastmcp import FastMCP
    import subprocess
    import json
    import os
    
    mcp = FastMCP("TreeHacks MCP")
    
    @mcp.tool(description="Book a restaurant reservation using browser automation.")
    def book_restaurant_tool(
        url: str,
        time_text: str,
        party_size: int,
        phone: str | None = None,
        otp_code: str | None = None,
    ) -> dict:
        """
        Book a restaurant reservation using Stagehand browser automation.
        
        Args:
            url: OpenTable restaurant URL
            time_text: Desired time (e.g., "7:30 PM")
            party_size: Number of people
        """
        payload = {
            "url": url,
            "time_text": time_text,
            "party_size": party_size,
            "phone": phone,
            "otp_code": otp_code,
        }
        
        try:
            result = subprocess.run(
                ["node", "--import", "tsx", "index.ts"],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=120,
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
    
    @mcp.tool(description="Get real-time Uber price estimates between two locations.")
    def estimate_rideshare(
        origin: str,
        destination: str,
    ) -> dict:
        """
        Scrape uber.com/price-estimate for live ride prices using Stagehand
        with a persistent authenticated Browserbase context.

        Args:
            origin: Full pickup address/place name (e.g. "Soda Hall, Berkeley, CA")
            destination: Full dropoff address/place name (e.g. "Noodle Dynasty, Berkeley, CA")
        """
        payload = {"origin": origin, "destination": destination}

        try:
            result = subprocess.run(
                ["node", "--import", "tsx", "uber-estimate.ts"],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=120,
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
                        # Only keep rides people actually use
                        keep = {"uberx", "uberxl", "share"}
                        filtered = [
                            e for e in all_estimates
                            if e.get("service", "").lower() in keep
                            and e.get("duration", "").lower() != "unavailable"
                        ]
                        parsed["estimates"] = filtered
                        return parsed
                    return {"status": "success", "output": parsed}
                except:
                    continue

            return {"status": "success", "output": result.stdout}

        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "timeout"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # Get the MCP ASGI app - using 'streamable-http' transport which is more stable
    mcp_asgi = mcp.http_app(path="/mcp", stateless_http=True, transport="streamable-http")
    
    return mcp_asgi


if __name__ == "__main__":
    # For local testing
    print("Done")
