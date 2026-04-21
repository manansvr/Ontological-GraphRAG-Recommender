#!/usr/bin/env python3
import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()


def _rl_enabled() -> bool:
    return os.getenv("RL_ENABLED", "true").lower() == "true"


def _rl_model_path() -> str:
    return os.getenv("RL_MODEL_PATH", ".rl-model.json")


class _RLBridge:
    """Runtime bridge to the user-named RL module file.

    The RL module file is intentionally named `reinforcemnt-learning.py`
    to match user preference, so dynamic loading is used.
    """

    def __init__(self) -> None:
        self.enabled = False
        self._agent: Any = None
        self._transition_cls: Any = None
        self._model_path = _rl_model_path()

        if not _rl_enabled():
            return

        module_path = Path(__file__).resolve().with_name("reinforcemnt-learning.py")
        if not module_path.exists():
            print("[rl] module file not found, RL disabled")
            return

        try:
            spec = importlib.util.spec_from_file_location("reinforcemnt_learning_module", module_path)
            if not spec or not spec.loader:
                print("[rl] failed to load module spec, RL disabled")
                return

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            self._transition_cls = getattr(module, "Transition")
            q_learning_cls = getattr(module, "QLearningAgent")

            model_path = Path(self._model_path)
            if model_path.exists():
                self._agent = q_learning_cls.load(model_path)
                print(f"[rl] loaded model from {self._model_path}")
            else:
                self._agent = q_learning_cls()
                print("[rl] initialized new model")

            self.enabled = True
        except Exception as exc:
            print(f"[rl] initialization failed, RL disabled: {exc}")
            self.enabled = False

    def choose_action(self, state: str, actions: list[str]) -> str | None:
        if not self.enabled or not actions:
            return None
        try:
            return self._agent.choose_action(state, actions)
        except Exception as exc:
            print(f"[rl] choose_action failed: {exc}")
            return None

    def update_and_save(self, state: str, action: str | None, reward: float, next_state: str, next_actions: list[str]) -> None:
        if not self.enabled or not action:
            return
        try:
            transition = self._transition_cls(state, action, reward, next_state, next_actions)
            self._agent.update(transition)
            self._agent.decay_exploration()
            self._agent.save(self._model_path)
        except Exception as exc:
            print(f"[rl] update/save failed: {exc}")


def _rl_state_and_actions(user_input: str) -> tuple[str, list[str]]:
    rule_id = _extract_rule_id_from_question(user_input)
    if rule_id:
        return "adr_lookup", ["graph_first", "documents_first", "hybrid"]
    return "general_lookup", ["documents_first"]


def _rl_reward(content: str, tool_used: bool, evidence_refs: list[str]) -> float:
    if "I do not have enough context in the indexed sources to answer that." in content:
        return -0.8
    reward = 0.0
    if tool_used:
        reward += 0.2
    if _has_explicit_citation(content) or evidence_refs:
        reward += 0.8
    else:
        reward -= 0.2
    return reward


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _ollama_model(default: str | None = None) -> str:
    return default or os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def _strict_context_only() -> bool:
    return os.getenv("STRICT_CONTEXT_ONLY", "true").lower() == "true"


def _require_explicit_citations() -> bool:
    return os.getenv("REQUIRE_EXPLICIT_CITATIONS", "true").lower() == "true"


def _has_explicit_citation(text: str) -> bool:
    return bool(re.search(r"(/[^\s]+\.(csv|md|txt|pdf|docx))(?:\s*\|\s*(row|line)\s*\d+)", text, flags=re.IGNORECASE))


