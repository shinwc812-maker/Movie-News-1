from crawler.sources.cine21 import parse_cine21_news_list


def test_parse_cine21_news_list_excludes_recommended_books():
    html = """
    <ul>
      <li class="list_with_thumb_item_m">
        <a href="/news/view/?mag_id=109962">
          <p class="news_title">씨네21 추천도서 - &lt;꿈의 방&gt;</p>
        </a>
      </li>
      <li class="list_with_thumb_item_m">
        <a href="/news/view/?mag_id=109900">
          <p class="news_title">강동원·엄태구 '와일드 씽' 팬 이벤트 현장</p>
        </a>
      </li>
    </ul>
    """

    results = parse_cine21_news_list(html, "https://www.cine21.com")

    assert results == [
        (
            "https://www.cine21.com/news/view/?mag_id=109900",
            "강동원·엄태구 '와일드 씽' 팬 이벤트 현장",
        )
    ]
