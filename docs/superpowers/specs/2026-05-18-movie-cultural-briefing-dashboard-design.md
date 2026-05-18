# Movie/Culture Briefing Dashboard Design

Date: 2026-05-18
Status: Approved direction for implementation planning

## Goal

Build on the current Movie-News project to create an internal briefing page where company employees can quickly check major film and culture-industry issues.

The page must:

- Show the key situation at a glance on one screen.
- Separate official articles from community reactions.
- Show yesterday's KOBIS audience-count top 5.
- Show the live KOBIS reservation-rate TOP 5 as structured data at upload/build time.
- Weight article curation by the KOBIS box office top 5.
- Include government/public support-policy updates, especially film support programs.
- Expand community coverage beyond the current film-community source and summarize body/comment sentiment when available.

## Chosen Product Direction

Use the A layout from the mockup: an executive briefing dashboard.

The first screen is a single "today's film/culture radar" view. It starts with four compact indicators:

- Yesterday's box office #1.
- Live reservation-rate #1.
- Official article count.
- Community reaction count.

Below those indicators, the page separates five sections:

1. Core curation.
2. Yesterday audience top 5 and live reservation-rate TOP 5.
3. Official articles.
4. Community reactions.
5. Government/public support policies.

Official articles and community reactions remain visually separate. The core curation section can connect them under the same issue, but must preserve source labels.

Mockup: `docs/superpowers/mockups/dashboard-layout-options.html`

## Data Sources

### Existing Official/Media Sources

Keep the current crawler sources as the official/media feed:

- Variety
- The Hollywood Reporter
- Deadline
- IndieWire
- Rolling Stone
- Cine21
- MaxMovie
- Existing Korean movie news sources that are editorial/news-like

These items should be typed as official/media content, not community content.

### Community Sources

Use a separate community source group.

Initial source:

- Extreme Movie community-style posts, where already available.

Expansion targets:

- DCInside
- Theqoo
- X/public social posts where technically and legally practical
- Other public film/community pages that can be parsed reliably

Community cards should include:

- Source.
- Title.
- URL.
- Published or crawled time.
- Short body excerpt.
- Reaction/comment mood summary when comments or reply-like text are available.
- Matched movie/person/distributor keywords.

Community content must be labeled as community reaction and must not be mixed into the official article list.

### KOBIS Box Office

Use KOBIS Open API for yesterday's daily box office:

- Endpoint family: `kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList`
- Key handling: read from `KOBIS_API_KEY`; do not commit the user's key.
- Target date: yesterday in KST, formatted as `YYYYMMDD`.
- Store the top 5 audience-count list under a separate market-data artifact.

Fields needed:

- Rank.
- Movie code.
- Korean title.
- Opening date if provided.
- Daily audience count.
- Cumulative audience count.
- Rank change where available.

### KOBIS Live Reservation Rate

At build/upload time, read the public KOBIS live reservation-rate page as structured data:

- Page: KOBIS mobile/PC live reservation-rate view.
- Store the TOP 5 list with rank, Korean title, reservation rate, and reservation audience count.
- Show the list in the dashboard with the same visual treatment as the previous-day audience TOP 5.

If reservation-rate fetch fails, the page should still build. It should display a clear missing-data state.

### Policy/Support Updates

Add a separate policy feed for public support programs and policy updates:

- KOFIC business notices.
- MCST film/culture policy and press releases.
- Film-support categories such as production support, distribution/exhibition support, independent/art film support, international co-production, discount-ticket programs, and public funding announcements.

Policy items should include:

- Agency/source.
- Category: notice, application, result, press/policy.
- Title.
- Date.
- URL.
- Short summary.
- Deadline/application period if discoverable.

## Curation And Scoring

Keep the current distributor/recency scoring, then add market and community signals.

Recommended scoring components:

- Existing tier keyword score for Lotte, Paramount, and distributors.
- Recency score.
- KOBIS box-office match score:
  - Rank 1 gets the strongest boost.
  - Ranks 2-5 get descending boosts.
  - Match by exact movie title first, then normalized title aliases when available.