def _extract_evidence_refs(tool_text: str, max_refs: int = 3) -> list[str]:
    refs: list[str] = []
    try:
        obj = json.loads(tool_text)
    except Exception:
        return refs

    matches = obj.get("matches", []) if isinstance(obj, dict) else []
    for m in matches:
        path = m.get("path", "")
        pointer_type = m.get("pointer_type", "")
        hits = m.get("hits", [])
        if not path or not hits:
            continue
        hit0 = hits[0] if isinstance(hits[0], dict) else {}
        if pointer_type == "row" and "row" in hit0:
            refs.append(f"{path} | row {hit0['row']}")
        elif pointer_type == "line" and "line" in hit0:
            refs.append(f"{path} | line {hit0['line']}")
        if len(refs) >= max_refs:
            break

    if refs:
        return refs

    # get_adr_requirements can provide explicit evidence references.
    if isinstance(obj, dict) and isinstance(obj.get("evidence_refs"), list):
        for ref in obj.get("evidence_refs", []):
            if isinstance(ref, str) and ref.strip():
                refs.append(ref.strip())
            if len(refs) >= max_refs:
                break

    if refs:
        return refs

    # Fallback for read_document output
    if isinstance(obj, dict) and "path" in obj and ("start_line" in obj or "line" in obj):
        path = obj.get("path", "")
        line = obj.get("start_line", obj.get("line", ""))
        if path and line:
            refs.append(f"{path} | line {line}")

    return refs[:max_refs]


def _extract_rule_id_from_question(text: str) -> str | None:
    m = re.search(r"\b(?:ADR|SRP)[\s_-]?0*\d{1,3}\b", text, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(0).replace(" ", "")


def _is_count_requirements_question(text: str) -> bool:
    t = text.lower()
    return "how many" in t and "requir" in t


def _is_reference_question(text: str) -> bool:
    t = text.lower()
    return "reference" in t and _extract_rule_id_from_question(text) is not None


def _is_design_guidance_question(text: str) -> bool:
    t = text.lower()
    return any(
        keyword in t
        for keyword in [
            "design",
            "manufactur",
            "fabricat",
            "assembly",
            "build",
            "prototype",
            "conceptual",
            "preliminary",
            "detailed",
            "procure",
            "quality control",
        ]
    )


def _design_guidance_redirect(text: str) -> dict[str, str] | None:
    t = text.lower()
    if any(keyword in t for keyword in ["manufactur", "fabricat", "assembly", "procure", "quality control", "build"]):
        return {
            "query": "Manufacturing Section",
            "redirect": "For the detailed manufacturing checklist, see [Manufacturing Section.pdf](/Users/manan/Desktop/Honours/thesis-extraction/Design-Documentation/Manufacturing%20Section.pdf#L1) (Manufacturing).",
        }

    if _is_design_guidance_question(text):
        return {
            "query": "The Design Process",
            "redirect": "For the broader design workflow, see [Design Manual.pdf](/Users/manan/Desktop/Honours/thesis-extraction/Design-Documentation/Design%20Manual.pdf#L111) (The Design Process).",
        }

    return None


def _format_requirements_listing(payload: dict[str, Any]) -> str:
    adr_id = payload.get("adr_id", "")
    count = payload.get("count", 0)
    req_rows = payload.get("requirements", [])
    evidence_refs = payload.get("evidence_refs", [])

    unique_reqs: list[str] = []
    seen: set[str] = set()
    for row in req_rows:
        req = (row.get("requirement") or "").strip()
        if not req:
            continue
        key = req.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_reqs.append(req)

    lines = [f"{adr_id} has {count} requirements."]
    if unique_reqs:
        lines.append("Requirements:")
        for i, req in enumerate(unique_reqs, start=1):
            lines.append(f"{i}. {req}")
    else:
        lines.append("No requirement text was returned.")

    if evidence_refs:
        lines.append("")
        lines.append(f"Evidence: {evidence_refs[0]}")

    return "\n".join(lines)


def _format_reference_listing(rule_id: str, req_payload: dict[str, Any], doc_payload: dict[str, Any]) -> str:
    adr_id = req_payload.get("adr_id", rule_id)
    req_count = req_payload.get("count", 0)
    refs = req_payload.get("evidence_refs", [])
    matches = doc_payload.get("matches", []) if isinstance(doc_payload, dict) else []

    lines = [f"References found for {adr_id}."]
    lines.append(f"Requirements linked: {req_count}")

    if matches:
        lines.append("Document references:")
        for i, m in enumerate(matches[:10], start=1):
            path = m.get("path", "")
            ptype = m.get("pointer_type", "")
            hits = m.get("hits", [])
            pointer = ""
            if hits:
                first = hits[0]
                if ptype == "row" and "row" in first:
                    pointer = f"row {first['row']}"
                elif ptype == "line" and "line" in first:
                    pointer = f"line {first['line']}"
            if path and pointer:
                lines.append(f"{i}. {path} | {pointer}")
            elif path:
                lines.append(f"{i}. {path}")
    else:
        lines.append("No document references were returned from local search.")

    if refs:
        lines.append("")
        lines.append(f"Evidence: {refs[0]}")

    return "\n".join(lines)


def _tool_to_ollama_schema(tool: Any) -> dict[str, Any]:
    schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "MCP tool",
            "parameters": schema if schema else {"type": "object", "properties": {}},
        },
    }


