from flask import Flask, render_template, request, send_file, jsonify
import os
import subprocess
import uuid
import shutil

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def camouflage_audio(input_path, output_path, level="medium"):
    presets = {
        "light": {
            "pitch": 1.02,
            "tempo": 1.01,
            "reverb_delay": 800,
            "reverb_decay": 0.2,
            "eq_low": 1,
            "eq_high": -0.5
        },
        "medium": {
            "pitch": 1.04,
            "tempo": 0.98,
            "reverb_delay": 1200,
            "reverb_decay": 0.3,
            "eq_low": 2,
            "eq_high": -1
        },
        "strong": {
            "pitch": 1.06,
            "tempo": 0.96,
            "reverb_delay": 1500,
            "reverb_decay": 0.4,
            "eq_low": 3,
            "eq_high": -2
        }
    }

    p = presets.get(level, presets["medium"])

    filter_complex = (
        f"asetrate=44100*{p['pitch']},aresample=44100,"
        f"atempo={p['tempo']},"
        f"aecho=0.6:0.3:{p['reverb_delay']}:{p['reverb_decay']},"
        f"equalizer=f=100:t=h:w=200:g={p['eq_low']},"
        f"equalizer=f=5000:t=h:w=1000:g={p['eq_high']},"
        f"anlmdn=s=1:p=0.002:r=0.002"
    )

    cmd = [
        'ffmpeg',
        '-y',
        '-i', input_path,
        '-af', filter_complex,
        '-ar', '44100',
        '-ac', '2',
        '-b:a', '192k',
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'audio' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['audio']
    level = request.form.get('level', 'medium')

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    file_id = str(uuid.uuid4())[:8]
    input_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_input.mp3")
    output_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_camouflé.mp3")

    file.save(input_path)

    success = camouflage_audio(input_path, output_path, level)

    os.remove(input_path)

    if not success:
        return jsonify({'error': 'Processing failed'}), 500

    return jsonify({
        'success': True,
        'file_id': file_id,
        'download_url': f'/download/{file_id}'
    })

@app.route('/download/<file_id>')
def download(file_id):
    output_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_camouflé.mp3")

    if not os.path.exists(output_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(
        output_path,
        as_attachment=True,
        download_name=f"camouflé_{file_id}.mp3",
        mimetype='audio/mpeg'
    )

@app.route('/preview/<file_id>')
def preview(file_id):
    output_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_camouflé.mp3")

    if not os.path.exists(output_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(output_path, mimetype='audio/mpeg')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