- Community trend score:
  - More conservative than official/media score.
  - Based on matched title/person keywords, comment/reply count if available, and repeated sentiment keywords.
- Policy relevance score:
  - Film-specific government support and active application notices rank above general culture policy.

The dashboard should not imply that community reaction is verified fact. Community summaries are audience-signal context only.

## Crawling Reliability Strategy

Keep the current lightweight approach as the first path:

1. RSS or HTTP fetch with `httpx`.
2. Static HTML parsing with `selectolax`.
3. Source-specific parser.

When a target is JavaScript-rendered, intermittently blocked, or returns empty/low-value HTML, use a Crawl4AI-inspired browser fallback:

1. Browser render with Crawl4AI-style configuration when a source explicitly needs it.
2. Site-specific `wait_for` or scroll/click actions.
3. Optional debug artifact capture only for crawler diagnostics, not for KOBIS reservation-rate display.
4. Retry/anti-bot detection where appropriate.
5. Mark source as failed with an error record rather than breaking the whole build.

Fallback crawling should be opt-in by source so the daily run stays fast and stable.

## Site Build And UX

The project remains a static HTML generator.

The build process should load:

- `data/articles.json`
- `data/market.json` or equivalent KOBIS artifact
- `data/community.json` or equivalent community artifact
- `data/policies.json` or equivalent policy artifact
- reservation-rate TOP 5 metadata

The generated page should be mobile-readable but optimized for a desktop internal briefing screen.

Dashboard layout:

- Header with update time.
- Top KPI row.
- Main two-column briefing area:
  - Left: core curation.
  - Right: box office top 5 and reservation-rate TOP 5.
- Below: side-by-side official articles and community reactions.
- Bottom or right rail: policy/support updates.

## Error Handling

The daily workflow must not fail just because one source fails.

Rules:

- KOBIS API failure: show last successful box-office data if available; otherwise show a missing-data card.
- Reservation-rate fetch failure: show unavailable state.
- Community source failure: omit that source and record a warning.
- Policy feed failure: omit failed source and record a warning.
- Translation failure: keep original text and keep the build successful.

## Configuration And Secrets

Add environment variables:

- `KOBIS_API_KEY`: required for daily box-office API calls.
- Optional crawler toggles for browser fallback and community expansion.

GitHub Actions should receive `KOBIS_API_KEY` as a repository secret.

The actual API key must not be committed in code, docs, generated JSON, or logs.

## Testing And Verification

Add focused tests around:

- KOBIS response parsing and top-5 extraction.
- Target-date calculation in KST.
- Article score boost when a title matches KOBIS top 5.
- Official/community separation in transformed view data.
- Policy notice parsing for representative HTML.
- Build behavior when market/community/policy artifacts are missing.

Manual verification:

- Run the crawler/build locally with a test or real KOBIS key in the environment.
- Confirm the generated page shows all required sections.
- Confirm the reservation-rate TOP 5 appears or degrades gracefully.
- Confirm no API key appears in git diff or generated output.

## Implementation Sequence

1. Add data models for market data, community reactions, policies, and crawl diagnostics.
2. Add KOBIS daily box-office client and saved market artifact.
3. Add KOBIS reservation-rate TOP 5 collection.
4. Split article/community/policy source types.
5. Add community expansion framework and first expanded parser.
6. Add policy feed parser.
7. Extend scoring with KOBIS and community signals.
8. Rebuild the static dashboard template and CSS around the A layout.
9. Update GitHub Actions secrets documentation and workflow steps.
10. Add tests and run local verification.

## Open Constraints

- Some community sites may block crawling or forbid automated scraping. Each source must be added only after checking practical access and robots/terms constraints.
- X/social sources may require authentication or API access; they should be treated as optional expansion, not a required launch dependency.
- Comment/reaction summaries must be concise and clearly labeled as community sentiment, not factual reporting.
