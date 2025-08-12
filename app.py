from flask import Flask, request, jsonify, send_file, abort, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
from datetime import datetime
import os, time, zipfile, mimetypes, re

UPLOAD_FOLDER = 'uploads'
EXPIRY_SECONDS = 86400  # 24 hours

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# In-memory records: { code: {paths:[], timestamp:float, created_at:str, expires_at:str, downloads:[], delete_after:bool} }
file_records = {}

# Admin “all logs” via /retrieve/<adminsecret>
admin_secret = ''.join(__import__('random').choices(__import__('string').ascii_letters + __import__('string').digits, k=32))
print(f"[ADMIN ACCESS CODE]: {admin_secret}")

def now_ts(): return time.time()
def ts_str(): return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
def ts_plus_str(seconds): return datetime.utcfromtimestamp(time.time() + seconds).strftime('%Y-%m-%d %H:%M:%S UTC')

def generate_code(length=8):
    import random, string
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def cleanup_expired():
    now = now_ts()
    expired = [code for code, rec in file_records.items() if now - rec['timestamp'] > EXPIRY_SECONDS]
    for code in expired:
        delete_files(code)

def delete_files(code):
    rec = file_records.get(code)
    if not rec: return
    for p in rec['paths']:
        try:
            if os.path.exists(p): os.remove(p)
        except: pass
    # cleanup any zip that may have been created
    try:
        z = os.path.join(app.config['UPLOAD_FOLDER'], f"{code}_bundle.zip")
        if os.path.exists(z): os.remove(z)
    except: pass
    file_records.pop(code, None)

@app.route('/upload', methods=['POST'])
def upload_files():
    cleanup_expired()
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files uploaded'}), 400

    delete_after_download = (request.form.get('delete_after') == 'true')
    code = generate_code()
    saved_paths = []

    for f in files:
        if not f or f.filename == '': 
            continue
        filename = secure_filename(f.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{code}_{filename}")
        f.save(save_path)
        saved_paths.append(save_path)

    file_records[code] = {
        'paths': saved_paths,
        'timestamp': now_ts(),
        'created_at': ts_str(),
        'expires_at': ts_plus_str(EXPIRY_SECONDS),
        'downloads': [],
        'delete_after': delete_after_download
    }
    return jsonify({'code': code})

@app.route('/retrieve/<code>', methods=['GET'])
def retrieve_or_logs(code):
    cleanup_expired()

    # Admin logs view
    if code == admin_secret:
        logs = []
        for k, v in file_records.items():
            logs.append({
                'code': k,
                'created_at': v['created_at'],
                'expires_at': v['expires_at'],
                'downloads': v['downloads'],
                'delete_after_download': v['delete_after']
            })
        return jsonify(logs)

    if code not in file_records:
        abort(404)

    rec = file_records[code]
    rec['downloads'].append(ts_str())
    paths = rec['paths']

    if len(paths) == 1:
        original = os.path.basename(paths[0]).replace(f"{code}_", "")
        return send_file(paths[0], as_attachment=True, download_name=original)
    else:
        zip_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{code}_bundle.zip")
        # rebuild zip each request to avoid stale
        if os.path.exists(zip_path): os.remove(zip_path)
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for p in paths:
                zf.write(p, os.path.basename(p).replace(f"{code}_", ""))
        return send_file(zip_path, as_attachment=True, download_name=f"{code}.zip")

@app.route('/meta/<code>', methods=['GET'])
def meta(code):
    """Return metadata for preview UI."""
    cleanup_expired()
    rec = file_records.get(code)
    if not rec: abort(404)

    files = []
    for idx, p in enumerate(rec['paths']):
        name = os.path.basename(p).replace(f"{code}_", "")
        size = os.path.getsize(p) if os.path.exists(p) else 0
        mime, _ = mimetypes.guess_type(name)
        mime = mime or 'application/octet-stream'
        is_video = mime.startswith('video/')
        is_audio = mime.startswith('audio/')
        is_image = mime.startswith('image/')
        files.append({
            'index': idx,
            'name': name,
            'size': size,
            'mime': mime,
            'is_video': is_video,
            'is_audio': is_audio,
            'is_image': is_image,
            'stream_url': request.host_url.rstrip('/') + f"/stream/{code}/{idx}"
        })

    return jsonify({
        'code': code,
        'created_at': rec['created_at'],
        'expires_at': rec['expires_at'],
        'delete_after_download': rec['delete_after'],
        'files': files,
        'download_all_url': request.host_url.rstrip('/') + f"/retrieve/{code}"
    })

# Basic HTTP Range support for inline streaming
_range_re = re.compile(r"bytes=(\d+)-(\d+)?")

def send_range(path, mime):
    file_size = os.path.getsize(path)
    range_header = request.headers.get('Range', None)
    if not range_header:
        return send_file(path, mimetype=mime, as_attachment=False, conditional=True)

    m = _range_re.match(range_header or "")
    if not m:
        return send_file(path, mimetype=mime, as_attachment=False, conditional=True)

    start = int(m.group(1))
    end = m.group(2)
    end = int(end) if end is not None else file_size - 1
    start = max(0, start)
    end = min(end, file_size - 1)
    length = end - start + 1

    with open(path, 'rb') as f:
        f.seek(start)
        data = f.read(length)

    rv = Response(data, 206, mimetype=mime, direct_passthrough=True)
    rv.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    rv.headers.add('Content-Length', str(length))
    return rv

@app.route('/stream/<code>/<int:index>', methods=['GET'])
def stream_file(code, index):
    cleanup_expired()
    rec = file_records.get(code)
    if not rec: abort(404)
    if index < 0 or index >= len(rec['paths']): abort(404)
    path = rec['paths'][index]
    if not os.path.exists(path): abort(404)

    name = os.path.basename(path).replace(f"{code}_", "")
    mime, _ = mimetypes.guess_type(name)
    mime = mime or 'application/octet-stream'
    # Inline stream (not attachment), with range support for scrub
    return send_range(path, mime)
