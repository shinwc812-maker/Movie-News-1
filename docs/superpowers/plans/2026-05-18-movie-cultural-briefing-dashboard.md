# Movie/Culture Briefing Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an internal static briefing dashboard that combines official movie news, expanded community reactions, KOBIS box office data, KOBIS reservation-rate screenshot capture, and film/culture policy updates.

**Architecture:** Keep the existing `crawler.main -> data/*.json -> site/build.py -> dist/index.html` pipeline. Add focused collectors for market data, community reactions, and policy notices, then make the static-site build load those artifacts and render the approved A-layout dashboard.

**Tech Stack:** Python 3.11, `httpx`, `selectolax`, `jinja2`, `rapidfuzz`, `python-dateutil`, optional Playwright browser capture for KOBIS reservation screenshots.

---

## File Structure

- Modify `.gitignore`: ignore local browser/runtime output and keep committed generated dashboard artifacts intentional.
- Modify `pyproject.toml`: add `playwright` for screenshot capture.
- Modify `.github/workflows/daily.yml`: install Chromium and pass `KOBIS_API_KEY`.
- Modify `README.md`: document `KOBIS_API_KEY`, browser capture, and new dashboard sections.
- Modify `crawler/models.py`: add `content_kind` and optional score-reason metadata to `Article`.
- Create `crawler/briefing_models.py`: dataclasses for KOBIS market data, reservation capture, community reactions, policy notices, and crawl diagnostics.
- Create `crawler/kobis.py`: KOBIS daily box office client, live reservation parsing, and screenshot capture.
- Create `crawler/community.py`: community source interface, existing Extreme Movie community extraction, and config-driven extension hooks for public community pages.
- Create `crawler/policies.py`: KOFIC and MCST policy/support notice collectors.
- Modify `crawler/scorer.py`: add KOBIS top-5 title boost and community trend scoring.
- Modify `crawler/main.py`: orchestrate article, market, community, policy, screenshot, scoring, and JSON saves.
- Modify `site/build.py`: load all artifacts, create view models, and degrade gracefully when artifacts are missing.
- Replace `site/template.html.j2`: render A-layout dashboard with separated official/community sections.
- Replace `site/style.css`: desktop briefing layout, compact cards, mobile fallback.
- Create `tests/test_kobis.py`: KOBIS parsing and date tests.
- Create `tests/test_scorer_market.py`: KOBIS boost tests.
- Create `tests/test_site_build.py`: missing-artifact and section-separation tests.
- Create `tests/test_policies.py`: policy notice parsing tests.

---

### Task 1: Data Models And Article Source Typing

**Files:**
- Modify: `crawler/models.py`
- Create: `crawler/briefing_models.py`
- Test: `tests/test_briefing_models.py`

- [ ] **Step 1: Write failing tests for new model serialization**

Create `tests/test_briefing_models.py`:

```python
from datetime import datetime, timezone

from crawler.briefing_models import (
    BoxOfficeMovie,
    CommunityReaction,
    MarketSnapshot,
    PolicyItem,
    ReservationSnapshot,
)
from crawler.models import Article


def test_article_defaults_to_official_content_kind():
    article = Article(id="a1", source="Variety", country="US", title="News")

    data = article.to_dict()
    restored = Article.from_dict(data)

    assert data["content_kind"] == "official"
    assert restored.content_kind == "official"


def test_market_snapshot_round_trips_datetime():
    snapshot = MarketSnapshot(
        target_date="20260517",
        fetched_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            BoxOfficeMovie(
                rank=1,
                movie_code="20260001",
                title="왕과 사는 남자",
                audi_count=221380,
                audi_acc=12435466,
            )
        ],
    )

    restored = MarketSnapshot.from_dict(snapshot.to_dict())

    assert restored.target_date == "20260517"
    assert restored.movies[0].title == "왕과 사는 남자"
    assert restored.movies[0].audi_count == 221380
    assert restored.fetched_at.tzinfo is not None


def test_community_and_policy_models_serialize_minimal_fields():
    reaction = CommunityReaction(
        id="c1",
        source="익스트림무비",
        title="관객 반응",
        url="https://example.com/community/1",
        excerpt="본문 일부",
        mood_summary="호평과 우려가 함께 보임",
        matched_keywords=["왕과 사는 남자"],
    )
    policy = PolicyItem(
        id="p1",
        source="영화진흥위원회",
        category="공고",
        title="제작지원 사업 공고",
        url="https://example.com/policy/1",
        published_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        summary="장편 극영화 제작지원",
    )
    reservation = ReservationSnapshot(
        captured_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        image_path="assets/reservation.png",
        top_movie="군체",
        top_rate="46.5%",
    )

    assert CommunityReaction.from_dict(reaction.to_dict()).mood_summary == "호평과 우려가 함께 보임"
    assert PolicyItem.from_dict(policy.to_dict()).category == "공고"
    assert ReservationSnapshot.from_dict(reservation.to_dict()).top_rate == "46.5%"
```

