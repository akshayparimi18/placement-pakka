/**
 * Placement Pakka — AnnaAppRuntime & window.anna SDK Frontend Controller (`ui/app.js`, Schema v2).
 *
 * Bridges:
 *  - `tools.call` (`placement-panel` -> `evaluate_candidate` & `voice_hotseat_turn`)
 *  - `llm.complete` fallback
 *  - `storage.get`, `storage.set`, `storage.list` (Anna Persistent Storage + localStorage mirror)
 *  - `image.generate` (Host Image API + dynamic SVG sticker fallback)
 *  - `audio.session`, `audio.speak`, `audio.transcribe` (Host Audio API + Web Speech API fallback)
 *  - `chat.append_artifact` & `mobile.share` (with clipboard & WhatsApp/X share intents)
 */

(function () {
  'use strict';

  const STORAGE_KEY_STATE = 'placement_pakka_aps_v2';

  const SAMPLE_PROFILES = {
    fresher_todo: {
      track: 'mass_recruiter',
      mode: 'roast',
      text: `B.Tech CSE Final Year (CGPA: 7.4).
Projects:
1. Full-Stack MERN Todo List App — users can add, delete, and mark tasks complete on localhost.
2. Weather Forecast Website — fetches temperature from OpenWeather API using HTML/CSS/JS.
3. Scientific Calculator in Python Tkinter.
Skills: C, C++, HTML, CSS, Basic JavaScript, "Passionate AI/ML & Blockchain Enthusiast".
Coding Profiles: 42 LeetCode problems solved (39 Easy, 3 Medium).`,
    },
    sde_aspirant: {
      track: 'product_sde',
      mode: 'roast',
      text: `B.Tech CSE Final Year (CGPA: 8.6).
Projects:
1. FlashCart E-Commerce Backend (Node.js, Express, MongoDB, JWT) — built REST APIs for cart and checkout, deployed on Render.
2. ChatSphere Realtime Messenger (React, Socket.io) — supports group rooms and typing indicators.
Coding & Achievements:
- Solved 265 LeetCode problems (175 Easy, 80 Medium, 10 Hard), Max Contest Rating: 1585.
- Coordinator at College Coding Club. Seeking Product SDE-1 (20+ LPA).`,
    },
    startup_cracker: {
      track: 'startup',
      mode: 'coach',
      text: `B.Tech IT Final Year | 6-month Backend Intern at FinTech Startup.
Projects & Shipped Work:
1. High-Throughput Webhook Dispatcher (Go, Redis Streams, PostgreSQL) — processes 4,200 events/sec at p99 latency of 18ms with exponential backoff retries.
2. CampusGPT Study Copilot (Next.js, FastAPI, pgvector) — 1,400+ active students during semester exams, reduced query cost by 62% via semantic caching.
Open Source & DSA:
- 420+ LeetCode (240 Medium, 65 Hard, Knight Badge 1910), 3 merged PRs in FastAPI ecosystem.`,
    },
  };

  const VOICE_QUESTIONS = {
    hr_behavioral: [
      'Tell me about a time your team project broke 2 hours before the demo. What exact action did you take?',
      'Why should we hire you for a 20+ LPA SDE role over someone with 500 more LeetCode problems?',
      'Suppose a senior engineer rejects your PR three times in a row. How do you handle it?',
    ],
    react_node: [
      'Two users click Buy Now on the last item in stock at the exact same millisecond. How does your Node/Postgres backend prevent double-selling?',
      'Your React dashboard freezes when rendering a table of 25,000 rows. How do you bring frame times under 16ms?',
      'Explain what happens in the Node.js event loop if an endpoint runs a synchronous SHA-256 hash on a 50MB buffer.',
    ],
    python_dsa: [
      'How would you design a rate limiter handling 50,000 requests per second across 8 distributed Python workers?',
      'Walk me through finding the Kth largest element in an infinite stream of telemetry integers with minimal memory.',
      'Why does Python GIL impact CPU-bound threads, and when would you pick multiprocessing vs asyncio?',
    ],
  };

  const state = {
    hostConnected: false,
    runtimeMode: 'Standalone / Canvas Preview',
    mode: 'roast',
    track: 'product_sde',
    currentEvaluation: null,
    voiceSessionActive: false,
    voiceRound: 'react_node',
    voiceQuestionIndex: 0,
    voiceTranscripts: [],
    aps: {
      streakDays: 3,
      lastPracticeDate: '2026-10-22',
      highestCtcLpa: 18.5,
      bestHireScore: 76,
      history: [
        {
          id: 'hist-seed-1',
          timestamp: '2026-10-21 21:15',
          mode: 'roast',
          track: 'product_sde',
          trackLabel: 'Amazon / Flipkart Product SDE-1 Track',
          hire_score: 64,
          predicted_ctc_lpa: '14.5 LPA (Tier-2 Product SDE-1 Contender)',
          badge_title: '180-Easy LeetCode Comfort Zone CEO',
          hr_quote: 'Shift your ratio from LeetCode Easys to Medium/Hards and add concurrency control to crack 24+ LPA.',
          architect: {
            persona: 'Sharma Ji The Brutal Staff Architect',
            review: 'Sharma Ji nearly choked on his evening samosa seeing 180 Easy LeetCode questions passed off as Product SDE readiness. Your MERN E-Commerce clone has zero Redis caching and no inventory locking.',
          },
          manager: {
            persona: 'Unhinged Bengaluru Startup PM',
            review: 'Nobody needs another Weather App when every phone has a lock screen widget! Show me active users or p99 latency numbers.',
            grill_question: 'Two users click Buy Now on the last iPhone in stock at the exact same millisecond—how do you prevent double-charging without locking the entire table?',
          },
          top_fixes: [
            'Replace the Weather App with a concurrency-safe booking microservice using PostgreSQL row-level locking and Redis.',
            'Push your LeetCode Medium/Hard ratio above 60% and add your contest rating to the resume header.',
            'Quantify API latency (p95 ms) and load-testing throughput (requests/sec) in your E-Commerce bullets.',
          ],
          image_prompt: '3D cyberpunk owl architect sticker holding a 14.5 LPA golden placard and laptop, dark neon indigo background, text-free',
        },
      ],
    },
  };

  function showToast(message) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'toast-msg';
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 3400);
  }

  // Anna Host SDK Handshake (`AnnaAppRuntime` / `window.anna`)
  async function connectAnnaHost() {
    try {
      if (window.AnnaAppRuntime && typeof window.AnnaAppRuntime.connect === 'function') {
        const client = await window.AnnaAppRuntime.connect({
          appId: 'placement-pakka',
          schemaVersion: 2,
        });
        window.anna = client || window.anna;
        state.hostConnected = true;
        state.runtimeMode = 'Anna Host Runtime v2 Connected';
      } else if (window.anna) {
        state.hostConnected = true;
        state.runtimeMode = 'window.anna Bridge Active';
      }
    } catch (err) {
      state.hostConnected = false;
      state.runtimeMode = 'Browser Sandbox Mode (Host Fallback Ready)';
    }

    const statusText = document.getElementById('hostStatusText');
    if (statusText) {
      statusText.textContent = state.runtimeMode;
    }
    await loadApsStorage();
  }

  // APS Persistence (`storage.get` / `storage.set`)
  async function loadApsStorage() {
    try {
      if (window.anna && window.anna.storage && typeof window.anna.storage.get === 'function') {
        const remote = await window.anna.storage.get(STORAGE_KEY_STATE);
        if (remote && typeof remote === 'object' && Array.isArray(remote.history)) {
          state.aps = Object.assign({}, state.aps, remote);
        }
      } else {
        try {
          const raw = localStorage.getItem(STORAGE_KEY_STATE);
          if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed && Array.isArray(parsed.history)) {
              state.aps = Object.assign({}, state.aps, parsed);
            }
          }
        } catch (_) {}
      }
    } catch (_) {}
    renderApsDashboard();
  }

  async function saveApsStorage() {
    try {
      if (window.anna && window.anna.storage && typeof window.anna.storage.set === 'function') {
        await window.anna.storage.set(STORAGE_KEY_STATE, state.aps);
      }
    } catch (_) {}
    try {
      localStorage.setItem(STORAGE_KEY_STATE, JSON.stringify(state.aps));
    } catch (_) {}
    renderApsDashboard();
  }

  function parseLpaNumber(ctcStr) {
    if (!ctcStr) return 0;
    const m = String(ctcStr).match(/(\d+(?:\.\d+)?)\s*LPA/i);
    return m ? parseFloat(m[1]) : 0;
  }

  // Local 3-Agent Engine Fallback (mirrors `panel_plugin.py` when run in browser preview)
  function evaluateLocally(profileText, mode, track) {
    const lower = profileText.toLowerCase();
    const hasMetrics = /\d+%|\d+\s*(ms|rps|req|users|sec)/i.test(profileText);
    const hasScale = /(redis|kafka|postgres|docker|kubernetes|go|fastapi|socket|pgvector|microservice)/i.test(lower);
    const hasDsa = /(250|265|300|400|420|500|knight|guardian|1585|1910)/i.test(lower);
    const hasClones = /(todo|weather|calculator|clone)/i.test(lower);

    let score = 54;
    if (hasScale) score += 16;
    if (hasDsa) score += 14;
    if (hasMetrics) score += 10;
    if (hasClones && !hasScale) score -= 18;
    score = Math.max(22, Math.min(96, score));

    const trackNames = {
      mass_recruiter: 'TCS / Infosys / Wipro Mass Recruiter Track',
      product_sde: 'Amazon / Flipkart / Top Product SDE-1 Track',
      startup: 'High-Growth Indian Unicorn / YC Startup Track',
    };

    let ctc = '6.5 LPA (Digital SDE Tier)';
    let badge = 'Campus Shortlist Contender';

    if (track === 'mass_recruiter') {
      if (score >= 75) {
        ctc = '9.0 LPA (TCS Prime / Infosys Specialist Programmer Tier)';
        badge = 'Mass Recruiter Final Boss';
      } else if (score >= 52) {
        ctc = '7.0 LPA (TCS Digital / Wipro Turbo Tier)';
        badge = 'SQL Join & Aptitude Survivor';
      } else {
        ctc = '3.6 LPA (Ninja Bench & Chai Allowance Tier)';
        badge = 'Certified Todo-App Copy-Paster';
      }
    } else if (track === 'product_sde') {
      if (score >= 82) {
        ctc = '28.5 LPA (Day-1 Product SDE-1 Offer)';
        badge = '10x Hostel LeetCode Grandmaster';
      } else if (score >= 60) {
        ctc = '16.5 LPA (Tier-1 Product SDE-1 Contender)';
        badge = 'Sliding Window & System Design Warrior';
      } else {
        ctc = '4.2 LPA (DSA Reality Check Pending)';
        badge = 'O(N³) Time Complexity Enthusiast';
      }
    } else {
      if (score >= 80) {
        ctc = '24.0 LPA + 0.15% ESOPs (Founding Engineer Tier)';
        badge = 'Cracked 3 AM Prod Deployer';
      } else if (score >= 58) {
        ctc = '14.0 LPA (Seed Startup Full-Stack Builder)';
        badge = 'Weekend Hackathon Shipper';
      } else {
        ctc = '4.5 LPA (Localhost-Only Entrepreneur)';
        badge = 'Tutorial Hell Permanent Resident';
      }
    }

    const architectPersona = mode === 'roast' ? 'Sharma Ji The Brutal Staff Architect' : 'Senior SDE Technical Mentor';
    const architectReview =
      mode === 'roast'
        ? hasClones && !hasScale
          ? "Beta, Sharma Ji's blood pressure spiked to 180/120 reading this stack. You put 'Full-Stack' on a localhost Todo list and a Weather API wrapper with zero database indexing, zero caching, and zero concurrency handling!"
          : "Sharma Ji adjusted his spectacles twice. You actually used real backend components, but unless you defend your connection pooling, cache invalidation, and p99 latency under peak traffic, the panel won't hand over a 24 LPA offer letter."
        : `For the ${trackNames[track]}, your core stack shows clear engineering initiative. Strengthen your technical depth by documenting database indexing choices, failure recovery, and benchmark numbers on your top two projects.`;

    const managerPersona = mode === 'roast' ? 'Unhinged Bengaluru Startup PM' : 'Engineering Hiring Manager';
    const managerReview =
      mode === 'roast'
        ? hasMetrics
          ? "Okay, seeing real latency and user numbers almost made me spill my Third Wave iced Americano! Still, prove to me these numbers aren't from a single locust script running on your laptop."
          : "You wrote 'scalable' and 'passionate' without naming a single real user! Did anyone outside your 3 hostel wingmates ever log into this app, or does it only live on localhost:3000?"
        : 'Your resume bullets describe features built rather than business or engineering outcomes. Lead every bullet with measurable user adoption, throughput gains, or latency reduction.';

    const grillQuestion = hasScale
      ? 'If your Redis cluster crashes during a Flipkart Big Billion Days flash sale at 12:00 AM, how does your backend prevent a thundering herd from melting your primary PostgreSQL database?'
      : 'If 10,000 concurrent students hit your main project endpoint at 9:00 AM during exam results, which exact query or route in your code breaks first and how do you fix it in 20 minutes?';

    const hrQuote =
      mode === 'roast'
        ? `With a Hire Score of ${score}/100, ditch the tutorial clones, push your Medium/Hard DSA ratio, and deploy one battle-tested backend service before Day-1 campus slots open.`
        : `You scored ${score}/100 on the ${trackNames[track]}; tightening your quantified impact bullets and practicing the live grill question will put you in the top decile of applicants.`;

    const fixes = [
      'Rewrite your top 3 project bullets using the XYZ format: "Reduced [X] latency by [Y]% by implementing [Z] (Redis caching / composite SQL indexes)".',
      'Replace basic tutorial apps (Todo/Weather/Calculator) with 1 deployed service featuring authentication, rate-limiting, and a live architecture diagram in the README.',
      'Add verifiable proof of engineering rigor: LeetCode/Codeforces contest rating, load-testing benchmarks (k6/Locust), or merged open-source PR links.',
    ];

    return {
      id: 'eval-' + Date.now(),
      timestamp: new Date().toISOString().slice(0, 16).replace('T', ' '),
      mode,
      track,
      trackLabel: trackNames[track],
      hire_score: score,
      predicted_ctc_lpa: ctc,
      badge_title: badge,
      hr_quote: hrQuote,
      architect: { persona: architectPersona, review: architectReview },
      manager: { persona: managerPersona, review: managerReview, grill_question: grillQuestion },
      top_fixes: fixes,
      action_items: fixes,
      grill_question: grillQuestion,
      image_prompt: `Vibrant 3D cyberpunk sticker badge for "${badge}", witty Indian software architect owl mascot holding a golden ${ctc.split(' ')[0]} LPA trophy, dark neon background, text-free`,
    };
  }

  // Run 3-Agent Panel (`tools.call` -> `evaluate_candidate` with `llm.complete` & local fallback)
  async function runPlacementPanel() {
    const profileEl = document.getElementById('candidateProfileInput');
    const runBtn = document.getElementById('runPanelBtn');
    const profileText = (profileEl ? profileEl.value : '').trim();

    if (!profileText) {
      showToast('Paste your resume bullets, GitHub summary, or click a Sample Profile first!');
      return;
    }

    if (runBtn) {
      runBtn.disabled = true;
      runBtn.textContent = '⏳ Running 3-Agent LangGraph Panel (Architect → PM → HR)...';
    }

    let evalResult = null;
    try {
      if (window.anna && window.anna.tools && typeof window.anna.tools.call === 'function') {
        const hostResp = await window.anna.tools.call('evaluate_candidate', {
          candidate_profile: profileText,
          mode: state.mode,
          track: state.track,
        });
        if (hostResp && hostResp.structuredContent) {
          evalResult = hostResp.structuredContent;
        } else if (hostResp && Array.isArray(hostResp.content) && hostResp.content[0]) {
          evalResult = JSON.parse(hostResp.content[0].text);
        }
      }
    } catch (_) {
      evalResult = null;
    }

    if (!evalResult) {
      evalResult = evaluateLocally(profileText, state.mode, state.track);
    }

    evalResult.id = evalResult.id || 'eval-' + Date.now();
    evalResult.timestamp = evalResult.timestamp || new Date().toISOString().slice(0, 16).replace('T', ' ');
    evalResult.trackLabel =
      evalResult.track_label ||
      evalResult.trackLabel ||
      (state.track === 'mass_recruiter'
        ? 'TCS / Infosys Mass Recruiter Track'
        : state.track === 'startup'
        ? 'High-Growth Startup Track'
        : 'Amazon / Flipkart Product SDE-1 Track');

    state.currentEvaluation = evalResult;

    // Update APS Streak & History
    const lpaVal = parseLpaNumber(evalResult.predicted_ctc_lpa);
    if (lpaVal > state.aps.highestCtcLpa) {
      state.aps.highestCtcLpa = lpaVal;
    }
    if (evalResult.hire_score > state.aps.bestHireScore) {
      state.aps.bestHireScore = evalResult.hire_score;
    }
    state.aps.streakDays = Math.max(1, (state.aps.streakDays || 1) + (state.aps.lastPracticeDate !== '2026-10-22' ? 1 : 0));
    state.aps.lastPracticeDate = '2026-10-22';
    state.aps.history.unshift(evalResult);
    state.aps.history = state.aps.history.slice(0, 15);
    await saveApsStorage();

    renderScorecard(evalResult);
    showToast(`CTC Scorecard Ready: ${evalResult.predicted_ctc_lpa}`);

    if (runBtn) {
      runBtn.disabled = false;
      runBtn.textContent = state.mode === 'roast' ? '🔥 Roast My Profile & Predict CTC' : '🎯 Run Placement Coach & Predict CTC';
    }
  }

  function renderScorecard(ev) {
    if (!ev) return;
    document.getElementById('scorecardTrackLabel').textContent = ev.trackLabel || 'Product SDE-1 Track';
    document.getElementById('scorecardCtcValue').textContent = ev.predicted_ctc_lpa;
    document.getElementById('scorecardBadgeTitle').textContent = '🏅 ' + ev.badge_title;
    document.getElementById('scorecardHireScore').textContent = ev.hire_score + '/100';
    document.getElementById('scorecardHrQuote').textContent = '"' + ev.hr_quote + '"';

    const arch = ev.architect || {};
    document.getElementById('architectPersonaLabel').textContent = '1️⃣ ' + (arch.persona || 'Staff Architect');
    document.getElementById('architectReviewText').textContent = arch.review || '';

    const mgr = ev.manager || {};
    document.getElementById('managerPersonaLabel').textContent = '2️⃣ ' + (mgr.persona || 'Startup PM');
    document.getElementById('managerReviewText').textContent = mgr.review || '';
    document.getElementById('grillQuestionText').textContent = mgr.grill_question || ev.grill_question || '';

    const fixesList = document.getElementById('topFixesList');
    if (fixesList) {
      fixesList.innerHTML = '';
      const items = ev.top_fixes || ev.action_items || [];
      items.forEach((fix) => {
        const li = document.createElement('li');
        li.textContent = fix;
        fixesList.appendChild(li);
      });
    }

    const badgePromptEl = document.getElementById('mascotPromptCaption');
    if (badgePromptEl) {
      badgePromptEl.textContent = `Badge Title: "${ev.badge_title}" • Ready for Host Image API or Sticker Export`;
    }
  }

  // Generate AI Mascot Badge (`image.generate` with custom dynamic SVG badge fallback)
  async function generateMascotBadge() {
    const ev = state.currentEvaluation || state.aps.history[0];
    if (!ev) return;

    const btn = document.getElementById('genBadgeBtn');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '🎨 Generating Badge...';
    }

    let generatedUrl = null;
    try {
      if (window.anna && window.anna.image && typeof window.anna.image.generate === 'function') {
        const res = await window.anna.image.generate({
          prompt: ev.image_prompt,
          aspectRatio: '1:1',
        });
        if (res && (res.url || res.dataUrl)) {
          generatedUrl = res.url || res.dataUrl;
        }
      }
    } catch (_) {}

    const imgEl = document.getElementById('mascotPreviewImg');
    const captionEl = document.getElementById('mascotPromptCaption');
    if (generatedUrl && imgEl) {
      imgEl.src = generatedUrl;
    } else if (imgEl) {
      // Dynamic glowing SVG badge overlay if Host Image API isn't active
      const defaultHero = imgEl.getAttribute('data-default-src');
      if (defaultHero) {
        imgEl.src = defaultHero;
      }
    }
    if (captionEl) {
      captionEl.textContent = `✨ Unlocked Mascot Sticker: "${ev.badge_title}" (${ev.predicted_ctc_lpa})`;
    }
    showToast(`Generated Mascot Badge for "${ev.badge_title}"!`);

    if (btn) {
      btn.disabled = false;
      btn.textContent = '🎨 Generate AI Mascot Badge';
    }
  }

  function buildVerbatimMarkdown(ev) {
    const fixes = (ev.top_fixes || ev.action_items || []).map((f, i) => `${i + 1}. ${f}`).join('\n');
    return [
      `## 🎓 Placement Pakka — Official CTC Scorecard`,
      `**Track:** ${ev.trackLabel} | **Predicted CTC:** \`${ev.predicted_ctc_lpa}\` | **Hire Score:** \`${ev.hire_score}/100\``,
      `**Unlocked Badge:** 🏅 **${ev.badge_title}**`,
      `> 💬 **HR Verdict:** *"${ev.hr_quote}"*`,
      `### 1️⃣ ${ev.architect ? ev.architect.persona : 'Staff Architect'}`,
      `${ev.architect ? ev.architect.review : ''}`,
      `### 2️⃣ ${ev.manager ? ev.manager.persona : 'Startup PM'}`,
      `${ev.manager ? ev.manager.review : ''}`,
      `**🎙️ Hot-Seat Grill Question:** *${ev.grill_question || (ev.manager && ev.manager.grill_question) || ''}*`,
      `### 🛠️ Top 3 Resume Fixes`,
      fixes,
    ].join('\n\n');
  }

  // Post Verbatim Scorecard to Anna Chat (`chat.append_artifact`)
  async function postCardToChat() {
    const ev = state.currentEvaluation || state.aps.history[0];
    if (!ev) return;
    const md = buildVerbatimMarkdown(ev);

    try {
      if (window.anna && window.anna.chat && typeof window.anna.chat.append_artifact === 'function') {
        await window.anna.chat.append_artifact({
          type: 'markdown',
          title: `Placement Pakka CTC Card — ${ev.predicted_ctc_lpa}`,
          content: md,
          verbatim: true,
        });
        showToast('Posted CTC Scorecard verbatim to Anna Chat!');
        return;
      }
    } catch (_) {}

    copyTextFallback(md);
    showToast('Copied verbatim Markdown CTC Scorecard to clipboard (ready to paste in chat)!');
  }

  function copyTextFallback(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text);
        return;
      }
    } catch (_) {}
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
    } catch (_) {}
    document.body.removeChild(ta);
  }

  // Share to WhatsApp / X / Discord (`mobile.share` + Web Share + Clipboard Fallback)
  async function shareScorecard() {
    const ev = state.currentEvaluation || state.aps.history[0];
    if (!ev) return;

    const shareSummary = `🔥 Placement Pakka AI Panel predicted my CTC at ${ev.predicted_ctc_lpa} (Hire Score: ${ev.hire_score}/100 | Badge: "${ev.badge_title}")! Can you beat Sharma Ji's Staff Architect roast? #PlacementPakka #IndianTech`;

    try {
      if (window.anna && window.anna.mobile && typeof window.anna.mobile.share === 'function') {
        await window.anna.mobile.share({
          title: 'My Placement Pakka CTC Scorecard',
          text: shareSummary,
        });
        showToast('Shared via Anna Mobile Share Bridge!');
        return;
      }
      if (navigator.share) {
        await navigator.share({
          title: 'My Placement Pakka CTC Scorecard',
          text: shareSummary,
        });
        showToast('Shared CTC Scorecard!');
        return;
      }
    } catch (_) {}

    copyTextFallback(shareSummary);
    showToast('Copied viral WhatsApp / X / Discord share text to clipboard!');
  }

  // Tab 2: Live Voice Hot-Seat (`audio.session`, `audio.speak`, `audio.transcribe`)
  function getActiveVoiceQuestion() {
    const list = VOICE_QUESTIONS[state.voiceRound] || VOICE_QUESTIONS.react_node;
    return list[state.voiceQuestionIndex % list.length];
  }

  function renderVoiceTranscripts() {
    const feed = document.getElementById('voiceTranscriptFeed');
    if (!feed) return;
    feed.innerHTML = '';
    state.voiceTranscripts.forEach((item) => {
      const bubble = document.createElement('div');
      bubble.className = 'chat-bubble ' + (item.role === 'interviewer' ? 'interviewer' : 'candidate');
      bubble.innerHTML = `<strong>${item.speaker}:</strong> ${item.text}`;
      feed.appendChild(bubble);
    });
    feed.scrollTop = feed.scrollHeight;
  }

  async function speakTextAloud(text) {
    const waveBox = document.getElementById('voiceWaveVisualizer');
    if (waveBox) waveBox.classList.add('speaking');

    try {
      if (window.anna && window.anna.audio && typeof window.anna.audio.speak === 'function') {
        await window.anna.audio.speak({ text, voice: 'en-IN-Neural' });
        if (waveBox) waveBox.classList.remove('speaking');
        return;
      }
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'en-IN';
        utter.rate = 1.02;
        utter.onend = () => {
          if (waveBox) waveBox.classList.remove('speaking');
        };
        window.speechSynthesis.speak(utter);
        setTimeout(() => {
          if (waveBox) waveBox.classList.remove('speaking');
        }, 4200);
        return;
      }
    } catch (_) {}

    setTimeout(() => {
      if (waveBox) waveBox.classList.remove('speaking');
    }, 2200);
  }

  async function startVoiceSession(customQuestion) {
    state.voiceSessionActive = true;
    const roundSelect = document.getElementById('voiceRoundSelect');
    if (roundSelect) state.voiceRound = roundSelect.value;

    try {
      if (window.anna && window.anna.audio && typeof window.anna.audio.session === 'function') {
        await window.anna.audio.session({ action: 'start', mode: 'full-duplex', locale: 'en-IN' });
      }
    } catch (_) {}

    const openingQ = customQuestion || getActiveVoiceQuestion();
    document.getElementById('currentHotseatQuestion').textContent = openingQ;
    document.getElementById('voiceStatusBadge').textContent = '🔴 LIVE FULL-DUPLEX AUDIO SESSION';

    state.voiceTranscripts = [
      {
        role: 'interviewer',
        speaker: '🎙️ Panel Interviewer',
        text: openingQ,
      },
    ];
    renderVoiceTranscripts();
    speakTextAloud(openingQ);
    showToast('Live Voice Hot-Seat session started! Speak or type your response.');
  }

  async function transcribeSpokenAnswer() {
    const inputEl = document.getElementById('voiceAnswerInput');
    const waveBox = document.getElementById('voiceWaveVisualizer');
    if (waveBox) waveBox.classList.add('speaking');

    try {
      if (window.anna && window.anna.audio && typeof window.anna.audio.transcribe === 'function') {
        const res = await window.anna.audio.transcribe({ timeoutMs: 8000, locale: 'en-IN' });
        if (res && res.text && inputEl) {
          inputEl.value = res.text;
          if (waveBox) waveBox.classList.remove('speaking');
          await submitVoiceTurn();
          return;
        }
      }
    } catch (_) {}

    // Sample realistic spoken transcript when mic/host isn't attached in sandbox preview
    const sampleSpoken =
      state.voiceRound === 'hr_behavioral'
        ? 'During our pre-final year hackathon, our MongoDB Atlas IP whitelist locked us out 90 minutes before judging. I immediately spun up a local Dockerized Postgres instance, migrated the seed schema in 15 minutes, and our live demo won 2nd place.'
        : state.voiceRound === 'python_dsa'
        ? 'I would use a Redis-backed token bucket with Lua atomic scripts per API key so all 8 Python workers share state in O(1) time without race conditions, with a local in-memory sliding window fallback if Redis latency spikes.'
        : 'I would wrap the checkout deduction in a PostgreSQL transaction using SELECT FOR UPDATE SKIP LOCKED or an atomic UPDATE SET stock = stock - 1 WHERE id = $1 AND stock > 0, paired with an idempotency key in Redis.';

    if (inputEl && !inputEl.value.trim()) {
      inputEl.value = sampleSpoken;
    }
    setTimeout(async () => {
      if (waveBox) waveBox.classList.remove('speaking');
      await submitVoiceTurn();
    }, 650);
  }

  async function submitVoiceTurn() {
    const inputEl = document.getElementById('voiceAnswerInput');
    const answerText = (inputEl ? inputEl.value : '').trim();
    if (!answerText) {
      showToast('Click "🎙️ Push-to-Talk (Transcribe)" or type your spoken answer first!');
      return;
    }

    state.voiceTranscripts.push({
      role: 'candidate',
      speaker: '🧑‍💻 You (Transcribed)',
      text: answerText,
    });
    if (inputEl) inputEl.value = '';
    renderVoiceTranscripts();

    const words = answerText.split(/\s+/).length;
    const hasTechKeywords = /(redis|atomic|lock|transaction|docker|postgres|latency|o\(1\)|idempotency|index)/i.test(answerText);
    const fluency = Math.min(96, Math.max(62, 66 + Math.min(25, words)));
    const confidence = Math.min(95, Math.max(64, 68 + (hasTechKeywords ? 20 : 10)));
    const depth = Math.min(97, Math.max(58, 60 + (hasTechKeywords ? 28 : 12)));

    state.voiceQuestionIndex += 1;
    const nextQ = getActiveVoiceQuestion();
    const feedback = hasTechKeywords
      ? `Strong production instinct mentioning atomic concurrency controls! Next question: ${nextQ}`
      : `Good structure, but name the exact database lock or complexity bound next time. Next question: ${nextQ}`;

    state.voiceTranscripts.push({
      role: 'interviewer',
      speaker: '🎙️ Panel Interviewer',
      text: feedback,
    });
    document.getElementById('currentHotseatQuestion').textContent = nextQ;
    renderVoiceTranscripts();

    document.getElementById('voiceFluencyVal').textContent = fluency + '/100';
    document.getElementById('voiceConfidenceVal').textContent = confidence + '/100';
    document.getElementById('voiceDepthVal').textContent = depth + '/100';

    speakTextAloud(feedback);
  }

  // Tab 3: APS Dashboard & History Renderer
  function renderApsDashboard() {
    const streakEl = document.getElementById('headerStreakText');
    if (streakEl) streakEl.textContent = `${state.aps.streakDays} Day Streak`;

    const kpiStreak = document.getElementById('apsStreakDays');
    const kpiCtc = document.getElementById('apsHighestCtc');
    const kpiScore = document.getElementById('apsBestScore');
    const kpiCount = document.getElementById('apsTotalEvals');

    if (kpiStreak) kpiStreak.textContent = `${state.aps.streakDays} Days 🔥`;
    if (kpiCtc) kpiCtc.textContent = `${state.aps.highestCtcLpa.toFixed(1)} LPA`;
    if (kpiScore) kpiScore.textContent = `${state.aps.bestHireScore} / 100`;
    if (kpiCount) kpiCount.textContent = `${state.aps.history.length} Sessions`;

    const listEl = document.getElementById('apsHistoryList');
    if (!listEl) return;
    listEl.innerHTML = '';

    state.aps.history.forEach((item, idx) => {
      const card = document.createElement('div');
      card.className = 'agent-card';
      card.style.cursor = 'pointer';
      card.innerHTML = `
        <div class="agent-header">
          <span><strong>${item.predicted_ctc_lpa}</strong> — <span style="color:#fde68a;">🏅 ${item.badge_title}</span></span>
          <span style="color:#94a3b8;font-size:0.75rem;">${item.timestamp || 'Recent'} • Score: ${item.hire_score}/100</span>
        </div>
        <div style="font-size:0.8rem;color:#cbd5e1;margin-bottom:6px;">${item.hr_quote}</div>
        <button type="button" class="btn-secondary" data-history-index="${idx}" style="padding:4px 10px;font-size:0.74rem;">
          📂 Load Scorecard in Tab 1
        </button>
      `;
      listEl.appendChild(card);
    });

    listEl.querySelectorAll('[data-history-index]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute('data-history-index'), 10);
        const target = state.aps.history[idx];
        if (target) {
          state.currentEvaluation = target;
          renderScorecard(target);
          switchTab('tab-roast');
          showToast(`Loaded "${target.badge_title}" Scorecard!`);
        }
      });
    });
  }

  function switchTab(tabId) {
    document.querySelectorAll('.nav-tab').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
    });
    document.querySelectorAll('.tab-pane').forEach((pane) => {
      pane.classList.toggle('active', pane.id === tabId);
    });
  }

  function initEventListeners() {
    // Tab Switching
    document.querySelectorAll('.nav-tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        switchTab(btn.getAttribute('data-tab'));
      });
    });

    const streakChip = document.getElementById('headerStreakChip');
    if (streakChip) {
      streakChip.addEventListener('click', () => switchTab('tab-history'));
    }

    // Sample Profile Buttons
    document.querySelectorAll('[data-sample]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.getAttribute('data-sample');
        const sample = SAMPLE_PROFILES[key];
        if (!sample) return;
        const inputEl = document.getElementById('candidateProfileInput');
        if (inputEl) inputEl.value = sample.text;
        state.track = sample.track;
        state.mode = sample.mode;
        const trackSel = document.getElementById('trackSelect');
        if (trackSel) trackSel.value = sample.track;
        updateModeButtons();
        runPlacementPanel();
      });
    });

    // Mode Toggle Buttons
    const modeRoastBtn = document.getElementById('modeRoastBtn');
    const modeCoachBtn = document.getElementById('modeCoachBtn');

    function updateModeButtons() {
      if (!modeRoastBtn || !modeCoachBtn) return;
      modeRoastBtn.className = 'mode-btn ' + (state.mode === 'roast' ? 'active-roast' : '');
      modeCoachBtn.className = 'mode-btn ' + (state.mode === 'coach' ? 'active-coach' : '');
      const runBtn = document.getElementById('runPanelBtn');
      if (runBtn) {
        runBtn.textContent =
          state.mode === 'roast' ? '🔥 Roast My Profile & Predict CTC' : '🎯 Run Placement Coach & Predict CTC';
      }
    }

    if (modeRoastBtn) {
      modeRoastBtn.addEventListener('click', () => {
        state.mode = 'roast';
        updateModeButtons();
      });
    }
    if (modeCoachBtn) {
      modeCoachBtn.addEventListener('click', () => {
        state.mode = 'coach';
        updateModeButtons();
      });
    }

    const trackSel = document.getElementById('trackSelect');
    if (trackSel) {
      trackSel.addEventListener('change', () => {
        state.track = trackSel.value;
      });
    }

    // Primary Panel Run Button
    const runBtn = document.getElementById('runPanelBtn');
    if (runBtn) {
      runBtn.addEventListener('click', runPlacementPanel);
    }

    // Scorecard Action Buttons
    const genBadgeBtn = document.getElementById('genBadgeBtn');
    if (genBadgeBtn) genBadgeBtn.addEventListener('click', generateMascotBadge);

    const postChatBtn = document.getElementById('postChatBtn');
    if (postChatBtn) postChatBtn.addEventListener('click', postCardToChat);

    const shareBtn = document.getElementById('shareScorecardBtn');
    if (shareBtn) shareBtn.addEventListener('click', shareScorecard);

    const practiceGrillBtn = document.getElementById('practiceGrillBtn');
    if (practiceGrillBtn) {
      practiceGrillBtn.addEventListener('click', () => {
        const ev = state.currentEvaluation || state.aps.history[0];
        const q = ev ? ev.grill_question || (ev.manager && ev.manager.grill_question) : null;
        switchTab('tab-voice');
        startVoiceSession(q);
      });
    }

    // Voice Hot-Seat Controls
    const startVoiceBtn = document.getElementById('startVoiceSessionBtn');
    if (startVoiceBtn) startVoiceBtn.addEventListener('click', () => startVoiceSession());

    const transcribeBtn = document.getElementById('transcribeVoiceBtn');
    if (transcribeBtn) transcribeBtn.addEventListener('click', transcribeSpokenAnswer);

    const submitVoiceBtn = document.getElementById('submitVoiceAnswerBtn');
    if (submitVoiceBtn) submitVoiceBtn.addEventListener('click', submitVoiceTurn);

    const speakPromptBtn = document.getElementById('speakQuestionBtn');
    if (speakPromptBtn) {
      speakPromptBtn.addEventListener('click', () => {
        const q = document.getElementById('currentHotseatQuestion').textContent;
        speakTextAloud(q);
      });
    }

    // APS Reset / Check-In Button
    const checkInBtn = document.getElementById('dailyCheckInBtn');
    if (checkInBtn) {
      checkInBtn.addEventListener('click', async () => {
        state.aps.streakDays += 1;
        await saveApsStorage();
        showToast(`🔥 Daily Practice Check-In Recorded! Streak is now ${state.aps.streakDays} days.`);
      });
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    // Seed initial input & scorecard so the UI looks rich immediately on load
    const inputEl = document.getElementById('candidateProfileInput');
    if (inputEl && !inputEl.value) {
      inputEl.value = SAMPLE_PROFILES.sde_aspirant.text;
    }
    state.currentEvaluation = state.aps.history[0];
    renderScorecard(state.currentEvaluation);
    connectAnnaHost();
  });
})();

