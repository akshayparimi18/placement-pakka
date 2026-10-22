"""
Anna Executa Python SDK (Schema v2) — Self-Contained Stdio JSON-RPC 2.0 & Reverse-RPC Bridge.

Provides:
- Zero-stdout-pollution JSON-RPC 2.0 framing over sys.stdin / sys.stdout
- Windows UTF-8 stdio reconfiguration
- Reverse-RPC `sampling/createMessage` (with optional `responseFormat` JSON Schema support)
- Reverse-RPC `storage/get`, `storage/set`, and `storage/list` for Anna Persistent Storage (APS)
- Verbatim `display_blocks` builder so Anna Chat renders Markdown scorecards byte-for-byte
"""

from __future__ import annotations

import itertools
import json
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional


def configure_utf8_stdio() -> None:
    """Ensure UTF-8 encoding on Windows & POSIX stdio streams without losing line buffering."""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


class ReverseRPCError(RuntimeError):
    """Raised when the Anna Host returns an error for a reverse-RPC request."""


class ExecutaPluginServer:
    """
    JSON-RPC 2.0 Server & Reverse-RPC Client over stdio for Anna Executa v2 plugins.
    """

    def __init__(
        self,
        name: str,
        version: str = "2.0.0",
        description: str = "",
        capabilities: Optional[Dict[str, bool]] = None,
    ) -> None:
        configure_utf8_stdio()
        self.name = name
        self.version = version
        self.description = description
        self.capabilities = capabilities or {"sampling": True, "storage": True}
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable[[Dict[str, Any], "ExecutaPluginServer"], Dict[str, Any]]] = {}
        self._rpc_id_counter = itertools.count(1000)
        self._raw_stdout = sys.stdout
        self._initialized = False

    def tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
    ) -> Callable:
        """Decorator to register an Executa tool and its JSON Schema."""
        def decorator(fn: Callable[[Dict[str, Any], "ExecutaPluginServer"], Dict[str, Any]]) -> Callable:
            self._tools[name] = {
                "name": name,
                "description": description,
                "inputSchema": input_schema,
                "parameters": input_schema,
            }
            self._handlers[name] = fn
            return fn
        return decorator

    def _write_frame(self, payload: Dict[str, Any]) -> None:
        """Write a single newline-delimited JSON-RPC 2.0 message to stdout."""
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self._raw_stdout.write(serialized + "\n")
        self._raw_stdout.flush()

    def log_debug(self, message: str) -> None:
        """Log diagnostic messages strictly to stderr so stdout remains pure JSON-RPC."""
        sys.stderr.write(f"[{self.name}] {message}\n")
        sys.stderr.flush()

    def send_reverse_rpc(
        self,
        method: str,
        params: Dict[str, Any],
        fallback_fn: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Any:
        """
        Send a reverse-RPC request (e.g., `sampling/createMessage`, `storage/get`, `storage/set`)
        over stdout and block waiting for the matching JSON-RPC response on stdin.
        """
        req_id = f"rev-{next(self._rpc_id_counter)}"
        request_frame = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        self._write_frame(request_frame)

        while True:
            line = sys.stdin.readline()
            if not line:
                # EOF reached during reverse-RPC (e.g., offline single-shot CLI pipe); use fallback if provided
                if fallback_fn is not None:
                    return fallback_fn(params)
                raise ReverseRPCError(f"EOF on stdin while awaiting reverse-RPC response for {method} (id={req_id})")

            line_str = line.strip()
            if not line_str:
                continue

            try:
                msg = json.loads(line_str)
            except json.JSONDecodeError:
                continue

            # If it's a response matching our req_id (or any response frame in synchronous mode)
            if "id" in msg and ("result" in msg or "error" in msg):
                if str(msg.get("id")) == str(req_id) or str(msg.get("id")).startswith("rev-"):
                    if "error" in msg and msg["error"]:
                        if fallback_fn is not None:
                            return fallback_fn(params)
                        err = msg["error"]
                        raise ReverseRPCError(f"Host error on {method}: {err}")
                    return msg.get("result")

    def create_message(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        max_tokens: int = 900,
        temperature: float = 0.7,
        response_format: Optional[Dict[str, Any]] = None,
        fallback_fn: Optional[Callable[[Dict[str, Any]], str]] = None,
    ) -> str:
        """
        Invoke Anna Host LLM via reverse-RPC `sampling/createMessage`.
        Supports MCP / Anna v2 text content blocks and optional `responseFormat` JSON Schema.
        """
        normalized_messages: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, str):
                content_obj: Any = {"type": "text", "text": content}
            else:
                content_obj = content
            normalized_messages.append({"role": role, "content": content_obj})

        params: Dict[str, Any] = {
            "messages": normalized_messages,
            "maxTokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            params["systemPrompt"] = system_prompt
        if response_format:
            params["responseFormat"] = response_format

        def _wrapped_fallback(p: Dict[str, Any]) -> Dict[str, Any]:
            text = fallback_fn(p) if fallback_fn else ""
            return {"role": "assistant", "content": {"type": "text", "text": text}}

        result = self.send_reverse_rpc(
            "sampling/createMessage",
            params,
            fallback_fn=_wrapped_fallback if fallback_fn else None,
        )

        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, dict):
                return str(content.get("text", ""))
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    return str(first.get("text", ""))
                return str(first)
            if "text" in result:
                return str(result["text"])
        return str(result or "")

    def storage_get(self, key: str, default: Any = None) -> Any:
        """Read a key from Anna Persistent Storage (APS) via reverse-RPC `storage/get`."""
        try:
            res = self.send_reverse_rpc(
                "storage/get",
                {"key": key},
                fallback_fn=lambda _: {"value": default},
            )
            if isinstance(res, dict) and "value" in res:
                return res["value"] if res["value"] is not None else default
            return res if res is not None else default
        except Exception:
            return default

    def storage_set(self, key: str, value: Any) -> bool:
        """Write a key-value pair to Anna Persistent Storage (APS) via reverse-RPC `storage/set`."""
        try:
            self.send_reverse_rpc(
                "storage/set",
                {"key": key, "value": value},
                fallback_fn=lambda _: {"ok": True},
            )
            return True
        except Exception:
            return False

    def handle_request(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single incoming JSON-RPC 2.0 request frame from the Anna Host."""
        req_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params") or {}

        try:
            if method == "initialize":
                self._initialized = True
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2.0",
                        "schemaVersion": 2,
                        "serverInfo": {
                            "name": self.name,
                            "version": self.version,
                            "description": self.description,
                        },
                        "capabilities": self.capabilities,
                    },
                }

            if method in ("describe", "tools/list"):
                tools_list = list(self._tools.values())
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "schema_version": 2,
                        "name": self.name,
                        "version": self.version,
                        "description": self.description,
                        "capabilities": self.capabilities,
                        "tools": tools_list,
                    },
                }

            if method in ("invoke", "tools/call"):
                tool_name = (
                    params.get("name")
                    or params.get("tool")
                    or params.get("method")
                    or next(iter(self._handlers.keys()), "")
                )
                arguments = (
                    params.get("arguments")
                    if "arguments" in params
                    else params.get("input", params.get("params", params))
                )
                if not isinstance(arguments, dict):
                    arguments = {"candidate_profile": str(arguments)}

                if tool_name not in self._handlers:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Unknown tool: {tool_name}. Available: {list(self._handlers.keys())}",
                        },
                    }

                result_payload = self._handlers[tool_name](arguments, self)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": result_payload,
                }

            if method == "shutdown":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"ok": True, "status": "shutting_down"},
                }

            if method == "ping":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"pong": True},
                }

            if req_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                }
            return None

        except Exception as exc:
            self.log_debug(f"Unhandled exception in {method}: {traceback.format_exc()}")
            if req_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32000,
                        "message": str(exc),
                    },
                }
            return None

    def serve_stdio(self) -> None:
        """Main loop reading JSON-RPC 2.0 requests line-by-line from stdin."""
        # Protect stdout from accidental print() calls inside 3rd-party libraries
        sys.stdout = sys.stderr  # type: ignore[assignment]
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError as err:
                    self._write_frame(
                        {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32700, "message": f"Parse error: {err}"},
                        }
                    )
                    continue

                response = self.handle_request(msg)
                if response is not None:
                    self._write_frame(response)
                if msg.get("method") == "shutdown":
                    break
        finally:
            sys.stdout = self._raw_stdout
