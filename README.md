# 영화 뉴스 크롤러

내부용 영화/문화 이슈 집계 사이트. 매일 KST 08:00에 공식 기사, 커뮤니티 반응,
KOBIS 박스오피스, 실시간 예매율 캡처, 영화/문화 정책 지원 공지를 자동 수집해
정적 HTML 대시보드를 생성합니다.

수집 매체: Variety, The Hollywood Reporter, Deadline, IndieWire, Rolling Stone (US, RSS) · 씨네21, 맥스무비 (KR, 스크래핑).
커뮤니티 반응은 공식 기사와 분리해 `data/community.json`에 저장하며, 익스트림무비를 시작점으로 공개 커뮤니티 소스를 확장할 수 있습니다.

## 설치

### uv (권장)

```bash
cd movie-news
uv sync
```

### pip (uv가 없을 때)

```bash
cd movie-news
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .
```

KOBIS 실시간 예매율 캡처를 사용하려면 Playwright 브라우저를 한 번 설치합니다.

```bash
python -m playwright install chromium
```

## 동작 확인

```bash
python -c "import feedparser, httpx, selectolax, jinja2, rapidfuzz, anthropic, yaml, playwright; print('OK')"
```

## 로컬 실행

```bash
# 1. 공식 기사/커뮤니티/정책/KOBIS 수집 → 점수 → 중복제거 → data/*.json
python -m crawler.main

# 2. 정적 대시보드 생성 → dist/index.html
python site/build.py
```

> `site`는 파이썬 표준 라이브러리 모듈명과 겹치므로 `python -m site.build`는 동작하지 않습니다.
> 사이트 빌드는 항상 `python site/build.py`로 실행하세요.

### 번역 (선택)

영문 기사의 한국어 번역에는 Anthropic API 키가 필요합니다. 환경 변수 `ANTHROPIC_API_KEY`가
설정돼 있으면 번역이 수행되고, 없으면 번역 단계만 건너뜁니다(나머지 파이프라인은 정상 동작).

```bash
# macOS / Linux
export ANTHROPIC_API_KEY=sk-...
# Windows PowerShell
$env:ANTHROPIC_API_KEY="sk-..."

python -m crawler.main
```

번역 결과는 `data/translations.json`에 캐싱되어, 다음 실행 때는 새 기사만 번역합니다.

### KOBIS 박스오피스/예매율

전일 관객 수 TOP 5는 KOBIS Open API를 사용합니다. API 키는 코드에 넣지 말고
환경 변수 `KOBIS_API_KEY`로 설정하세요.

```bash
# macOS / Linux
export KOBIS_API_KEY=...
# Windows PowerShell
$env:KOBIS_API_KEY="..."
```

실시간 예매율은 KOBIS 공개 페이지를 빌드/업로드 시점에 브라우저로 캡처합니다.
브라우저 캡처가 실패해도 빌드는 실패하지 않고, 대시보드에는 캡처 불가 상태가 표시됩니다.

생성되는 주요 데이터 파일:

- `data/articles.json`: 공식 기사
- `data/market.json`: KOBIS 전일 관객 TOP 5
- `data/reservation.json`: 실시간 예매율 캡처 메타데이터
- `data/assets/`: 실시간 예매율 캡처 이미지
- `data/community.json`: 커뮤니티 반응과 분위기 요약
- `data/policies.json`: 영진위/문체부 영화·문화 지원 정책 공지

## 결과 보기

`dist/index.html`을 브라우저로 직접 열거나, 로컬 서버로 확인합니다.

```bash
python -m http.server -d dist
# http://localhost:8000 접속
```

우상단 `[원문] [한국어]` 토글로 언어를 전환할 수 있습니다.

## 자동화 (GitHub Actions)

`.github/workflows/daily.yml`이 매일 KST 08:00(UTC 23:00)에 크롤링·빌드를 실행하고,
변경이 있으면 `dist/`와 `data/`를 커밋·푸시합니다. Actions 탭의 **Run workflow** 버튼으로
수동 실행도 가능합니다.

### ANTHROPIC_API_KEY 등록

번역을 사용하려면 레포지토리에 시크릿을 등록하세요:

1. GitHub 레포지토리 → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭
3. Name: `ANTHROPIC_API_KEY`, Secret: 발급받은 키 입력 후 저장

시크릿이 없으면 워크플로우는 실패하지 않고 번역만 건너뜁니다.

### KOBIS_API_KEY 등록

KOBIS 박스오피스 API를 사용하려면 레포지토리에 시크릿을 등록하세요:

1. GitHub 레포지토리 → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭
3. Name: `KOBIS_API_KEY`, Secret: 발급받은 KOBIS 키 입력 후 저장

시크릿이 없으면 워크플로우는 실패하지 않고 기존 캐시 또는 빈 박스오피스 상태로 빌드됩니다.

### (선택) GitHub Pages

`dist/index.html`을 GitHub Pages로 공개하려면 **Settings → Pages**에서 브랜치와
`/` 또는 `/docs` 경로를 지정하세요. 단, **비공개(private) 레포지토리에서 Pages를
사용하려면 유료 플랜이 필요**합니다. 사내용으로만 쓴다면 생성된 `dist/index.html`을
브라우저로 직접 여는 방식으로 충분합니다.
