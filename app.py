from flask import Flask, request, jsonify, send_file, abort
import os
import random
import string
import time
import zipfile
from werkzeug.utils import secure_filename
from flask_cors import CORS
from datetime import datetime

UPLOAD_FOLDER = 'uploads'
EXPIRY_SECONDS = 86400  # 24 hours

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
file_records = {}
admin_secret = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
print(f"[ADMIN ACCESS CODE]: {admin_secret}")  # Only printed on server start

def generate_code(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def timestamp():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

def timestamp_from_now(seconds):
    return datetime.utcfromtimestamp(time.time() + seconds).strftime('%Y-%m-%d %H:%M:%S UTC')

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
        if file.filename == '':
            continue
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{code}_{filename}")
        file.save(save_path)
        saved_paths.append(save_path)

    file_records[code] = {
        'paths': saved_paths,
        'timestamp': time.time(),
        'created_at': timestamp(),
        'expires_at': timestamp_from_now(EXPIRY_SECONDS),
        'downloads': [],
        'delete_after': delete_after_download
    }

    return jsonify({'code': code})

@app.route('/retrieve/<code>', methods=['GET'])
def retrieve_file(code):
    cleanup_expired()
    if code not in file_records:
        abort(404)

    record = file_records[code]
    paths = record['paths']
    delete_after = record['delete_after']
    record['downloads'].append(timestamp())

    if len(paths) == 1:
        original_filename = os.path.basename(paths[0]).replace(f"{code}_", "")
        response = send_file(paths[0], as_attachment=True, download_name=original_filename)
    else:
        zip_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{code}_bundle.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for path in paths:
                zipf.write(path, os.path.basename(path))
        response = send_file(zip_path, as_attachment=True)

    if delete_after:
        delete_files(code)

    return response

@app.route('/log/<code>', methods=['GET'])
def get_log(code):
    admin_token = request.args.get('admin')
    if admin_token != admin_secret:
        return jsonify({'error': 'Unauthorized'}), 403

    if code not in file_records:
        return jsonify({'error': 'Code not found'}), 404

    record = file_records[code]
    return jsonify({
        'code': code,
        'created_at': record['created_at'],
        'expires_at': record['expires_at'],
        'downloads': record['downloads'],
        'delete_after_download': record['delete_after']
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