- [ ] **Step 2: Run the failing tests**

Run: `python -m pytest tests/test_briefing_models.py -q`

Expected: fail because `crawler.briefing_models` and `Article.content_kind` do not exist.

- [ ] **Step 3: Add model fields and dataclasses**

Modify `crawler/models.py`:

```python
from typing import Literal, Optional


@dataclass
class Article:
    id: str
    source: str
    country: Literal["US", "KR"]
    title: str
    title_ko: Optional[str] = None
    summary: str = ""
    summary_ko: Optional[str] = None
    url: str = ""
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    content_kind: Literal["official", "community"] = "official"
    tier: int = 4
    score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
```

Update `Article.from_dict()` to tolerate older JSON:

```python
if "content_kind" not in d:
    d["content_kind"] = "official"
```

Create `crawler/briefing_models.py` with `to_dict()` and `from_dict()` helpers for `BoxOfficeMovie`, `MarketSnapshot`, `ReservationSnapshot`, `CommunityReaction`, `PolicyItem`, and `CrawlDiagnostic`. Use ISO datetime strings exactly like `Article`.

- [ ] **Step 4: Run model tests**

Run: `python -m pytest tests/test_briefing_models.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add crawler/models.py crawler/briefing_models.py tests/test_briefing_models.py
git commit -m "Add briefing data models"
```

---

### Task 2: KOBIS Market Client And Reservation Screenshot

**Files:**
- Create: `crawler/kobis.py`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/daily.yml`
- Test: `tests/test_kobis.py`

- [ ] **Step 1: Write failing tests for KOBIS parsing**

Create `tests/test_kobis.py`:

```python
import json
from datetime import date

from crawler.kobis import (
    build_daily_boxoffice_url,
    kst_yesterday,
    parse_daily_boxoffice,
    parse_reservation_top,
)


def test_kst_yesterday_formats_target_date():
    assert kst_yesterday(date(2026, 5, 18)) == "20260517"


def test_build_daily_boxoffice_url_uses_key_and_target_date():
    url = build_daily_boxoffice_url("abc", "20260517")

    assert "key=abc" in url
    assert "targetDt=20260517" in url
    assert "searchDailyBoxOfficeList.json" in url


def test_parse_daily_boxoffice_keeps_top_five_by_rank():
    payload = {
        "boxOfficeResult": {
            "dailyBoxOfficeList": [
                {"rank": "1", "movieCd": "m1", "movieNm": "왕과 사는 남자", "audiCnt": "221,380", "audiAcc": "12,435,466"},
                {"rank": "2", "movieCd": "m2", "movieNm": "호퍼스", "audiCnt": "17445", "audiAcc": "375392"},
                {"rank": "6", "movieCd": "m6", "movieNm": "기타", "audiCnt": "1", "audiAcc": "2"},
            ]
        }
    }

    movies = parse_daily_boxoffice(payload)

    assert [m.rank for m in movies] == [1, 2]
    assert movies[0].title == "왕과 사는 남자"
    assert movies[0].audi_count == 221380


def test_parse_reservation_top_from_kobis_mobile_html():
    html = """
    <h3>실시간 예매율</h3>
    <p>1</p>
    <p>군체  (COLONY)</p>
    <p>예매율(예매관객수)</p>
    <p>46.5% (110,465명)</p>
    """

    top_movie, top_rate = parse_reservation_top(html)

    assert top_movie == "군체"
    assert top_rate == "46.5%"
