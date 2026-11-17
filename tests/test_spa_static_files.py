"""前端静态服务回归测试：HTML 不缓存，缺失资源与 API 不重写为 HTML。"""

import pytest

NO_STORE = "no-store, no-cache, must-revalidate, max-age=0"


def _client():
    from fastapi.testclient import TestClient

    from backend.app import app

    return TestClient(app)


@pytest.fixture(scope="module")
def frontend_ready():
    from backend.utils.paths import APPLICATION_ROOT

    dist = APPLICATION_ROOT / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        pytest.skip("前端产物未构建")
    return dist


@pytest.mark.parametrize(
    "path",
    ["/", "/index.html", "/login", "/settings", "/settings/model", "/settings/general"],
)
def test_html_documents_are_served_without_cache(frontend_ready, path):
    response = _client().get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == NO_STORE


def test_missing_api_and_assets_are_not_rewritten_to_html(frontend_ready):
    client = _client()

    for path in ["/assets/js/definitely-missing.js", "/assets/css/definitely-missing.css"]:
        response = client.get(path)
        assert response.status_code == 404
        assert not response.headers.get("content-type", "").startswith("text/html")

    response = client.get("/api/definitely-missing")
    assert not response.headers.get("content-type", "").startswith("text/html")


def test_hashed_assets_keep_cacheable(frontend_ready):
    asset = next((frontend_ready / "assets" / "js").glob("*.js"), None)
    if asset is None:
        pytest.skip("产物中没有 JS 分块")

    response = _client().get(f"/assets/js/{asset.name}")

    assert response.status_code == 200
    assert response.headers.get("cache-control") is None
