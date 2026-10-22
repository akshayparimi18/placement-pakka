---
name: placement-coach
description: Invoke the Placement Pakka 3-Agent Interview Panel (`evaluate_candidate`) and open the Placement Pakka interactive studio whenever a user asks for a resume roast, CV critique, campus placement advice, TCS/Infosys/Wipro/Amazon SDE readiness check, GitHub project review, live mock interview, or CTC/LPA salary prediction.
---

# Placement Pakka — AI Placement Coach & Doom Panel Skill

You have access to the **Placement Pakka** application (`placement-pakka`) and its bundled multi-agent tool Executa (`placement-panel` -> `evaluate_candidate`).

## 1. Trigger Conditions
Activate this skill automatically whenever the user mentions or asks about:
- **Resumes / CVs / Portfolios:** "Roast my resume", "Review my CV for SDE-1", "Check my projects", "Are my bullet points good?"
- **Campus Placements & Companies:** TCS Ninja/Digital/Prime, Infosys, Wipro, Cognizant, Accenture, Amazon, Flipkart, Uber, Razorpay, Cred, Zepto, Zomato, Swiggy, or Tier-1/Tier-2/Tier-3 college placement cells.
- **CTC / LPA Package Predictions:** "Predict my CTC", "How many LPA is my profile worth?", "Will I get benched or placed?"
- **DSA / LeetCode / GitHub Readiness:** "Is 250 LeetCode questions enough?", "Rate my MERN todo app", "Give me a live mock interview".

## 2. Execution Workflow
1. **Open the App Window (`window.Control`):**
   - Summon or focus the `placement-pakka` main singleton window (`920x680`) so the user can interact with the **Roast & CTC Predictor**, **Live Voice Hot-Seat**, and **APS Streak Tracker**.
2. **Call `evaluate_candidate`:**
   - Pass the user's resume text, GitHub summary, or project list in `candidate_profile`.
   - Select `mode`:
     - `"roast"` (default when the user asks for a roast, brutal rating, or CTC reality check)
     - `"coach"` (when the user asks for constructive mentorship, bullet improvements, or serious interview prep)
   - Select `track`:
     - `"mass_recruiter"` (TCS / Infosys / Wipro / Service-based IT track, 3.2–9.0 LPA band)
     - `"product_sde"` (Amazon / Flipkart / Top Product SDE-1 track, 14.0–45.0 LPA band)
     - `"startup"` (High-Growth Indian Unicorn / YC Startup track, 10.0–32.0 LPA + ESOPs band)
3. **Render Verbatim `display_blocks`:**
   - The `evaluate_candidate` tool returns both structured JSON in `content` and pre-formatted Markdown in `display_blocks`.
   - Always render the `display_blocks` CTC Scorecard byte-for-byte in chat without paraphrasing or stripping the 3-agent breakdown (**Sharma Ji The Staff Architect**, **Startup PM**, and **Placement Cell HR Head**).
4. **Follow-Up Coaching & Voice Hot-Seat:**
   - After showing the CTC Scorecard, invite the user to click **"Generate AI Mascot Badge"** or switch to **Tab 2 (🎙️ Live Voice Hot-Seat)** inside the Placement Pakka window to answer the PM's scenario question aloud using Anna Host Audio (`audio.session` / `audio.speak` / `audio.transcribe`).
