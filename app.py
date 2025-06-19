from flask import Flask, request, send_file, jsonify
from pdf2image import convert_from_bytes
from io import BytesIO
from flask_cors import CORS

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
        images = convert_from_bytes(pdf_file.read(), first_page=1, last_page=1)
        img_io = BytesIO()
        images[0].save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
