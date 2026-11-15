import base64
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from io import BytesIO

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from pdf2image import convert_from_path
from PIL import Image
from werkzeug.exceptions import RequestEntityTooLarge

# The largest PDF accepted, in MB (the whiteboard refuses larger files before
# uploading them; this is the server's own check).
MAX_PDF_MB = int(os.environ.get("MAX_PDF_MB", "30"))
MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024

# Pages are rendered at DPI unless that would make an image larger than
# MAX_PAGE_PIXELS (a 4xA0 sheet at 200 dpi is ~248 M pixels): such a page is
# rendered at the highest resolution that stays under it.
DPI = 200
MAX_PAGE_PIXELS = int(os.environ.get("MAX_PAGE_PIXELS", "64000000"))

app = Flask(__name__)
# room for the multipart wrapping around a PDF of exactly the limit
app.config["MAX_CONTENT_LENGTH"] = MAX_PDF_BYTES + 1024 * 1024
CORS(app)


def too_large():
    return (
        jsonify(
            {
                "error": f"PDF is too large: the limit is {MAX_PDF_MB} MB",
                "max_mb": MAX_PDF_MB,
            }
        ),
        413,
    )


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return too_large()


def page_sizes(path):
    """each page's size in inches, from pdfinfo; ValueError if it is no PDF"""
    info = subprocess.run(
        ["pdfinfo", "-f", "1", "-l", "100000", path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if info.returncode != 0:
        raise ValueError("The file is not a readable PDF")
    sizes = {}
    for line in info.stdout.splitlines():
        m = re.match(r"Page\s+(\d+) size:\s+([\d.]+) x ([\d.]+) pts", line)
        if m:
            sizes[int(m.group(1))] = (float(m.group(2)) / 72, float(m.group(3)) / 72)
    if not sizes:
        raise ValueError("The PDF has no pages")
    return [sizes[n] for n in sorted(sizes)]


def page_dpi(width_in, height_in):
    """DPI, or less where a page would otherwise exceed MAX_PAGE_PIXELS"""
    area = width_in * height_in
    if area <= 0 or area * DPI * DPI <= MAX_PAGE_PIXELS:
        return DPI
    return max(1, math.floor(math.sqrt(MAX_PAGE_PIXELS / area)))


def render_page(path, page, dpi):
    return convert_from_path(path, dpi=dpi, first_page=page, last_page=page)[0]


# a page may be rendered right up to MAX_PAGE_PIXELS
Image.MAX_IMAGE_PIXELS = max(Image.MAX_IMAGE_PIXELS or 0, MAX_PAGE_PIXELS * 2)


@app.route("/convert", methods=["POST"])
def convert_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    pdf_file = request.files["file"]
    if pdf_file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    workdir = tempfile.mkdtemp(prefix="pdf-")
    path = os.path.join(workdir, "in.pdf")
    try:
        pdf_file.save(path)
        if os.path.getsize(path) > MAX_PDF_BYTES:
            shutil.rmtree(workdir, ignore_errors=True)
            return too_large()
        sizes = page_sizes(path)
    except ValueError as e:
        shutil.rmtree(workdir, ignore_errors=True)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500

    def pages():
        # One page at a time, each sent as soon as it is ready: memory stays at
        # one page, and the proxy sees data well within its read timeout even
        # when the whole document takes minutes. A failure after the first
        # bytes can no longer change the status, so it ends the JSON with
        # an "error" next to the pages already sent.
        yield '{"files":['
        try:
            for index, (w, h) in enumerate(sizes):
                image = render_page(path, index + 1, page_dpi(w, h))
                out = BytesIO()
                image.save(out, "PNG")
                image.close()
                item = json.dumps(
                    {
                        "filename": f"page-{index + 1}.png",
                        "content_type": "image/png",
                        "data": base64.b64encode(out.getvalue()).decode("ascii"),
                    }
                )
                yield ("," if index else "") + item
            yield "]}"
        except Exception as e:
            yield "]," + json.dumps({"error": str(e)})[1:]
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    response = Response(pages(), mimetype="application/json")
    # also when the client goes away before the last page
    response.call_on_close(lambda: shutil.rmtree(workdir, ignore_errors=True))
    return response


@app.route("/health", methods=["GET"])
def health():
    poppler_ok = shutil.which("pdftoppm") is not None
    body = {
        "status": "ok" if poppler_ok else "degraded",
        "poppler": poppler_ok,
        "service": "pdf-to-image",
    }
    return jsonify(body), (200 if poppler_ok else 503)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
