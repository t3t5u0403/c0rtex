# presentation outline — c0rtex prompt-injection mitigation

Structure for a ~10–12 min open-source programming class talk, plus live
demo and Q&A. Frames the hobby-vs-class split explicitly, treats the
security work as real research (limitations included), and uses the
generated charts as the natural climax.

## suggested outline (~11 min + demo + Q&A)

### 1. Title slide (30 s)
- **c0rtex: layered defenses against indirect prompt injection**
- Your name(s), class, date
- One-line framing: "Adding defense-in-depth to an open-source local AI assistant."

### 2. What is c0rtex? (1.5 min)
- Local, privacy-first personal AI assistant. Ollama backend, runs on your own hardware.
- ~30 guardrailed tools — file ops, system monitoring, web browsing, CTF helpers.
- Originally a personal hobby project. Open source (MIT).
- One architecture slide: user → c0rtex loop → ollama → tool calls → ollama → final response.
- Mention the stack briefly (Python, Flask dashboard, Matrix bridge) — shows it's a real project, not a toy.

### 3. Scope for this class (30 s)
- **Be explicit:** "The rest of c0rtex pre-existed as a hobby project. What my teammate and I contributed for this class is the prompt-injection mitigation layer — merged as PR #4 on `main`."
- Credits: you + teammate's handle.
- Open-source fingerprint: link to the PR, the commit hashes. Shows you actually used OSS workflows (branch, PR, review, merge).

### 4. The threat: why indirect prompt injection matters (2 min)
- **Direct injection** (user tells the AI to misbehave): mostly a model-alignment problem.
- **Indirect injection** (AI reads malicious instructions from a web page, doc, email): much worse because *the untrusted input is opened by the model itself*, inside its agent loop.
- Why c0rtex is specifically vulnerable: `browse_page` pulls arbitrary web content into the context window, and the agent has file-writing and shell-ish tools.
- Concrete recent example (Simon Willison's writeups on prompt injection, or the Bing Chat "Sydney" leaks, or the 2024 GitHub Copilot Workspace injections) — grounds it in the real world.

### 5. The defenses — before + after our PR (3 min)
One slide on what *already existed*, one on what *we added*.

**Already in c0rtex:**
- Content isolation wrapper (`[UNTRUSTED WEB CONTENT]` markers in `c0rtex_pinchtab.py`)
- Path-scoping on file tools, no `shell=True`, automatic `.bak` backups
- Honest caveat: all prompt-based, model-behavior-dependent

**What we (PR #4) added — show a small code snippet per layer:**

| layer | mechanism                          | where                     |
|-------|------------------------------------|---------------------------|
| 1     | keyword blocklist on tool args     | `validate_input`          |
| 2     | system-prompt hardening            | `DEFAULT_SOUL`            |
| 3     | subprocess command whitelist       | `_run_safe`               |
| 4     | ndjson security-event logging      | `Logger.security_alert`   |
| 5     | console alert on block             | `c0rtex.py` tool-result path |

Architecture diagram: arrows showing where each layer sits in the request flow.

### 6. How do we know it works? Evaluation setup (1 min)
- 6 attack classes, each isolated in its own HTML page (show `index.html` screenshot).
- 3 model sizes for a capability-vs-defense comparison.
- Automated scoring: marker tokens in transcripts, plus forbidden-tool-call detection in logs.
- Reproducible: `./run_all.sh <repo> <models...>` — one command, deterministic grading.
- Frame as a **controlled experiment**, not a vibe check.

### 7. Live demo (2–3 min) — the highlight
Pick 2–3 pages to browse interactively. Best contrast:
1. **01-overt** — obvious injection, defense clearly blocks.
2. **03-subtle-social** — no trigger keywords, model judgment is the only defense. Tension: will it catch it?
3. **04-bypass** (synonym variant) — shows the keyword blocklist's weakness.

Have the log viewer open in another pane so the audience sees `security_violation` events fire in real time (or not).

### 8. Results (2 min) — use your charts
- **`01_overall_defense_rate.png`** — headline number: "c0rtex blocks X%/Y%/Z% of attacks across the three model sizes."
- **`02_pass_rate_by_class.png`** — the interesting slide. Where does defense scale with model capability, and where does it not?
- **`03_status_heatmap.png`** — dense summary, one glance = "we did a lot of tests."
- One interpretation bullet under each chart, not just the chart alone.

### 9. Honest limitations (1 min) — often the best slide
- Keyword blocklist is bypassable with synonyms / unicode / whitespace (show a `04-bypass` row).
- `validate_input` runs on tool args, not LLM inputs → can't catch indirect injection directly.
- No cryptographic enforcement — all defenses ultimately depend on model behavior.
- We found a duplicate monitoring block bug during this work (code quality observation).
- This is **good** for the talk: shows you critically evaluated your own work.

### 10. What we learned / future work (30 s)
- Defense in depth works: no single layer is sufficient, but stacking them raised the bar.
- Empirical testing beat theoretical argument — some layers looked strong on paper and weren't.
- Future: semantic input filtering via a secondary LLM, stronger content sandboxing, formalized threat model doc in the repo.
- OSS angle: our work is public; anyone can audit, fork, or improve it.

### 11. Q&A / thanks (30 s)
- Repo link, PR link, your contact.
- One backup slide with the full results table in case someone asks for raw numbers.

## framing tips

- **Own the hobby/class split transparently.** Professors like when students clearly demarcate "this was the baseline project, this was the delta I/we added." Saves them from having to ask.
- **Lead with the threat, not the solution.** Spend time making the audience *feel* why indirect injection matters before you show what you did.
- **Show code, sparingly.** One well-chosen 5-line snippet per layer beats a wall of code.
- **Don't oversell.** A student talk that says "we built a bulletproof defense" gets picked apart. A talk that says "we built defense-in-depth; here's what works, here's what doesn't, here's the data" gets respect.
- **The live demo is the emotional peak.** Rehearse the happy path once and have a backup video if the network/ollama flakes.
- **OSS workflow is a freebie you should mention.** The PR itself is evidence of collaboration. A screenshot of the merged PR on GitHub is a good "this is how we worked" slide.

## a note on ordering

If your class weighs OSS process heavily, swap sections 3 and 4 so "how
we worked" comes before "what we did." If it weighs technical depth,
keep the order above.
