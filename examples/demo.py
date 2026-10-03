"""Run the documented two-client exchange in a disposable local mailbox.

Uses the installed agent-dms console and real SDK clients, without provider APIs.
"""
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    console = Path(sys.executable).with_name("agent-dms")
    if not console.is_file():
        raise SystemExit("Install agent-dms in this Python environment first; see docs/INSTALL.md")
    client_example = Path(__file__).with_name("two_clients.py").resolve()
    with tempfile.TemporaryDirectory(prefix="agent-dms-demo-") as temporary:
        project = Path(temporary)
        data = project / ".agent-dms"

        def operator(*args):
            result = subprocess.run([str(console), *map(str, args)], cwd=project,
                                    check=True, capture_output=True, text=True, timeout=30)
            return json.loads(result.stdout)

        operator("init", "--project-root", project)
        manager = operator("agent", "--data-dir", data, "add", "Manager", "--provider", "sdk-demo")
        worker = operator("agent", "--data-dir", data, "add", "Worker", "--provider", "sdk-demo")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        with (project / "server.log").open("w") as log:
            process = subprocess.Popen([str(console), "serve", "--data-dir", str(data),
                                        "--port", str(port)], cwd=project, stdout=log, stderr=log)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                deadline = time.monotonic() + 15
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Temporary server exited before readiness")
                    try:
                        with opener.open(origin + "/health/ready", timeout=1) as response:
                            if json.load(response) == {"ok": True}:
                                break
                    except (OSError, urllib.error.URLError):
                        pass
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Temporary server did not become ready")
                    time.sleep(0.1)
                result = subprocess.run([
                    sys.executable, str(client_example), "--url", origin + "/mcp",
                    "--manager-token-file", manager["credential_file"],
                    "--worker-token-file", worker["credential_file"],
                ], cwd=project, check=True, text=True, capture_output=True, timeout=45)
                required = ("Manager (online)", "Worker (online)",
                            "Reply and explicit parent ACK:", "Explicit reply ACK: handled")
                if not all(part in result.stdout for part in required):
                    raise RuntimeError("Demo did not complete the documented DM/ACK exchange")
                print(result.stdout, end="")
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    print("Demo passed; temporary mailbox removed.")


if __name__ == "__main__":
    main()
