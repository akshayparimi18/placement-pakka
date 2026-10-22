#!/usr/bin/env python3
"""
Automated Smoke Test Suite (`test_plugin.py`) for Placement Pakka (`placement-panel` Executa v2).

Verifies:
1. `anna-app.json` and `executas/placement-panel/executa.json` Schema v2 validity & required grants.
2. Zero stdout pollution during JSON-RPC 2.0 over stdio handshake (`initialize`, `describe`).
3. Full 3-node multi-agent `invoke` (`evaluate_candidate`) with live bidirectional mocked reverse-RPC
   `sampling/createMessage` responses from the simulated Anna Host.
4. Validation of structured JSON output (`hire_score`, `predicted_ctc_lpa`, `badge_title`, `hr_quote`,
   `top_fixes`, `action_items`, `image_prompt`) AND verbatim Markdown in `display_blocks`.
5. Clean `shutdown` handshake.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent
PLUGIN_PATH = ROOT_DIR / "executas" / "placement-panel" / "panel_plugin.py"
APP_MANIFEST_PATH = ROOT_DIR / "anna-app.json"
EXECUTA_MANIFEST_PATH = ROOT_DIR / "executas" / "placement-panel" / "executa.json"
SKILL_PATH = ROOT_DIR / "skills" / "placement-coach" / "SKILL.md"


def test_manifests_and_skill() -> None:
    """Verify anna-app.json, executa.json, and SKILL.md meet all Schema v2 requirements."""
    assert APP_MANIFEST_PATH.exists(), "anna-app.json is missing"
    app_manifest = json.loads(APP_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert app_manifest.get("schema_version") >= 2, "anna-app.json schema_version must be >= 2"
    assert app_manifest.get("id") == "placement-pakka"
    assert "prompt_instructions" in app_manifest and "evaluate_candidate" in app_manifest["prompt_instructions"]

    ui = app_manifest.get("ui", {})
    assert set(ui.get("form_factors", [])) >= {"desktop", "mobile"}
    window = ui.get("window", {})
    assert window.get("singleton") is True
    assert window.get("width") == 920 and window.get("height") == 680

    required_grants = {
        "llm.complete",
        "tools.call",
        "storage.get",
        "storage.set",
        "storage.list",
        "image.generate",
        "audio.session",
        "audio.speak",
        "audio.transcribe",
        "chat.append_artifact",
        "window.Control",
        "mobile.share",
    }
    actual_grants = set(ui.get("host_api", {}).get("grants", []))
    missing_grants = required_grants - actual_grants
    assert not missing_grants, f"Missing required host_api.grants: {missing_grants}"

    assert EXECUTA_MANIFEST_PATH.exists(), "executa.json is missing"
    executa_manifest = json.loads(EXECUTA_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert executa_manifest.get("schema_version") == 2
    assert executa_manifest.get("capabilities", {}).get("sampling") is True
    assert executa_manifest.get("capabilities", {}).get("storage") is True

    assert SKILL_PATH.exists(), "SKILL.md is missing"
    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    assert skill_text.startswith("---"), "SKILL.md must start with YAML frontmatter"
    assert "name: placement-coach" in skill_text
    assert "evaluate_candidate" in skill_text
    print("[PASS] Manifests (anna-app.json, executa.json) and SKILL.md validated.")


def test_stdio_jsonrpc_and_reverse_sampling() -> None:
    """
    Spawn `panel_plugin.py` as a child process over stdio pipes and simulate the Anna Host:
    1. Send `initialize` -> assert capabilities (`sampling: true`, `storage: true`)
    2. Send `describe`   -> assert `evaluate_candidate` tool schema is registered
    3. Send `invoke` (`evaluate_candidate`) -> intercept 3 reverse-RPC `sampling/createMessage`
       requests on stdout (Node 1 Architect, Node 2 PM, Node 3 HR) and feed mock host LLM responses
       back via stdin!
    4. Assert final `invoke` result contains structured JSON in `content` AND verbatim Markdown in `display_blocks`.
    5. Send `shutdown` -> assert clean exit with zero non-JSON lines on stdout.
    """
    proc = subprocess.Popen(
        [sys.executable, str(PLUGIN_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None

    def send_rpc(frame: Dict[str, Any]) -> None:
        proc.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    def read_rpc_frame() -> Dict[str, Any]:
        line = proc.stdout.readline()
        assert line, "Unexpected EOF from panel_plugin.py stdout"
        stripped = line.strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"Stdout pollution detected! Non-JSON line on stdout: {stripped!r}") from exc
        assert parsed.get("jsonrpc") == "2.0", f"Invalid JSON-RPC frame: {parsed}"
        return parsed

    try:
        # 1. Test `initialize`
        send_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "anna-host-test"}}})
        init_resp = read_rpc_frame()
        assert init_resp["id"] == 1
        caps = init_resp["result"]["capabilities"]
        assert caps.get("sampling") is True and caps.get("storage") is True
        print("[PASS] `initialize` handshake verified (sampling=True, storage=True).")

        # 2. Test `describe`
        send_rpc({"jsonrpc": "2.0", "id": 2, "method": "describe", "params": {}})
        desc_resp = read_rpc_frame()
        assert desc_resp["id"] == 2
        tools = desc_resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "evaluate_candidate" in tool_names
        print(f"[PASS] `describe` verified (registered tools: {tool_names}).")

        # 3. Test `invoke` (`evaluate_candidate`) with 3-node reverse-RPC `sampling/createMessage`
        send_rpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "invoke",
                "params": {
                    "name": "evaluate_candidate",
                    "arguments": {
                        "candidate_profile": (
                            "Final year B.Tech CSE student. Built a MERN Stack E-Commerce clone and a Weather App. "
                            "Solved 250 LeetCode problems (180 Easy, 65 Medium, 5 Hard). Seeking Product SDE-1."
                        ),
                        "mode": "roast",
                        "track": "product_sde",
                    },
                },
            }
        )

        sampling_calls: List[Dict[str, Any]] = []
        while True:
            incoming = read_rpc_frame()
            # Check if this frame is a reverse-RPC request from the plugin to the host
            if incoming.get("method") == "sampling/createMessage":
                sampling_calls.append(incoming)
                rev_id = incoming["id"]
                call_num = len(sampling_calls)

                if call_num == 1:
                    # Node 1: Architect response
                    mock_text = (
                        "Sharma Ji nearly choked on his evening samosa seeing 180 Easy LeetCode questions passed off "
                        "as Product SDE readiness. Your MERN E-Commerce clone uses zero Redis caching, no database "
                        "transactions for inventory locking, and would crash the moment two hostelers buy the same hoodie."
                    )
                elif call_num == 2:
                    # Node 2: Startup PM response + GRILL_QUESTION
                    mock_text = (
                        "Nobody needs another Weather App when every phone has a lock screen widget! You listed "
                        "'scalable microservices' on a single Express.js file with zero active users.\n"
                        "GRILL_QUESTION: Two users click 'Buy Now' on the last iPhone in stock at the exact same "
                        "millisecond in your MERN store—how do you prevent double-charging without locking the entire table?"
                    )
                else:
                    # Node 3: HR Head structured JSON response
                    mock_text = json.dumps(
                        {
                            "hire_score": 64,
                            "predicted_ctc_lpa": "14.5 LPA (Tier-2 Product SDE-1 Contender)",
                            "badge_title": "180-Easy LeetCode Comfort Zone CEO",
                            "hr_quote": "Shift your ratio from LeetCode Easys to Medium/Hards and deploy one real system with concurrency control to crack 24+ LPA.",
                            "top_fixes": [
                                "Replace the Weather App with a concurrency-safe booking or payment microservice using PostgreSQL row-level locking and Redis.",
                                "Push your LeetCode Medium/Hard ratio to at least 60% and add your contest rating to the header.",
                                "Quantify API latency (p95 ms) and load-testing throughput (requests/sec) in your E-Commerce bullet points.",
                            ],
                            "image_prompt": "3D cyberpunk owl architect sticker holding a 14.5 LPA golden placard and laptop, dark neon indigo background, text-free",
                        }
                    )

                send_rpc(
                    {
                        "jsonrpc": "2.0",
                        "id": rev_id,
                        "result": {
                            "role": "assistant",
                            "model": "anna-host-mock-v2",
                            "content": {"type": "text", "text": mock_text},
                        },
                    }
                )
            elif incoming.get("id") == 3:
                # Final `invoke` response received!
                invoke_resp = incoming
                break
            else:
                raise AssertionError(f"Unexpected frame during invoke: {incoming}")

        assert len(sampling_calls) == 3, f"Expected 3 reverse-RPC sampling calls (Architect, PM, HR), got {len(sampling_calls)}"
        print("[PASS] 3-node reverse-RPC `sampling/createMessage` pipeline executed (Architect -> PM -> HR).")

        result = invoke_resp["result"]
        assert result.get("isError") is False

        # Verify structured JSON in `content`
        content_blocks = result.get("content", [])
        assert len(content_blocks) >= 1 and content_blocks[0]["type"] == "text"
        payload = json.loads(content_blocks[0]["text"])

        assert payload["hire_score"] == 64
        assert payload["predicted_ctc_lpa"] == "14.5 LPA (Tier-2 Product SDE-1 Contender)"
        assert payload["badge_title"] == "180-Easy LeetCode Comfort Zone CEO"
        assert len(payload["top_fixes"]) == 3
        assert len(payload["action_items"]) == 3
        assert "Two users click" in payload["grill_question"]

        # Verify verbatim Markdown in `display_blocks`
        display_blocks = result.get("display_blocks", [])
        assert len(display_blocks) >= 1
        md_text = display_blocks[0].get("markdown") or display_blocks[0].get("text", "")
        assert "Placement Pakka — Official CTC Scorecard" in md_text
        assert "14.5 LPA (Tier-2 Product SDE-1 Contender)" in md_text
        assert "Sharma Ji The Brutal Staff Architect" in md_text
        assert "180-Easy LeetCode Comfort Zone CEO" in md_text
        print("[PASS] Structured JSON `content` and verbatim Markdown `display_blocks` verified.")

        # 4. Test `shutdown`
        send_rpc({"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        shut_resp = read_rpc_frame()
        assert shut_resp["id"] == 4 and shut_resp["result"]["ok"] is True
        print("[PASS] `shutdown` clean exit verified with zero stdout pollution.")

    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    test_manifests_and_skill()
    test_stdio_jsonrpc_and_reverse_sampling()
    print("\nALL PLACEMENT PAKKA SCHEMA V2 CHECKS PASSED SUCCESSFULLY!")
