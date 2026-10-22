# 🎓 Placement Pakka (`placement-pakka`) — Full-Stack Anna App (Schema v2)

**Placement Pakka** is a full-stack Anna App (Schema v2) built for the Indian engineering and college placement ecosystem. It combines viral acquisition (**"Doom Panel Roast Mode"**) with high-retention practice workflows (**"Placement Coach & Live Voice Hot-Seat"**) backed by Anna Persistent Storage (APS).

## ✨ Key Features

1. **🔥 3-Agent LangGraph Interview Panel (`executas/placement-panel/panel_plugin.py`):**
   - Powered 100% by Anna Host reverse-RPC `sampling/createMessage` (zero external LLM API keys required).
   - **Node 1 (`architect`):** *"Sharma Ji The Brutal Staff Architect"* (`roast` mode) or *"Senior SDE Technical Mentor"* (`coach` mode).
   - **Node 2 (`manager`):** *"Unhinged Bengaluru Startup PM"* (`roast` mode) or *"Engineering Hiring Manager"* (`coach` mode) + 1 sharp scenario grill question.
   - **Node 3 (`hr`):** *"Placement Cell & HR Head"* — outputs structured JSON (`hire_score`, `predicted_ctc_lpa`, `badge_title`, `hr_quote`, `top_fixes`, `image_prompt`) and verbatim Markdown in `display_blocks`.
2. **🎙️ Live Voice Hot-Seat (`ui/` Tab 2):**
   - Spoken interview simulator using `audio.session`, `audio.speak`, and `audio.transcribe` across `React/Node`, `Python/DSA`, and `HR Behavioral` rounds.
3. **🏆 Daily Streak & CTC History (`ui/` Tab 3 — Anna Persistent Storage):**
   - Uses `storage.get` and `storage.set` to persist daily practice streaks, highest predicted CTC (LPA), and past evaluation history.

## 🚀 Quickstart on Windows (`D:\placement-pakka`)

```powershell
# 1. Create and activate local Python virtual environment
python -m venv .venv
.\.venv\Scripts\pip install -e ./executas/placement-panel langgraph langchain-core pydantic pytest

# 2. Run the automated JSON-RPC 2.0 & reverse-RPC sampling smoke test suite
.\.venv\Scripts\python test_plugin.py

# 3. Validate and launch inside Anna App Dev Harness
anna-app validate
anna-app dev
```