def _post_chat(model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    response = requests.post(
        f"{_ollama_base_url().rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0.2},
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


async def run_chat(model: str, server_command: str, server_args: list[str]) -> None:
    server_params = StdioServerParameters(command=server_command, args=server_args)

    async with stdio_client(server_params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tool_list = await session.list_tools()
            tools = [_tool_to_ollama_schema(t) for t in tool_list.tools]

            system_prompt = (
                "You are connected to MCP tools for local SR8 documents and a Neo4j knowledge graph. "
                "You must answer only from MCP tool context returned in this chat session. "
                "If the context is missing, insufficient, or ambiguous, do not guess. "
                "Instead say: 'I do not have enough context in the indexed sources to answer that.' "
                "For factual questions, call tools first and cite concrete file evidence. "
                "If the user asks about design or manufacturing, answer from the indexed documents and then append the relevant redirect to the Design Manual or Manufacturing Section."
            )

            messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            rl_bridge = _RLBridge()

            print("Connected. Type your prompt, or /exit to quit.")
            print(f"Model: {model}")
            print("Tools:")
            for t in tool_list.tools:
                print(f"  - {t.name}")

            while True:
                user_input = input("\nYou: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in {"/exit", "exit", "quit"}:
                    break

                # Deterministic path for count+list requirement questions by ADR/SRP ID.
                if _is_count_requirements_question(user_input):
                    rule_id = _extract_rule_id_from_question(user_input)
                    if rule_id:
                        print(f"\n[tool] get_adr_requirements({{'adr_id': '{rule_id}', 'limit': 1000}})")
                        tool_result = await session.call_tool("get_adr_requirements", {"adr_id": rule_id, "limit": 1000})

                        tool_text_parts: list[str] = []
                        for part in tool_result.content:
                            text = getattr(part, "text", None)
                            if text:
                                tool_text_parts.append(text)
                        tool_text = "\n".join(tool_text_parts) if tool_text_parts else "{}"

                        try:
                            payload = json.loads(tool_text)
                        except Exception:
                            payload = {"adr_id": rule_id, "count": 0, "requirements": [], "evidence_refs": []}

                        content = _format_requirements_listing(payload)
                        print(f"\nAssistant: {content}")
                        messages.append({"role": "user", "content": user_input})
                        messages.append({"role": "assistant", "content": content})
                        continue

                # Deterministic path for reference queries by ADR/SRP ID.
                if _is_reference_question(user_input):
                    rule_id = _extract_rule_id_from_question(user_input)
                    if rule_id:
                        print(f"\n[tool] get_adr_requirements({{'adr_id': '{rule_id}', 'limit': 1000}})")
                        req_result = await session.call_tool("get_adr_requirements", {"adr_id": rule_id, "limit": 1000})

                        req_text_parts: list[str] = []
                        for part in req_result.content:
                            text = getattr(part, "text", None)
                            if text:
                                req_text_parts.append(text)
                        req_text = "\n".join(req_text_parts) if req_text_parts else "{}"

                        try:
                            req_payload = json.loads(req_text)
                        except Exception:
                            req_payload = {"adr_id": rule_id, "count": 0, "evidence_refs": []}

                        normalized_rule = req_payload.get("adr_id", rule_id)
                        print(f"\n[tool] search_local_documents({{'query': '{normalized_rule}', 'max_files': 10, 'max_hits_per_file': 3}})")
                        doc_result = await session.call_tool(
                            "search_local_documents",
                            {"query": normalized_rule, "max_files": 10, "max_hits_per_file": 3},
                        )

                        doc_text_parts: list[str] = []
                        for part in doc_result.content:
                            text = getattr(part, "text", None)
                            if text:
                                doc_text_parts.append(text)
                        doc_text = "\n".join(doc_text_parts) if doc_text_parts else "{}"

                        try:
                            doc_payload = json.loads(doc_text)
                        except Exception:
                            doc_payload = {"matches": []}

                        content = _format_reference_listing(rule_id, req_payload, doc_payload)
                        print(f"\nAssistant: {content}")
                        messages.append({"role": "user", "content": user_input})
                        messages.append({"role": "assistant", "content": content})
                        continue

                design_guidance = _design_guidance_redirect(user_input)
                if design_guidance:
                    print(
                        f"\n[tool] search_local_documents({{'query': '{design_guidance['query']}', 'max_files': 5, 'max_hits_per_file': 3}})"
                    )
                    design_result = await session.call_tool(
                        "search_local_documents",
                        {"query": design_guidance["query"], "max_files": 5, "max_hits_per_file": 3},
                    )

                    design_text_parts: list[str] = []
                    for part in design_result.content:
                        text = getattr(part, "text", None)
                        if text:
                            design_text_parts.append(text)
                    design_text = "\n".join(design_text_parts) if design_text_parts else "{}"

                    messages.append({"role": "user", "content": user_input})
                    messages.append({"role": "tool", "name": "search_local_documents", "content": design_text})
                    tool_used_this_turn = True
                    evidence_refs_this_turn = _extract_evidence_refs(design_text)

                    for _ in range(6):
                        result = _post_chat(model=model, messages=messages, tools=tools)
                        assistant_message = result.get("message", {})
                        tool_calls = assistant_message.get("tool_calls", [])

                        if not tool_calls:
                            content = assistant_message.get("content", "")
                            if _strict_context_only() and not tool_used_this_turn:
                                content = "I do not have enough context in the indexed sources to answer that."
                            elif _strict_context_only() and _require_explicit_citations():
                                if not _has_explicit_citation(content):
                                    if evidence_refs_this_turn:
                                        refs_text = "; ".join(evidence_refs_this_turn[:3])
                                        content = f"{content.strip()}\n\nEvidence: {refs_text}"
                                    else:
                                        content = "I do not have enough context in the indexed sources to answer that."

                            if design_guidance["redirect"] not in content:
                                content = f"{content.strip()}\n\n{design_guidance['redirect']}"

                            print(f"\nAssistant: {content}")
                            messages.append({"role": "assistant", "content": content})
                            break

                        messages.append(
                            {
                                "role": "assistant",
                                "content": assistant_message.get("content", ""),
                                "tool_calls": tool_calls,
                            }
                        )

                        for call in tool_calls:
                            fn = call.get("function", {})
                            tool_name = fn.get("name")
                            args = fn.get("arguments", {})

                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except Exception:
                                    args = {}

                            print(f"\n[tool] {tool_name}({args})")
                            tool_result = await session.call_tool(tool_name, args)
                            tool_used_this_turn = True

                            tool_text_parts: list[str] = []
                            for part in tool_result.content:
                                text = getattr(part, "text", None)
                                if text:
                                    tool_text_parts.append(text)
                            tool_text = "\n".join(tool_text_parts) if tool_text_parts else str(tool_result)
                            refs = _extract_evidence_refs(tool_text)
                            if refs:
                                evidence_refs_this_turn.extend(refs)

                            messages.append(
                                {
                                    "role": "tool",
                                    "name": tool_name,
                                    "content": tool_text,
                                }
                            )
                    else:
                        print("\nAssistant: I hit the tool-call loop limit. Please rephrase and try again.")
                    continue

                messages.append({"role": "user", "content": user_input})
                tool_used_this_turn = False
                evidence_refs_this_turn: list[str] = []

                # RL-guided prefetch stage for standard questions.
                rl_state, rl_actions = _rl_state_and_actions(user_input)
                rl_action = rl_bridge.choose_action(rl_state, rl_actions)
                if rl_action:
                    print(f"\n[rl] state={rl_state} action={rl_action}")

                rule_id = _extract_rule_id_from_question(user_input)

                if rl_action in {"documents_first", "hybrid"}:
                    doc_query = rule_id or user_input
                    print(f"\n[tool] search_local_documents({{'query': '{doc_query}', 'max_files': 5, 'max_hits_per_file': 3}})")
                    doc_result = await session.call_tool(
                        "search_local_documents",
                        {"query": doc_query, "max_files": 5, "max_hits_per_file": 3},
                    )
                    doc_text_parts: list[str] = []
                    for part in doc_result.content:
                        text = getattr(part, "text", None)
                        if text:
                            doc_text_parts.append(text)
                    doc_text = "\n".join(doc_text_parts) if doc_text_parts else "{}"
                    refs = _extract_evidence_refs(doc_text)
                    if refs:
                        evidence_refs_this_turn.extend(refs)
                    messages.append({"role": "tool", "name": "search_local_documents", "content": doc_text})
                    tool_used_this_turn = True

                if rl_action in {"graph_first", "hybrid"} and rule_id:
                    print(f"\n[tool] get_adr_requirements({{'adr_id': '{rule_id}', 'limit': 400}})")
                    graph_result = await session.call_tool(
                        "get_adr_requirements",
                        {"adr_id": rule_id, "limit": 400},
                    )
                    graph_text_parts: list[str] = []
                    for part in graph_result.content:
                        text = getattr(part, "text", None)
                        if text:
                            graph_text_parts.append(text)
                    graph_text = "\n".join(graph_text_parts) if graph_text_parts else "{}"
                    refs = _extract_evidence_refs(graph_text)
                    if refs:
                        evidence_refs_this_turn.extend(refs)
                    messages.append({"role": "tool", "name": "get_adr_requirements", "content": graph_text})
                    tool_used_this_turn = True

                for _ in range(6):
                    result = _post_chat(model=model, messages=messages, tools=tools)
                    assistant_message = result.get("message", {})
                    tool_calls = assistant_message.get("tool_calls", [])

                    if not tool_calls:
                        content = assistant_message.get("content", "")
                        if _strict_context_only() and not tool_used_this_turn:
                            content = "I do not have enough context in the indexed sources to answer that."
                        elif _strict_context_only() and _require_explicit_citations():
                            if not _has_explicit_citation(content):
                                if evidence_refs_this_turn:
                                    refs_text = "; ".join(evidence_refs_this_turn[:3])
                                    content = f"{content.strip()}\n\nEvidence: {refs_text}"
                                else:
                                    content = "I do not have enough context in the indexed sources to answer that."
                        print(f"\nAssistant: {content}")
                        messages.append({"role": "assistant", "content": content})

                        # RL update from this completed turn.
                        reward = _rl_reward(content, tool_used_this_turn, evidence_refs_this_turn)
                        rl_bridge.update_and_save(
                            state=rl_state,
                            action=rl_action,
                            reward=reward,
                            next_state=rl_state,
                            next_actions=rl_actions,
                        )
                        break

                    messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_message.get("content", ""),
                            "tool_calls": tool_calls,
                        }
                    )

                    for call in tool_calls:
                        fn = call.get("function", {})
                        tool_name = fn.get("name")
                        args = fn.get("arguments", {})

                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}

                        print(f"\n[tool] {tool_name}({args})")
                        tool_result = await session.call_tool(tool_name, args)
                        tool_used_this_turn = True

                        tool_text_parts: list[str] = []
                        for part in tool_result.content:
                            text = getattr(part, "text", None)
                            if text:
                                tool_text_parts.append(text)
                        tool_text = "\n".join(tool_text_parts) if tool_text_parts else str(tool_result)
                        refs = _extract_evidence_refs(tool_text)
                        if refs:
                            evidence_refs_this_turn.extend(refs)

                        messages.append(
                            {
                                "role": "tool",
                                "name": tool_name,
                                "content": tool_text,
                            }
                        )
                else:
                    print("\nAssistant: I hit the tool-call loop limit. Please rephrase and try again.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terminal chat with Ollama + local MCP server")
    parser.add_argument("--model", default=None, help="Ollama model tag (default from OLLAMA_MODEL)")
    parser.add_argument(
        "--server-command",
        default="python3",
        help="Command used to launch the MCP server",
    )
    parser.add_argument(
        "--server-script",
        default="sr8-mcp",
        help="MCP server script path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = _ollama_model(args.model)
    asyncio.run(run_chat(model=model, server_command=args.server_command, server_args=[args.server_script]))


if __name__ == "__main__":
    main()
