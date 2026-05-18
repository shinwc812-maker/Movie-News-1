import json

from crawler.main import save_json_items


def test_save_json_items_creates_parent_and_writes_utf8(tmp_path):
    path = tmp_path / "data" / "community.json"

    save_json_items([{"title": "왕과 사는 남자"}], path)

    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "왕과 사는 남자"