```

- [ ] **Step 2: Run the failing tests**

Run: `python -m pytest tests/test_kobis.py -q`

Expected: fail because `crawler.kobis` does not exist.

- [ ] **Step 3: Implement KOBIS client**

Create `crawler/kobis.py` with:

```python
KOBIS_DAILY_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
KOBIS_RESERVATION_URL = "https://www.kobis.or.kr/kobis/mobile/main/findRealTicketList.do"
```

Functions:

- `kst_yesterday(today: date | None = None) -> str`
- `build_daily_boxoffice_url(api_key: str, target_date: str) -> str`
- `parse_daily_boxoffice(payload: dict) -> list[BoxOfficeMovie]`
- `fetch_market_snapshot(api_key: str, target_date: str | None = None) -> MarketSnapshot`
- `parse_reservation_top(html: str) -> tuple[str | None, str | None]`
- `capture_reservation_snapshot(output_dir: Path) -> ReservationSnapshot`
- `save_market_snapshot(snapshot: MarketSnapshot, path: Path) -> None`
- `save_reservation_snapshot(snapshot: ReservationSnapshot, path: Path) -> None`

Use `httpx` for API and page HTML. For screenshot, import Playwright inside the function so normal tests do not require browser startup:

```python
from playwright.sync_api import sync_playwright
```

If Playwright import or capture fails, return `ReservationSnapshot(capture_failed=True, error_message=str(exc))` and do not raise.

- [ ] **Step 4: Add Playwright dependency and workflow install**

Modify `pyproject.toml` dependencies:

```toml
    "playwright",
```

Modify `.github/workflows/daily.yml` after dependency install:

```yaml
      - name: Install browser for KOBIS capture
        run: uv run python -m playwright install chromium
```

Add to `Crawl news` env:

```yaml
          KOBIS_API_KEY: ${{ secrets.KOBIS_API_KEY }}
```

- [ ] **Step 5: Run KOBIS tests**

Run: `python -m pytest tests/test_kobis.py -q`

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add crawler/kobis.py pyproject.toml .github/workflows/daily.yml tests/test_kobis.py
git commit -m "Add KOBIS market data client"
```

---

### Task 3: Market-Aware Scoring

**Files:**
- Modify: `crawler/scorer.py`
- Test: `tests/test_scorer_market.py`

- [ ] **Step 1: Write failing scoring tests**

Create `tests/test_scorer_market.py`:

```python
from datetime import datetime, timezone

from crawler.briefing_models import BoxOfficeMovie, MarketSnapshot
from crawler.models import Article
from crawler.scorer import score_all


def test_boxoffice_rank_one_boosts_matching_article_above_unmatched():
    market = MarketSnapshot(
        target_date="20260517",
        fetched_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            BoxOfficeMovie(rank=1, movie_code="m1", title="왕과 사는 남자", audi_count=221380, audi_acc=12435466),
            BoxOfficeMovie(rank=5, movie_code="m5", title="휴민트", audi_count=4308, audi_acc=1955611),
        ],
    )
    matched = Article(id="a1", source="씨네21", country="KR", title="왕과 사는 남자 흥행 독주")
    unmatched = Article(id="a2", source="씨네21", country="KR", title="다른 영화 소식")

    score_all([matched, unmatched], now=datetime(2026, 5, 18, tzinfo=timezone.utc), market=market)

    assert matched.score > unmatched.score
    assert "왕과 사는 남자" in matched.matched_keywords


def test_community_score_is_lower_than_official_for_same_boxoffice_match():
    market = MarketSnapshot(
        target_date="20260517",
        fetched_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[BoxOfficeMovie(rank=1, movie_code="m1", title="왕과 사는 남자", audi_count=221380, audi_acc=12435466)],
    )
    official = Article(id="a1", source="씨네21", country="KR", title="왕과 사는 남자 흥행", content_kind="official")
    community = Article(id="c1", source="커뮤니티", country="KR", title="왕과 사는 남자 반응", content_kind="community")

    score_all([official, community], now=datetime(2026, 5, 18, tzinfo=timezone.utc), market=market)

    assert official.score > community.score
```

- [ ] **Step 2: Run failing scoring tests**

