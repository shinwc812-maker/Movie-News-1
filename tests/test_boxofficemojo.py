from crawler.boxofficemojo import parse_latest_weekend


def test_parse_latest_weekend_extracts_top_five_from_homepage_text():
    html = """
    <html>
      <body>
        <h2>Latest Weekend: May 15-17</h2>
        <table>
          <tr><td>1</td><td><a href="/release/rl1/">Michael</a></td><td>$26.1M</td></tr>
          <tr><td>2</td><td><a href="/release/rl2/">The Devil Wears Prada 2</a></td><td>$17.9M</td></tr>
          <tr><td>3</td><td><a href="/release/rl3/">Obsession</a></td><td>$17.2M</td></tr>
          <tr><td>4</td><td><a href="/release/rl4/">Mortal Kombat II</a></td><td>$13.4M</td></tr>
          <tr><td>5</td><td><a href="/release/rl5/">The Sheep Detectives</a></td><td>$9.6M</td></tr>
        </table>
      </body>
    </html>
    """

    snapshot = parse_latest_weekend(html, base_url="https://www.boxofficemojo.com/")

    assert snapshot.weekend_label == "May 15-17"
    assert [movie.title for movie in snapshot.movies] == [
        "Michael",
        "The Devil Wears Prada 2",
        "Obsession",
        "Mortal Kombat II",
        "The Sheep Detectives",
    ]
    assert snapshot.movies[0].gross == "$26.1M"
    assert snapshot.movies[0].url == "https://www.boxofficemojo.com/release/rl1/"
