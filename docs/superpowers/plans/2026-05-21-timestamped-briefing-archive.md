# Timestamped Briefing Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve each generated briefing as a timestamped archive while keeping `dist/index.html` as the latest briefing.

**Architecture:** Add a small archive writer in `site/build.py` that receives rendered HTML, the build timestamp, and source data paths. The writer stores `dist/archive/YYYY-MM-DD/HHmmss/index.html` and copies current JSON inputs into `data/archive/YYYY-MM-DD/HHmmss/`; if the same second already exists, it appends `-02`, `-03`, and so on.

**Tech Stack:** Python, pathlib, pytest, existing static Jinja build pipeline.

---

### Task 1: Archive Writer

**Files:**
- Modify: `site/build.py`
- Test: `tests/test_site_build.py`

- [ ] **Step 1: Write the failing test**

```python
def test_write_archive_snapshot_uses_kst_timestamp_and_copies_current_data(tmp_path):
    build = load_site_build_module()
    data_dir = tmp_path / "data"
    dist_dir = tmp_path / "dist"
    data_dir.mkdir()
    articles = data_dir / "articles.json"
    community = data_dir / "community.json"
    articles.write_text('[{"title":"오늘 기사"}]', encoding="utf-8")
    community.write_text('[{"title":"오늘 반응"}]', encoding="utf-8")
    now = build.datetime(2026, 5, 21, 1, 2, 3, tzinfo=build.timezone.utc)

    archive = build.write_archive_snapshot(
        "<html>today</html>\n",
        now,
        data_paths=[articles, community, data_dir / "missing.json"],
        dist_dir=dist_dir,
        data_dir=data_dir,
    )

    assert archive["html_path"] == dist_dir / "archive" / "2026-05-21" / "100203" / "index.html"
    assert archive["data_dir"] == data_dir / "archive" / "2026-05-21" / "100203"
    assert archive["html_path"].read_text(encoding="utf-8") == "<html>today</html>\n"
    assert (archive["data_dir"] / "articles.json").read_text(encoding="utf-8") == '[{"title":"오늘 기사"}]'
    assert (archive["data_dir"] / "community.json").read_text(encoding="utf-8") == '[{"title":"오늘 반응"}]'
    assert not (archive["data_dir"] / "missing.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests\test_site_build.py::test_write_archive_snapshot_uses_kst_timestamp_and_copies_current_data -q`

Expected: FAIL with `AttributeError` for missing `write_archive_snapshot`.

- [ ] **Step 3: Implement minimal archive writer**

Add `DATA_SNAPSHOT_PATHS`, `archive_timestamp_path()`, `next_archive_path()`, and `write_archive_snapshot()` to `site/build.py`. Call `write_archive_snapshot(html, now)` after writing latest `dist/index.html`.

- [ ] **Step 4: Run targeted and full tests**

Run: `python -m pytest tests\test_site_build.py::test_write_archive_snapshot_uses_kst_timestamp_and_copies_current_data -q`

Run: `python -m pytest tests -q`

- [ ] **Step 5: Generate today's briefing**

Run the crawler with KOBIS, Naver, and YouTube environment variables, then run `python site\build.py`. Confirm latest and archived paths exist.

- [ ] **Step 6: Commit and push**

Run `git add .`, `git commit -m "Archive timestamped briefing builds"`, and `git push`.