Run: `python -m pytest tests/test_scorer_market.py -q`

Expected: fail because `score_all(..., market=...)` is unsupported.

- [ ] **Step 3: Implement market boost**

Modify `crawler/scorer.py`:

- Add constants:

```python
BOXOFFICE_RANK_BOOSTS = {1: 700, 2: 500, 3: 350, 4: 250, 5: 180}
COMMUNITY_SCORE_FACTOR = 0.45
```

- Add `market` optional argument to `score_article()` and `score_all()`.
- Normalize title text by lowercasing and removing extra whitespace.
- If a KOBIS movie title appears in article title or summary, add rank boost and append the movie title to `matched_keywords`.
- If `article.content_kind == "community"`, apply the community factor to the market boost only.

- [ ] **Step 4: Run scoring tests**

Run: `python -m pytest tests/test_scorer_market.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add crawler/scorer.py tests/test_scorer_market.py
git commit -m "Weight article scoring by box office"
```

---

### Task 4: Community Reaction Collection

**Files:**
- Create: `crawler/community.py`
- Modify: `crawler/main.py`
- Test: `tests/test_community.py`

- [ ] **Step 1: Write failing community parser tests**

Create `tests/test_community.py`:

```python
from crawler.community import parse_extmovie_community_cards, summarize_reaction_mood


def test_parse_extmovie_community_cards_extracts_reaction_fields():
    html = """
    <div class="widget-title">뉴스</div>
    <div class="widget-body">
      <a href="/movietalk/1">
        <span class="title-text">'왕과 사는 남자' 관객 반응</span>
        <span class="summary">재밌다는 반응과 CG 아쉽다는 의견이 같이 있습니다.</span>
        <span class="meta"><span class="date">1시간 전</span></span>
      </a>
    </div>
    """

    reactions = parse_extmovie_community_cards(html)

    assert len(reactions) == 1
    assert reactions[0].source == "익스트림무비"
    assert reactions[0].excerpt.startswith("재밌다는")
    assert reactions[0].content_kind == "community"


def test_summarize_reaction_mood_detects_mixed_sentiment():
    summary = summarize_reaction_mood("재밌다 좋다 아쉽다 별로다 기대된다")

    assert "호불호" in summary
```

- [ ] **Step 2: Run failing community tests**

Run: `python -m pytest tests/test_community.py -q`

Expected: fail because `crawler.community` does not exist.

- [ ] **Step 3: Implement community collector**

Create `crawler/community.py`:

- `CommunitySource` protocol with `name` and `fetch()`.
- `ExtMovieCommunitySource.fetch()` using the same polite `httpx` pattern as `ExtMovieSource`.
- `parse_extmovie_community_cards(html: str) -> list[CommunityReaction]`.
- `summarize_reaction_mood(text: str) -> str` using deterministic Korean keyword buckets:
  - positive: `재밌`, `좋`, `기대`, `호평`, `추천`
  - negative: `아쉽`, `별로`, `혹평`, `실망`, `걱정`
  - mixed output when both appear.
- `fetch_community_reactions() -> list[CommunityReaction]`.
- `save_community_reactions(reactions, path)`.

For DC/Theqoo/X expansion, add a config-driven class `ConfiguredCommunityListSource` that accepts `name`, `list_url`, `item_selector`, `title_selector`, `summary_selector`, and `link_selector`. Wire no private/authenticated source by default.

- [ ] **Step 4: Wire community artifact in `crawler/main.py`**

Add paths:

```python
COMMUNITY_PATH = DATA_DIR / "community.json"
```

Call `fetch_community_reactions()` after official articles are saved, then save `data/community.json`.

- [ ] **Step 5: Run community tests**

Run: `python -m pytest tests/test_community.py -q`

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add crawler/community.py crawler/main.py tests/test_community.py
git commit -m "Add community reaction collection"
```

---

### Task 5: Policy And Support Notice Collection

**Files:**
- Create: `crawler/policies.py`
- Modify: `crawler/main.py`
- Test: `tests/test_policies.py`

- [ ] **Step 1: Write failing policy parser tests**

Create `tests/test_policies.py`:

```python
from crawler.policies import parse_kofic_business_notices, policy_relevance_summary


