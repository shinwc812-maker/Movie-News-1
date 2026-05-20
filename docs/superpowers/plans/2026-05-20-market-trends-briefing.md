# Market Trends Briefing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `시장동향 / Live·IP·팝업` section that classifies market-trend articles and optionally enriches them with GPT CLI style summaries.

**Architecture:** Add a separate `data/market_trends.json` artifact so market trends do not mix with official movie articles or community reactions. The crawler builds rule-based trend cards from collected articles first, augments them with Naver News/OpenAPI plus Google News RSS fallback, then optionally calls an operator-provided `MARKET_TRENDS_AI_CMD` command to rewrite the frame, short note, and business implication. The static site reads the new artifact and renders a compact dashboard section.

**Tech Stack:** Python dataclasses, existing crawler pipeline, optional subprocess-based CLI integration, Jinja static HTML, CSS.

---

### Task 1: Data Model

**Files:**
- Modify: `crawler/briefing_models.py`
- Test: `tests/test_briefing_models.py`

- [x] **Step 1: Write the failing test**

```python
def test_market_trend_item_serializes_business_summary():
    item = MarketTrendItem(
        category="팝업/공간",
        title="팝업이 팬덤 소비 동선으로 이동",
        url="https://example.com/popup",
        source="Example",
        frame="팝업은 부가 이벤트가 아니라 기본 동선",
        note="팬덤이 오프라인 공간에 반복 방문하는 흐름.",
        implication="극장 공간과 IP 이벤트를 함께 설계할 여지가 큼.",
        keywords=["팝업", "팬덤"],
    )
    assert MarketTrendItem.from_dict(item.to_dict()).implication.startswith("극장")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests\test_briefing_models.py::test_market_trend_item_serializes_business_summary -q`

- [x] **Step 3: Implement `MarketTrendItem`**

Add a dataclass with `category`, `title`, `url`, `source`, `frame`, `note`, `implication`, `published_at`, `keywords`, and `content_kind="market_trend"`.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests\test_briefing_models.py::test_market_trend_item_serializes_business_summary -q`

### Task 2: Market Trend Builder

**Files:**
- Create: `crawler/market_trends.py`
- Modify: `crawler/main.py`
- Test: `tests/test_market_trends.py`

- [x] **Step 1: Write failing tests**

Test category classification for immersive content, IP/OSMU, and popup articles. Test that `MARKET_TRENDS_AI_CMD` absence returns deterministic rule-based summaries. Test that an AI command failure keeps the rule-based summary.

- [x] **Step 2: Implement builder**

Create category keyword tables, `build_market_trends(articles, limit_per_category=3)`, Naver/Google fallback parsers, rule-based summaries, and `enrich_market_trends_with_ai(items, command=None)`.

- [x] **Step 3: Wire into main**

After official articles are scored/deduped, build market trends and write `data/market_trends.json`.

### Task 3: Dashboard Rendering

**Files:**
- Modify: `site/build.py`
- Modify: `site/template.html.j2`
- Modify: `site/style.css`
- Test: `tests/test_site_build.py`

- [x] **Step 1: Write failing render tests**

Test that `market_trend_view()` formats trend items and that the built template exposes `시장동향 / Live·IP·팝업` separately from official articles.

- [x] **Step 2: Implement render path**

Load `data/market_trends.json`, pass `market_trends` to the template, and render a compact three-column/category-aware section under the main briefing bands.

### Task 4: Verification And Commit

**Files:**
- Generated: `data/market_trends.json`
- Generated: `dist/index.html`

- [x] Run targeted tests.
- [x] Run `python -m pytest tests -q`.
- [x] Run `python site\build.py`.
- [x] Run `git diff --check`.
- [x] Scan for secrets.
- [ ] Commit and push to `briefing-dashboard`.
