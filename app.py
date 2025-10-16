from flask import Flask, request, send_file, jsonify
from pdf2image import convert_from_bytes
from io import BytesIO
from flask_cors import CORS
import base64

app = Flask(__name__)
CORS(app)

@app.route("/convert", methods=["POST"])
def convert_pdf():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    pdf_file = request.files['file']
    if pdf_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        # Convert all pages of the PDF to images (default: all pages)
        images = convert_from_bytes(pdf_file.read())

        files = []
        for index, image in enumerate(images):
            image_bytes_io = BytesIO()
            image.save(image_bytes_io, 'PNG')
            image_bytes_io.seek(0)

            encoded_image = base64.b64encode(image_bytes_io.getvalue()).decode('utf-8')
            files.append({
                "filename": f"page-{index + 1}.png",
                "content_type": "image/png",
                "data": encoded_image
            })

        return jsonify({"files": files}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
