#!/usr/bin/env python3
"""
Placement Pakka — 3-Agent LangGraph Executa Plugin (`panel_plugin.py`, Schema v2).

Implements JSON-RPC 2.0 over stdio (`initialize`, `describe`, `invoke`, `shutdown`)
with reverse-RPC `sampling/createMessage` and `storage/*` capabilities.

Nodes:
  1. `architect` — "Sharma Ji The Brutal Staff Architect" (roast) / "Senior SDE Mentor" (coach)
  2. `manager`   — "Unhinged Startup PM" (roast) / "Engineering Hiring Manager" (coach)
  3. `hr`        — "Placement Cell & HR Head" (calculates Hire Score, LPA Band, Badge Title, Top Fixes)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict

# Ensure UTF-8 encoding on Windows & POSIX stdio before anything else
if hasattr(sys.stdin, "reconfigure"):
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure local `executa_sdk` is importable regardless of current working directory
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from executa_sdk import ExecutaPluginServer  # noqa: E402

# Optional LangGraph import: uses LangGraph StateGraph when installed in .venv,
# with a lightweight deterministic 3-node StateGraph fallback if run in base Python.
try:
    from langgraph.graph import END, START, StateGraph  # type: ignore

    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False


class PanelState(TypedDict, total=False):
    candidate_profile: str
    mode: str
    track: str
    architect_persona: str
    architect_review: str
    manager_persona: str
    manager_review: str
    grill_question: str
    hire_score: int
    predicted_ctc_lpa: str
    badge_title: str
    hr_quote: str
    top_fixes: List[str]
    action_items: List[str]
    image_prompt: str
    scorecard_markdown: str


TRACK_METADATA: Dict[str, Dict[str, str]] = {
    "mass_recruiter": {
        "label": "TCS / Infosys / Wipro Mass Recruiter Track",
        "band": "3.2 LPA – 9.0 LPA (Ninja / Digital / Prime Tier)",
        "focus": "OOP basics, DBMS/SQL joins, SDLC, basic Java/Python, communication & bond readiness",
    },
    "product_sde": {
        "label": "Amazon / Flipkart / Top Product SDE-1 Track",
        "band": "14.0 LPA – 42.0 LPA (Product SDE-1 Tier)",
        "focus": "DSA problem solving, low-level design, distributed systems scale, measurable production metrics",
    },
    "startup": {
        "label": "High-Growth Indian Unicorn / YC Startup Track",
        "band": "10.0 LPA – 32.0 LPA + High-Conviction ESOPs",
        "focus": "0-to-1 shipping velocity, live deployed links, full-stack ownership, real users & GitHub commits",
    },
}


HR_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "placement_hr_verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "hire_score": {"type": "integer", "minimum": 1, "maximum": 100},
                "predicted_ctc_lpa": {"type": "string"},
                "badge_title": {"type": "string"},
                "hr_quote": {"type": "string"},
                "top_fixes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "image_prompt": {"type": "string"},
            },
            "required": [
                "hire_score",
                "predicted_ctc_lpa",
                "badge_title",
                "hr_quote",
                "top_fixes",
                "image_prompt",
            ],
            "additionalProperties": False,
        },
    },
}


def _heuristic_architect_fallback(profile: str, mode: str, track: str) -> str:
    """Fallback Architect evaluation if Host LLM sampling is offline."""
    p_lower = profile.lower()
    has_metrics = bool(re.search(r"\d+%|\d+\s*(ms|users|req|rps|k\b)", p_lower))
    has_todo = any(w in p_lower for w in ("todo", "calculator", "weather app", "netflix clone", "tic tac toe"))
    if mode == "roast":
        if has_todo and not has_metrics:
            return (
                "Beta, Sharma Ji’s blood pressure just spiked to 180/120 looking at this stack. "
                "You wrote 'Full-Stack Architect' on top of a tutorial clone with zero database indexing, "
                "zero caching, and hard-coded API routes. Even localhost is ashamed to serve this on port 3000."
            )
        return (
            "Sharma Ji adjusted his spectacles twice. Your tech stack actually mentions real backend components, "
            "but where are the p99 latency benchmarks, failure recovery strategies, and load test numbers? "
            "Right now your architecture diagrams exist only in your hostel daydream."
        )
    else:
        return (
            f"For the {TRACK_METADATA[track]['label']}, your core stack selection shows solid foundational intent. "
            "To stand out in technical rounds, replace generic feature descriptions with specific engineering "
            "trade-offs: explain your database schema indexing, API rate-limiting, and how you tested edge cases."
        )


def _heuristic_manager_fallback(profile: str, mode: str, track: str) -> Dict[str, str]:
    """Fallback PM evaluation + 1 sharp scenario question if Host LLM sampling is offline."""
    p_lower = profile.lower()
    if mode == "roast":
        critique = (
            "You used 'passionate', 'scalable', and 'AI-powered' four times without citing a single real user! "
            "Did anyone outside your 3 hostel roommates ever click login on your app, or did you just wrap an "
            "OpenAI API key in a React form and call it a SaaS startup?"
        )
    else:
        critique = (
            "Your project bullets focus heavily on which libraries you imported rather than the user problem "
            "solved. Hiring managers look for measurable impact: adoption numbers, latency reduction, or workflow time saved."
        )

    if "redis" in p_lower or "kafka" in p_lower or "microservice" in p_lower:
        question = (
            "If your primary cache cluster goes down during a Flipkart Big Billion Days flash sale at 12:00 AM, "
            "how does your backend prevent a thundering herd from melting your primary PostgreSQL instance?"
        )
    elif track == "mass_recruiter":
        question = (
            "Walk me through the exact difference between an INNER JOIN and a LEFT OUTER JOIN on a 5-million-row "
            "employee table, and explain how you would debug a slow query without rewriting the application code."
        )
    else:
        question = (
            "If 10,000 concurrent college students hit your main project endpoint at 9:00 AM during exam results, "
            "which exact line of your backend breaks first and how would you fix it in under 30 minutes?"
        )
    return {"critique": critique, "question": question}


def _heuristic_hr_fallback(profile: str, mode: str, track: str) -> Dict[str, Any]:
    """Fallback structured HR verdict if Host LLM sampling is offline."""
    p_lower = profile.lower()
    score = 52
    if any(k in p_lower for k in ("leetcode", "codeforces", "250+", "300+", "500+", "knight", "guardian")):
        score += 18
    if any(k in p_lower for k in ("docker", "kubernetes", "redis", "kafka", "aws", "postgres", "fastapi", "go")):
        score += 14
    if re.search(r"\d+%|\d+x|\d+\s*(ms|users|rps)", p_lower):
        score += 10
    if any(k in p_lower for k in ("todo", "weather app", "calculator", "clone")) and score < 70:
        score -= 16
    score = max(18, min(96, score))

    if track == "mass_recruiter":
        if score >= 75:
            ctc = "9.0 LPA (TCS Prime / Infosys Specialist Programmer Tier)"
            badge = "Mass Recruiter Final Boss"
        elif score >= 50:
            ctc = "7.0 LPA (TCS Digital / Wipro Turbo Tier)"
            badge = "Aptitude & SQL Survivor"
        else:
            ctc = "3.6 LPA (Ninja Bench & Chai Allowance Tier)"
            badge = "Certified Todo-App Copy-Paster"
    elif track == "product_sde":
        if score >= 80:
            ctc = "28.5 LPA ( Tier-1 Product SDE-1 Offer)"
            badge = "10x Hostel LeetCode Grandma"
        elif score >= 60:
            ctc = "16.5 LPA (Mid-Tier Product SDE-1)"
            badge = "Sliding Window Warrior"
        else:
            ctc = "4.2 LPA (DSA Reality Check Pending)"
            badge = "O(N^3) Time Complexity Enthusiast"
    else:
        if score >= 78:
            ctc = "22.0 LPA + 0.15% ESOPs (Founding Engineer Material)"
            badge = "Cracked 3 AM Prod Deployer"
        elif score >= 55:
            ctc = "12.5 LPA (Seed Startup Full-Stack Builder)"
            badge = "Weekend Hackathon Grinder"
        else:
            ctc = "4.5 LPA (Localhost-Only Entrepreneur)"
            badge = "Tutorial Hell Permanent Resident"

    if mode == "roast":
        quote = (
            f"With a Hire Score of {score}/100, our Placement Cell recommends keeping your ID card lanyard ironed "
            "and replacing tutorial clones with at least one deployed production URL before Day-1 slots open."
        )
    else:
        quote = (
            f"You scored {score}/100 on the {TRACK_METADATA[track]['label']}; tightening your impact metrics and "
            "system design depth can push your profile into the top tier of campus shortlists."
        )

    fixes = [
        "Rewrite top project bullets using the XYZ formula: 'Accomplished [X] as measured by [Y], by implementing [Z]' with concrete latency/user metrics.",
        "Add live deployed links, architectural README diagrams, and automated tests to your top 2 GitHub repositories instead of listing 6 unfinished clones.",
        "Highlight verifiable problem-solving proof (LeetCode/Codeforces contest rating, open-source PRs, or production internship deliverables).",
    ]
    image_prompt = (
        f"Vibrant 3D vector sticker badge for '{badge}', playful Indian campus placement tech mascot owl "
        "holding a laptop and golden LPA trophy, neon cyberpunk dark background, clean composition, text-free"
    )
    return {
        "hire_score": score,
        "predicted_ctc_lpa": ctc,
        "badge_title": badge,
        "hr_quote": quote,
        "top_fixes": fixes,
        "action_items": fixes,
        "image_prompt": image_prompt,
    }


def _extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    """Safely extract a JSON object from raw LLM text or fenced code blocks."""
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)
    else:
        brace_match = re.search(r"(\{.*\})", cleaned, flags=re.DOTALL)
        if brace_match:
            cleaned = brace_match.group(1)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _format_scorecard_markdown(state: PanelState) -> str:
    """Build the verbatim Markdown CTC Scorecard returned in `display_blocks`."""
    mode = state.get("mode", "roast")
    track = state.get("track", "product_sde")
    track_info = TRACK_METADATA.get(track, TRACK_METADATA["product_sde"])
    mode_badge = "🔥 SAVAGE ROAST MODE" if mode == "roast" else "🎯 PLACEMENT COACH MODE"
    fixes = state.get("top_fixes") or state.get("action_items") or []
    fixes_md = "\n".join(f"{idx}. {fix}" for idx, fix in enumerate(fixes, 1))

    return (
        f"## 🎓 Placement Pakka — Official CTC Scorecard ({mode_badge})\n\n"
        f"**Target Track:** {track_info['label']}  \n"
        f"**Predicted Package:** **`{state.get('predicted_ctc_lpa', 'N/A')}`**  \n"
        f"**Hireability Score:** **`{state.get('hire_score', 50)} / 100`**  \n"
        f"**Unlocked Title:** 🏅 **{state.get('badge_title', 'Campus Contender')}**\n\n"
        f"> 💬 **HR Head Verdict:** *\"{state.get('hr_quote', '')}\"*\n\n"
        f"### 1️⃣ {state.get('architect_persona', 'Staff Architect')}\n"
        f"{state.get('architect_review', '')}\n\n"
        f"### 2️⃣ {state.get('manager_persona', 'Hiring Manager')}\n"
        f"{state.get('manager_review', '')}\n\n"
        f"**🎙️ Live Hot-Seat Grill Question:**\n"
        f"> *{state.get('grill_question', '')}*\n\n"
        f"### 🛠️ Top 3 Resume Fixes to Boost Your CTC\n"
        f"{fixes_md}\n"
    )


def build_and_run_panel_workflow(
    candidate_profile: str,
    mode: str,
    track: str,
    server: ExecutaPluginServer,
) -> PanelState:
    """
    Execute the 3-node multi-agent workflow (`architect` -> `manager` -> `hr`)
    using LangGraph StateGraph (when installed) and reverse-RPC `sampling/createMessage`.
    """
    norm_mode = "coach" if str(mode).lower().strip() == "coach" else "roast"
    norm_track = str(track).lower().strip()
    if norm_track not in TRACK_METADATA:
        norm_track = "product_sde"
    track_meta = TRACK_METADATA[norm_track]

    def architect_node(state: PanelState) -> Dict[str, Any]:
        persona = (
            "Sharma Ji The Brutal Staff Architect"
            if state["mode"] == "roast"
            else "Senior SDE Technical Mentor"
        )
        sys_prompt = (
            f"You are {persona} evaluating an Indian engineering student/fresher for the "
            f"{track_meta['label']} ({track_meta['band']}). Focus areas: {track_meta['focus']}. "
            + (
                "Be hilariously sharp, Desi-tech authentic, and ruthlessly call out tutorial clones, "
                "missing system design depth, or unverified buzzwords in 3-4 punchy sentences."
                if state["mode"] == "roast"
                else "Be warm, constructive, and technically rigorous. Evaluate their stack and architecture "
                "depth in 3-4 clear, actionable sentences."
            )
        )
        user_msg = f"Candidate Resume / GitHub / Projects:\n{state['candidate_profile']}"
        review = server.create_message(
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=sys_prompt,
            max_tokens=350,
            temperature=0.75 if state["mode"] == "roast" else 0.4,
            fallback_fn=lambda _: _heuristic_architect_fallback(
                state["candidate_profile"], state["mode"], state["track"]
            ),
        )
        return {
            "architect_persona": persona,
            "architect_review": review.strip(),
        }

    def manager_node(state: PanelState) -> Dict[str, Any]:
        persona = (
            "Unhinged Bengaluru Startup PM"
            if state["mode"] == "roast"
            else "Engineering Hiring Manager"
        )
        sys_prompt = (
            f"You are {persona} reviewing a candidate for {track_meta['label']}. "
            "First, write a 2-3 sentence critique of their real-world product impact and expose any hollow buzzwords. "
            "Second, on a new line prefixed with 'GRILL_QUESTION:', ask 1 specific, high-pressure scenario question "
            "based on their exact projects."
        )
        user_msg = (
            f"Candidate Profile:\n{state['candidate_profile']}\n\n"
            f"Architect's Technical Notes:\n{state.get('architect_review', '')}"
        )

        def _mgr_fallback(_: Dict[str, Any]) -> str:
            fb = _heuristic_manager_fallback(
                state["candidate_profile"], state["mode"], state["track"]
            )
            return f"{fb['critique']}\nGRILL_QUESTION: {fb['question']}"

        raw_mgr = server.create_message(
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=sys_prompt,
            max_tokens=380,
            temperature=0.75 if state["mode"] == "roast" else 0.45,
            fallback_fn=_mgr_fallback,
        )

        if "GRILL_QUESTION:" in raw_mgr:
            parts = raw_mgr.split("GRILL_QUESTION:", 1)
            critique_text = parts[0].strip()
            question_text = parts[1].strip()
        else:
            fb = _heuristic_manager_fallback(
                state["candidate_profile"], state["mode"], state["track"]
            )
            critique_text = raw_mgr.strip() or fb["critique"]
            question_text = fb["question"]

        return {
            "manager_persona": persona,
            "manager_review": critique_text,
            "grill_question": question_text,
        }

    def hr_node(state: PanelState) -> Dict[str, Any]:
        sys_prompt = (
            "You are the Placement Cell & HR Head calculating the final Indian placement CTC package (in LPA). "
            "Respond strictly with a single valid JSON object matching the required schema with keys: "
            "hire_score (int 1-100), predicted_ctc_lpa (string), badge_title (string), hr_quote (string), "
            "top_fixes (array of 3 strings), and image_prompt (string)."
        )
        user_msg = (
            f"Track: {track_meta['label']} ({track_meta['band']})\n"
            f"Mode: {state['mode']}\n"
            f"Candidate Profile:\n{state['candidate_profile']}\n\n"
            f"Architect Review:\n{state.get('architect_review', '')}\n\n"
            f"Manager Review:\n{state.get('manager_review', '')}"
        )

        fallback_dict = _heuristic_hr_fallback(
            state["candidate_profile"], state["mode"], state["track"]
        )
        raw_hr = server.create_message(
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=sys_prompt,
            max_tokens=500,
            temperature=0.5,
            response_format=HR_RESPONSE_SCHEMA,
            fallback_fn=lambda _: json.dumps(fallback_dict, ensure_ascii=False),
        )

        parsed = _extract_json_object(raw_hr) or fallback_dict
        hire_score = int(parsed.get("hire_score", fallback_dict["hire_score"]))
        hire_score = max(1, min(100, hire_score))
        predicted_ctc_lpa = str(parsed.get("predicted_ctc_lpa") or fallback_dict["predicted_ctc_lpa"])
        badge_title = str(parsed.get("badge_title") or fallback_dict["badge_title"])
        hr_quote = str(parsed.get("hr_quote") or fallback_dict["hr_quote"])

        raw_fixes = parsed.get("top_fixes") or parsed.get("action_items") or fallback_dict["top_fixes"]
        if not isinstance(raw_fixes, list) or len(raw_fixes) < 3:
            top_fixes = list(fallback_dict["top_fixes"])
        else:
            top_fixes = [str(item) for item in raw_fixes[:3]]

        image_prompt = str(parsed.get("image_prompt") or fallback_dict["image_prompt"])

        partial_state: PanelState = {
            **state,
            "hire_score": hire_score,
            "predicted_ctc_lpa": predicted_ctc_lpa,
            "badge_title": badge_title,
            "hr_quote": hr_quote,
            "top_fixes": top_fixes,
            "action_items": top_fixes,
            "image_prompt": image_prompt,
        }
        scorecard_md = _format_scorecard_markdown(partial_state)
        return {
            "hire_score": hire_score,
            "predicted_ctc_lpa": predicted_ctc_lpa,
            "badge_title": badge_title,
            "hr_quote": hr_quote,
            "top_fixes": top_fixes,
            "action_items": top_fixes,
            "image_prompt": image_prompt,
            "scorecard_markdown": scorecard_md,
        }

    initial_state: PanelState = {
        "candidate_profile": candidate_profile.strip(),
        "mode": norm_mode,
        "track": norm_track,
    }

    if HAS_LANGGRAPH:
        workflow = StateGraph(PanelState)
        workflow.add_node("architect", architect_node)
        workflow.add_node("manager", manager_node)
        workflow.add_node("hr", hr_node)
        workflow.add_edge(START, "architect")
        workflow.add_edge("architect", "manager")
        workflow.add_edge("manager", "hr")
        workflow.add_edge("hr", END)
        app = workflow.compile()
        final_state: PanelState = app.invoke(initial_state)  # type: ignore[assignment]
        return final_state
    else:
        # Lightweight sequential state orchestration fallback
        state = dict(initial_state)
        state.update(architect_node(state))  # type: ignore[arg-type]
        state.update(manager_node(state))  # type: ignore[arg-type]
        state.update(hr_node(state))  # type: ignore[arg-type]
        return state  # type: ignore[return-value]


# Initialize the Anna v2 Executa Plugin Server
server = ExecutaPluginServer(
    name="placement-panel",
    version="2.0.0",
    description="Placement Pakka 3-Agent LangGraph Campus Placement Panel & Live Voice Hot-Seat Evaluator",
    capabilities={
        "sampling": True,
        "storage": True,
    },
)


@server.tool(
    name="evaluate_candidate",
    description=(
        "Evaluates an engineering candidate's resume, GitHub profile, or project description using a "
        "3-agent LangGraph interview panel (Staff Architect, Startup PM, Placement Cell HR Head) via "
        "reverse-RPC sampling/createMessage. Returns both structured JSON (`hire_score`, `predicted_ctc_lpa`, "
        "`badge_title`, `hr_quote`, `top_fixes`, `image_prompt`) and a verbatim Markdown CTC Scorecard in `display_blocks`."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "candidate_profile": {
                "type": "string",
                "description": "Resume text, GitHub summary, project bullet points, or LeetCode stats.",
            },
            "mode": {
                "type": "string",
                "enum": ["roast", "coach"],
                "default": "roast",
                "description": "'roast' for Doom Panel Savage Roast mode, or 'coach' for constructive SDE Mentor mode.",
            },
            "track": {
                "type": "string",
                "enum": ["mass_recruiter", "product_sde", "startup"],
                "default": "product_sde",
                "description": "Target placement track: 'mass_recruiter' (TCS/Infosys), 'product_sde' (Amazon/Flipkart), or 'startup'.",
            },
        },
        "required": ["candidate_profile"],
    },
)
def evaluate_candidate_handler(args: Dict[str, Any], srv: ExecutaPluginServer) -> Dict[str, Any]:
    candidate_profile = str(
        args.get("candidate_profile")
        or args.get("resume")
        or args.get("profile")
        or "Final year CSE student with a MERN stack Todo app and 50 LeetCode easy problems."
    )
    mode = str(args.get("mode", "roast"))
    track = str(args.get("track", "product_sde"))

    final_state = build_and_run_panel_workflow(
        candidate_profile=candidate_profile,
        mode=mode,
        track=track,
        server=srv,
    )

    structured_payload: Dict[str, Any] = {
        "mode": final_state["mode"],
        "track": final_state["track"],
        "track_label": TRACK_METADATA[final_state["track"]]["label"],
        "architect": {
            "persona": final_state["architect_persona"],
            "review": final_state["architect_review"],
        },
        "manager": {
            "persona": final_state["manager_persona"],
            "review": final_state["manager_review"],
            "grill_question": final_state["grill_question"],
        },
        "hr": {
            "persona": "Placement Cell & HR Head",
            "hire_score": final_state["hire_score"],
            "predicted_ctc_lpa": final_state["predicted_ctc_lpa"],
            "badge_title": final_state["badge_title"],
            "hr_quote": final_state["hr_quote"],
            "top_fixes": final_state["top_fixes"],
            "action_items": final_state["action_items"],
            "image_prompt": final_state["image_prompt"],
        },
        # Top-level flat keys as required by Schema v2 callers & UI
        "hire_score": final_state["hire_score"],
        "predicted_ctc_lpa": final_state["predicted_ctc_lpa"],
        "badge_title": final_state["badge_title"],
        "hr_quote": final_state["hr_quote"],
        "top_fixes": final_state["top_fixes"],
        "action_items": final_state["action_items"],
        "image_prompt": final_state["image_prompt"],
        "grill_question": final_state["grill_question"],
        "orchestrator": "langgraph" if HAS_LANGGRAPH else "sequential-state-graph",
    }

    markdown_card = final_state["scorecard_markdown"]

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(structured_payload, ensure_ascii=False),
            }
        ],
        "structuredContent": structured_payload,
        "display_blocks": [
            {
                "type": "markdown",
                "markdown": markdown_card,
                "text": markdown_card,
                "verbatim": True,
            }
        ],
        "isError": False,
    }


@server.tool(
    name="voice_hotseat_turn",
    description=(
        "Evaluates a spoken candidate response from the Live Voice Hot-Seat room and generates "
        "a fluency/confidence score plus the next follow-up question."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "round_type": {
                "type": "string",
                "enum": ["hr_behavioral", "react_node", "python_dsa"],
                "default": "react_node",
            },
            "question_asked": {"type": "string"},
            "spoken_answer": {"type": "string"},
        },
        "required": ["spoken_answer"],
    },
)
def voice_hotseat_turn_handler(args: Dict[str, Any], srv: ExecutaPluginServer) -> Dict[str, Any]:
    round_type = str(args.get("round_type", "react_node"))
    question_asked = str(args.get("question_asked", "Tell me about the hardest bug you fixed."))
    spoken_answer = str(args.get("spoken_answer", ""))

    prompt = (
        f"Interview Round: {round_type}\n"
        f"Question Asked: {question_asked}\n"
        f"Candidate Spoken Transcript: {spoken_answer}\n\n"
        "Return JSON with keys: fluency_score (1-100), confidence_score (1-100), technical_score (1-100), "
        "spoken_feedback (2 sentences to speak aloud via TTS), next_question (1 sharp follow-up question)."
    )

    def _voice_fallback(_: Dict[str, Any]) -> str:
        word_count = len(spoken_answer.split())
        fluency = min(94, max(45, 55 + word_count))
        confidence = min(92, max(50, 60 + (word_count // 2)))
        tech = min(95, max(48, 52 + word_count))
        return json.dumps(
            {
                "fluency_score": fluency,
                "confidence_score": confidence,
                "technical_score": tech,
                "spoken_feedback": (
                    "Clear structure on the approach, though adding concrete latency or memory trade-offs "
                    "would make your answer much stronger for a panel round."
                ),
                "next_question": (
                    "What happens if the input payload grows 100x larger and memory is capped at 512MB?"
                ),
            }
        )

    raw = srv.create_message(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="You are a live voice mock interviewer for Indian campus placements. Output strictly JSON.",
        max_tokens=300,
        temperature=0.5,
        fallback_fn=_voice_fallback,
    )
    parsed = _extract_json_object(raw) or json.loads(_voice_fallback({}))
    md = (
        f"**🎙️ Voice Hot-Seat Rating:** Fluency `{parsed.get('fluency_score', 78)}/100` | "
        f"Confidence `{parsed.get('confidence_score', 80)}/100` | "
        f"Technical `{parsed.get('technical_score', 75)}/100`\n\n"
        f"**Interviewer Feedback:** {parsed.get('spoken_feedback', '')}\n\n"
        f"**Next Grill Question:** *{parsed.get('next_question', '')}*"
    )
    return {
        "content": [{"type": "text", "text": json.dumps(parsed, ensure_ascii=False)}],
        "structuredContent": parsed,
        "display_blocks": [{"type": "markdown", "markdown": md, "text": md, "verbatim": True}],
        "isError": False,
    }


def main() -> None:
    if "--describe" in sys.argv:
        resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "describe", "params": {}})
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return
    server.serve_stdio()


if __name__ == "__main__":
    main()