def test_parse_kofic_business_notices_extracts_recent_film_support_items():
    html = """
    <table>
      <tr><th>번호</th><th>분류</th><th>제목</th><th>작성일자</th></tr>
      <tr>
        <td>1</td><td>공고</td>
        <td><a href="/kofic/business/prom/promotionBoardDetail.do?seqNo=17677">2026년 독립예술영화 제작지원 사업 공고</a></td>
        <td>2026.05.14</td>
      </tr>
    </table>
    """

    items = parse_kofic_business_notices(html)

    assert len(items) == 1
    assert items[0].source == "영화진흥위원회"
    assert items[0].category == "공고"
    assert "제작지원" in items[0].title


def test_policy_relevance_summary_marks_support_program():
    assert policy_relevance_summary("2026년 국민 영화관람 활성화 지원사업 공고") == "영화 지원사업"
```

- [ ] **Step 2: Run failing policy tests**

Run: `python -m pytest tests/test_policies.py -q`

Expected: fail because `crawler.policies` does not exist.

- [ ] **Step 3: Implement policy collector**

Create `crawler/policies.py`:

- `KOFIC_BUSINESS_NOTICE_URL` pointing to the business notice list.
- `MCST_POLICY_SEARCH_URL` or search/list endpoint for film policy pages.
- `parse_kofic_business_notices(html: str) -> list[PolicyItem]`.
- `policy_relevance_summary(title: str) -> str`.
- `fetch_policy_items() -> list[PolicyItem]`.
- `save_policy_items(items, path)`.

Filter for Korean terms: `영화`, `제작지원`, `관람`, `할인권`, `독립예술영화`, `국제공동제작`, `상영`, `배급`, `콘텐츠`.

- [ ] **Step 4: Wire policy artifact in `crawler/main.py`**

Add:

```python
POLICIES_PATH = DATA_DIR / "policies.json"
```

Call `fetch_policy_items()` and save `data/policies.json`. A fetch failure must print a warning and save an empty list.

- [ ] **Step 5: Run policy tests**

Run: `python -m pytest tests/test_policies.py -q`

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add crawler/policies.py crawler/main.py tests/test_policies.py
git commit -m "Add film policy collection"
```

---

### Task 6: Pipeline Orchestration And Graceful Artifacts

**Files:**
- Modify: `crawler/main.py`
- Test: `tests/test_pipeline_artifacts.py`

- [ ] **Step 1: Write failing artifact save tests**

Create `tests/test_pipeline_artifacts.py`:

```python
import json
from pathlib import Path

from crawler.main import save_json_items


def test_save_json_items_creates_parent_and_writes_utf8(tmp_path):
    path = tmp_path / "data" / "community.json"

    save_json_items([{"title": "왕과 사는 남자"}], path)

    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "왕과 사는 남자"
```

- [ ] **Step 2: Run failing artifact tests**

Run: `python -m pytest tests/test_pipeline_artifacts.py -q`

Expected: fail because `save_json_items` does not exist.

- [ ] **Step 3: Refactor JSON saving**

Modify `crawler/main.py`:

- Add reusable `save_json_items(items: list[dict], path: Path)`.
- Keep `save_articles()` but make it call `save_json_items([a.to_dict() for a in articles], ARTICLES_PATH)`.
- Add `load_optional_market()` for scoring input if KOBIS fails.
- Make all side artifacts non-fatal.

- [ ] **Step 4: Run artifact tests**

Run: `python -m pytest tests/test_pipeline_artifacts.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add crawler/main.py tests/test_pipeline_artifacts.py
git commit -m "Save briefing artifacts in pipeline"
```

---

### Task 7: Static Dashboard Build

**Files:**
- Modify: `site/build.py`
- Replace: `site/template.html.j2`
- Replace: `site/style.css`
- Test: `tests/test_site_build.py`

- [ ] **Step 1: Write failing site build tests**

Create `tests/test_site_build.py`:

```python
from site.build import split_articles_by_kind, top_curation_items


def test_split_articles_by_kind_separates_official_and_community():
    views = [
        {"content_kind": "official", "title": "공식"},
        {"content_kind": "community", "title": "커뮤니티"},
    ]

    official, community = split_articles_by_kind(views)

    assert official[0]["title"] == "공식"
    assert community[0]["title"] == "커뮤니티"


def test_top_curation_items_limits_to_five_score_order():
    views = [{"title": str(i), "score": i} for i in range(10)]

    result = top_curation_items(views)

    assert [item["title"] for item in result] == ["9", "8", "7", "6", "5"]
```

