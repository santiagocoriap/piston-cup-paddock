from django.test import Client


def test_the_app_page_is_never_reused_without_asking_the_server(settings, tmp_path):
    (tmp_path / "index.html").write_text("<script src='/static/assets/index-abc.js'></script>")
    settings.FRONTEND_DIST = tmp_path
    response = Client().get("/some/page")
    assert response.status_code == 200
    assert "no-cache" in response["Cache-Control"]
