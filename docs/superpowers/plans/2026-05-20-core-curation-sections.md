# Core Curation Sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `핵심 큐레이션` list with sectioned executive briefing groups and attach optional LLM-generated summary/evaluation text to each curated item.

**Architecture:** Keep article and policy collection unchanged. Build curation sections in `site/build.py` after the existing article/policy views are available, using deterministic section rules first and an optional `CORE_CURATION_AI_CMD` subprocess enrichment step that returns JSON `{id, summary, evaluation}` updates. Render `curation_sections` in the existing Jinja dashboard, with rule-based fallback copy when the LLM command is missing or fails.

**Tech Stack:** Python, Jinja, existing static build pipeline, plain CSS, pytest.

---

### Task 1: Curation Section Builder

**Files:**
- Modify: `site/build.py`
- Test: `tests/test_site_build.py`

- [x] **Step 1: Add failing tests for sectioned sorting**

Add tests that create article/policy dicts for box-office, policy, competitor, overseas, and culture/IP signals. Assert `curation_sections(...)` returns ordered sections with no duplicate article assigned to multiple sections.

- [x] **Step 2: Implement deterministic sectioning**

Add section definitions in `site/build.py`, classify each top candidate into one section, sort candidates with the existing `_curation_priority(...)`, and cap each section to two items.

- [x] **Step 3: Preserve old flat selector tests**

Keep `top_curation_items(...)` unchanged so existing tests remain meaningful; make the new section builder call the existing priority and eligibility helpers instead of replacing them.

### Task 2: LLM Summary/Evaluation Enrichment

**Files:**
- Modify: `site/build.py`
- Test: `tests/test_site_build.py`

- [x] **Step 1: Add failing tests for fallback and command success**

Test that missing `CORE_CURATION_AI_CMD` creates deterministic `curation_summary` and `curation_evaluation`, and that a command returning a JSON array updates those fields.

- [x] **Step 2: Implement opt-in command runner**

Add `_curation_ai_prompt(...)`, `_parse_curation_ai_output(...)`, and `enrich_curation_sections_with_ai(...)`. Run subprocess without `shell=True`, with UTF-8 input/output, captured stdout/stderr, and a timeout.

- [x] **Step 3: Keep build resilient**

If the command is missing, fails, times out, or returns invalid JSON, print a warning only when relevant and keep the fallback text.

### Task 3: Dashboard Rendering

**Files:**
- Modify: `site/template.html.j2`
- Modify: `site/style.css`
- Test: `tests/test_site_build.py`

- [x] **Step 1: Add template test**

Assert the template contains the section labels and summary/evaluation labels.

- [x] **Step 2: Render sectioned curation**

Replace the flat `curation` loop with a `curation_sections` loop. Each section gets a short heading, count/label, and compact cards with source, title, 요약, 평가, and matched keyword chips.

- [x] **Step 3: Style dense briefing layout**

Use the existing light dashboard style. Add compact section bands, stable card spacing, and mobile one-column behavior. Do not add a new visual system.

### Task 4: Verification And Commit

**Files:**
- Generated: `dist/index.html`

- [x] Run targeted tests for `tests/test_site_build.py`.
- [x] Run `python -m pytest tests -q`.
- [x] Run `python site\build.py`.
- [x] Run `git diff --check`.
- [x] Scan for secrets.
- [ ] Commit and push to `briefing-dashboard`.