- [ ] **Step 2: Run failing site tests**

Run: `python -m pytest tests/test_site_build.py -q`

Expected: fail because helper functions do not exist or `site` import conflicts. If Python imports stdlib `site`, load the file with `importlib.util.spec_from_file_location` in the test.

- [ ] **Step 3: Implement build helpers**

Modify `site/build.py`:

- `load_json(path, fallback)`.
- `split_articles_by_kind(views)`.
- `top_curation_items(official_views, community_views=None, limit=5)`.
- `format_int(value)`.
- Load `market.json`, `community.json`, `policies.json`, `reservation.json`.
- Pass all view data to template.

- [ ] **Step 4: Replace template with A-layout**

Replace `site/template.html.j2` with sections:

- Header/KPI row.
- Core curation.
- Box office top 5.
- Reservation capture card.
- Official article lane.
- Community reaction lane.
- Policy/support lane.
- Existing language toggle for official article text where available.

- [ ] **Step 5: Replace CSS**

Replace `site/style.css` with compact desktop dashboard styles and mobile fallback. Keep card border radius at 8px or less.

- [ ] **Step 6: Run site tests**

Run: `python -m pytest tests/test_site_build.py -q`

Expected: pass.

- [ ] **Step 7: Build static site with sample artifacts**

Run: `python site/build.py`

Expected: prints `Built ...` and `dist/index.html` includes the text `커뮤니티 반응`, `전일 관객 TOP 5`, and `정책/지원`.

- [ ] **Step 8: Commit**

Run:

```bash
git add site/build.py site/template.html.j2 site/style.css dist/index.html tests/test_site_build.py
git commit -m "Render briefing dashboard"
```

---

### Task 8: Documentation And Local Verification

**Files:**
- Modify: `README.md`
- Modify: `run.bat`
- Test: command verification

- [ ] **Step 1: Update README**

Add sections for:

- `KOBIS_API_KEY` setup.
- GitHub Actions secret setup.
- Optional Playwright installation.
- New output artifacts: `data/market.json`, `data/community.json`, `data/policies.json`, `data/reservation.json`, and screenshot image path.

- [ ] **Step 2: Update `run.bat`**

Add comments:

```bat
REM Required for KOBIS box office:
REM set KOBIS_API_KEY=your-kobis-key
```

Keep the actual key out of the file.

- [ ] **Step 3: Run full relevant tests**

Run: `python -m pytest tests -q`

Expected: all tests pass.

- [ ] **Step 4: Run build without secrets**

Run: `python site/build.py`

Expected: build succeeds with fallback/missing states.

- [ ] **Step 5: Secret scan**

Run: `rg -n "3ac5e|90d82a|7227e2b8" .`

Expected: no matches.

- [ ] **Step 6: Commit**

Run:

```bash
git add README.md run.bat dist/index.html
git commit -m "Document briefing dashboard setup"
```

---

## Self-Review Checklist

- Spec coverage:
  - One-screen A dashboard: Task 7.
  - Official/community separation: Tasks 1, 4, 7.
  - KOBIS top 5: Task 2.
  - KOBIS reservation-rate screenshot: Task 2.
  - Box-office weighted curation: Task 3.
  - Government support policy: Task 5.
  - Community expansion with body/comment mood: Task 4.
  - Crawl4AI-style fallback: Task 2 screenshot plus Task 4 config-driven browser fallback hook.
  - Secret safety: Tasks 2 and 8.
- Placeholder scan: no unfinished placeholder steps are intentionally left.
- Type consistency:
  - `Article.content_kind` is defined in Task 1 and consumed in Tasks 3 and 7.
  - `MarketSnapshot` is defined in Task 1 and consumed in Tasks 2 and 3.
  - `CommunityReaction` is defined in Task 1 and consumed in Task 4 and Task 7.
  - `PolicyItem` is defined in Task 1 and consumed in Task 5 and Task 7.
