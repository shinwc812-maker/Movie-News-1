# 영화 뉴스 크롤러

내부용 영화/문화 이슈 집계 사이트. 매일 KST 08:00에 공식 기사, 커뮤니티 반응,
KOBIS 박스오피스, 실시간 예매율 TOP 5, 영화/콘텐츠/문화 정책 지원 공지를 자동 수집해
정적 HTML 대시보드를 생성합니다.

수집 매체: Variety, The Hollywood Reporter, Deadline, IndieWire, Rolling Stone (US, RSS) · 씨네21, 맥스무비 (KR, 스크래핑).
커뮤니티 반응은 공식 기사와 분리해 `data/community.json`에 저장하며, 익스트림무비, 더쿠/디시인사이드 직접 검색, 네이버카페 공개 검색, X 공개 웹 검색, YouTube 검색 API를 사용합니다. 영화명은 `와일드 씽`/`와일드씽`처럼 띄어쓰기 변형까지 함께 검색합니다.

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

## 동작 확인

```bash
python -c "import feedparser, httpx, selectolax, jinja2, rapidfuzz, anthropic, yaml; print('OK')"
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

전일 관객 TOP 5는 관객수, 전일대비 증감, 누적관객수, 개봉일을 저장합니다. 좌석수와 좌점율은
운영 시트의 공개 GViz 응답을 함께 읽어 보강하며, 기본 시트가 바뀌면 `BOXOFFICE_SEAT_METRICS_URL`
환경 변수로 대체 URL을 지정할 수 있습니다. 좌판율은 관객수/좌석수 기준으로 계산합니다.

실시간 예매율은 KOBIS 공개 페이지를 수집 시점에 구조화 데이터로 읽어 TOP 5와 예매율을 표시합니다.
예매율 수집이 실패해도 빌드는 실패하지 않고, 대시보드에는 예매율 데이터 없음 상태가 표시됩니다.

KOBIS 영화 상세 API의 배급사 정보도 함께 조회합니다. 배급사가 `롯데컬처웍스(주)롯데엔터테인먼트`,
`롯데엔터테인먼트`, `Lotte Entertainment`로 확인되는 박스오피스/예매율 TOP 5 작품은 기사 큐레이션과
커뮤니티 검색에서 추가 가중치를 받습니다.

핵심 큐레이션은 공식 기사 중심으로 계산합니다. 박스오피스/예매율 TOP 5 직접 매칭과 국내 기사를 우선하고,
해외 기사는 롯데/파라마운트/박스오피스 직접 관련성이 있을 때만 상단 후보로 남깁니다. `Michael`처럼
인명과 겹치는 짧은 영문 영화명은 따옴표 제목이거나 박스오피스·개봉·예매 문맥이 가까이 있을 때만
영화명으로 인정합니다.

### TMDB 연결 (선택)

TMDB API 키가 있으면 KOBIS 박스오피스/예매율 TOP 5 영화명으로 TMDB 영화 검색을 실행해
`data/market.json`과 `data/reservation.json`에 TMDB ID, 제목, 포스터 경로, 개요, 개봉일
메타데이터를 보강합니다. 키가 없으면 이 단계는 건너뜁니다.

```bash
# macOS / Linux
export TMDB_API_KEY=...

# Windows PowerShell
$env:TMDB_API_KEY="..."
```

### 커뮤니티 확장 검색

익스트림무비, 더쿠, 디시인사이드, 네이버카페, X/Twitter 공개 검색은 별도 키 없이 동작합니다. Naver Search Open API와
YouTube Data API를 함께 사용하면 카페/웹/영상 검색 결과를 더 넓게 보강합니다. 키는 코드에
넣지 말고 환경 변수로 설정하세요.

```bash
# macOS / Linux
export NAVER_CLIENT_ID=...
export NAVER_CLIENT_SECRET=...
export YOUTUBE_API_KEY=...

# Windows PowerShell
$env:NAVER_CLIENT_ID="..."
$env:NAVER_CLIENT_SECRET="..."
$env:YOUTUBE_API_KEY="..."
```

Naver API 인증이 실패해도 공개 검색 fallback은 계속 실행됩니다. 더쿠/디시인사이드는 각 사이트의
공개 검색 결과를 직접 수집하고, X는 로그인 없이 검색엔진에 노출되는 공개 결과만 수집하므로 검색
결과가 막히는 날에는 0건일 수 있습니다.

생성되는 주요 데이터 파일:

- `data/articles.json`: 공식 기사
- `data/market.json`: KOBIS 전일 관객 TOP 5
- `data/reservation.json`: 실시간 예매율 TOP 5
- `data/community.json`: 커뮤니티 반응과 분위기 요약
- `data/policies.json`: 영진위/콘진원/문체부 영화·콘텐츠·문화 지원 정책 공지

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

### 커뮤니티 검색 시크릿 등록

확장 커뮤니티 검색을 사용하려면 필요에 따라 아래 시크릿을 추가하세요:

- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `YOUTUBE_API_KEY`
- `TMDB_API_KEY`

Naver 시크릿이 없거나 인증에 실패해도 익스트림무비, 네이버카페 공개 검색, YouTube 키가 있으면
YouTube 검색은 계속 동작합니다.

### (선택) GitHub Pages

`dist/index.html`을 GitHub Pages로 공개하려면 **Settings → Pages**에서 브랜치와
`/` 또는 `/docs` 경로를 지정하세요. 단, **비공개(private) 레포지토리에서 Pages를
사용하려면 유료 플랜이 필요**합니다. 사내용으로만 쓴다면 생성된 `dist/index.html`을
브라우저로 직접 여는 방식으로 충분합니다.
