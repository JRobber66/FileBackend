from flask import Flask, request, jsonify, send_file, abort
import os
import random
import string
import time
import zipfile
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
EXPIRY_SECONDS = 86400  # 24 hours

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
file_records = {}  # Stores: code -> { 'paths': [file1, file2], 'timestamp': upload_time, 'delete_after': True/False }

def generate_code(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def cleanup_expired():
    now = time.time()
    expired = [code for code, record in file_records.items() if now - record['timestamp'] > EXPIRY_SECONDS]
    for code in expired:
        delete_files(code)

def delete_files(code):
    if code in file_records:
        for path in file_records[code]['paths']:
            if os.path.exists(path):
                os.remove(path)
        del file_records[code]

@app.route('/upload', methods=['POST'])
def upload_files():
    cleanup_expired()
    files = request.files.getlist('files')
    delete_after_download = request.form.get('delete_after') == 'true'

    if not files:
        return jsonify({'error': 'No files uploaded'}), 400

    code = generate_code()
    saved_paths = []

    for file in files:
        filename = secure_filename(file.filename)
        save_path = os.path.join(UPLOAD_FOLDER, f"{code}_{filename}")
        file.save(save_path)
        saved_paths.append(save_path)

    file_records[code] = {
        'paths': saved_paths,
        'timestamp': time.time(),
        'delete_after': delete_after_download
    }

    return jsonify({'code': code})

@app.route('/retrieve/<code>', methods=['GET'])
def retrieve_file(code):
    cleanup_expired()

    if code not in file_records:
        abort(404)

    paths = file_records[code]['paths']
    delete_after = file_records[code]['delete_after']

    if len(paths) == 1:
        file_path = paths[0]
        response = send_file(file_path, as_attachment=True)
    else:
        zip_path = os.path.join(UPLOAD_FOLDER, f"{code}_bundle.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for path in paths:
                zipf.write(path, os.path.basename(path))
        response = send_file(zip_path, as_attachment=True)

    if delete_after:
        delete_files(code)

    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
