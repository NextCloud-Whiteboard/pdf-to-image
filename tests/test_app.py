import base64
import io
import json

import pytest
from PIL import Image

import app as converter


def make_pdf(pages):
    """a PDF with one page per (width_in, height_in), drawn as tiny images"""
    images = [
        # 10 px per inch: the page size comes from the resolution
        Image.new("RGB", (int(w * 10), int(h * 10)), "white")
        for w, h in pages
    ]
    out = io.BytesIO()
    images[0].save(out, "PDF", resolution=10, save_all=True, append_images=images[1:])
    return out.getvalue()


@pytest.fixture
def client():
    converter.app.config["TESTING"] = True
    return converter.app.test_client()


def post(client, data, name="plan.pdf"):
    return client.post(
        "/convert",
        data={"file": (io.BytesIO(data), name)},
        content_type="multipart/form-data",
        headers={"Origin": "http://example.test"},
    )


def page_sizes(body):
    sizes = []
    for f in body["files"]:
        img = Image.open(io.BytesIO(base64.b64decode(f["data"])))
        sizes.append(img.size)
    return sizes


def test_converts_every_page_in_order(client):
    res = post(client, make_pdf([(2, 1), (1, 2), (3, 3)]))
    assert res.status_code == 200
    body = json.loads(res.get_data(as_text=True))
    assert [f["filename"] for f in body["files"]] == ["page-1.png", "page-2.png", "page-3.png"]
    assert "error" not in body
    # 200 dpi
    assert page_sizes(body) == [(400, 200), (200, 400), (600, 600)]


def test_refuses_a_pdf_over_the_limit_with_413(client, monkeypatch):
    monkeypatch.setattr(converter, "MAX_PDF_BYTES", 1000)
    res = post(client, make_pdf([(2, 1)]) + b"\0" * 2000)
    assert res.status_code == 413
    body = res.get_json()
    assert body["max_mb"] == converter.MAX_PDF_MB
    assert "30 MB" in body["error"] or str(converter.MAX_PDF_MB) in body["error"]
    # the browser must be allowed to read why
    assert res.headers.get("Access-Control-Allow-Origin")


def test_refuses_a_request_body_far_over_the_limit(client, monkeypatch):
    monkeypatch.setitem(converter.app.config, "MAX_CONTENT_LENGTH", 1000)
    res = post(client, b"%PDF" + b"\0" * 5000)
    assert res.status_code == 413
    assert res.get_json()["max_mb"] == converter.MAX_PDF_MB
    assert res.headers.get("Access-Control-Allow-Origin")


def test_the_limit_is_30_mb_by_default():
    assert converter.MAX_PDF_MB == 30
    assert converter.MAX_PDF_BYTES == 30 * 1024 * 1024


def test_lowers_the_resolution_of_a_page_too_big_for_full_resolution(client, monkeypatch):
    # 10 x 10 in at 200 dpi is 4 M pixels; allow 1 M
    monkeypatch.setattr(converter, "MAX_PAGE_PIXELS", 1_000_000)
    body = json.loads(post(client, make_pdf([(10, 10), (2, 2)])).get_data(as_text=True))
    (w1, h1), (w2, h2) = page_sizes(body)
    assert w1 * h1 <= 1_000_000 and w1 >= 990
    # the small page keeps full resolution
    assert (w2, h2) == (400, 400)


def test_says_why_a_file_is_not_a_pdf(client):
    res = post(client, b"not a pdf at all")
    assert res.status_code == 400
    assert res.get_json()["error"]


def test_reports_a_failure_halfway_in_the_json(client, monkeypatch):
    real = converter.render_page

    def failing(path, page, dpi):
        if page == 2:
            raise RuntimeError("page 2 is broken")
        return real(path, page, dpi)

    monkeypatch.setattr(converter, "render_page", failing)
    body = json.loads(post(client, make_pdf([(1, 1), (1, 1)])).get_data(as_text=True))
    assert len(body["files"]) == 1
    assert "page 2 is broken" in body["error"]


def test_still_requires_a_file(client):
    res = client.post("/convert", data={}, content_type="multipart/form-data")
    assert res.status_code == 400
