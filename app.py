from flask import Flask, render_template, request, send_file, jsonify
import os
import subprocess
import uuid

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

FFMPEG_TIMEOUT = 180
OUTPUT_ARGS = ['-ar', '44100', '-ac', '2', '-b:a', '192k']

METHODS = {
    'light': {
        'label': '01 Light',
        'desc': 'Pitch +3%, Tempo -2%',
        'filter': 'asetrate=44100*1.03,aresample=44100,atempo=0.98',
    },
    'medium': {
        'label': '02 Medium',
        'desc': 'Pitch +5%, EQ modéré',
        'filter': 'asetrate=44100*1.05,aresample=44100,atempo=0.97,equalizer=f=100:t=h:w=300:g=2,equalizer=f=3000:t=h:w=1500:g=-1.5',
    },
    'strong': {
        'label': '03 Strong',
        'desc': 'Pitch +6%, Reverb, EQ fort',
        'filter': 'asetrate=44100*1.06,aresample=44100,atempo=0.96,aecho=0.5:0.3:800:0.2,equalizer=f=80:t=h:w=250:g=3,equalizer=f=4000:t=h:w=2000:g=-2',
    },
    'vocoder': {
        'label': '04 Vocoder',
        'desc': 'Formant shift, reverb léger',
        'filter': 'asetrate=44100*1.04,aresample=44100,atempo=0.97,aecho=0.4:0.2:600:0.15,equalizer=f=150:t=h:w=400:g=2.5,equalizer=f=2500:t=h:w=1200:g=-2,equalizer=f=8000:t=h:w=3000:g=1.5',
    },
    'blur': {
        'label': '05 Blur',
        'desc': 'Spectral blur léger + pitch',
        'filter': "afftfilt=real='hypot(re,im)*cos((random(0)*2-1)*2*3.14*0.3)':imag='hypot(re,im)*sin((random(0)*2-1)*2*3.14*0.3)',asetrate=44100*1.04,aresample=44100,atempo=0.98,equalizer=f=200:t=h:w=500:g=1.5",
    },
    'stereo': {
        'label': '06 Stereo',
        'desc': 'Stereo widening + pitch',
        'filter': 'stereotools=mlev=0.8:mpan=0.2,asetrate=44100*1.05,aresample=44100,atempo=0.97,equalizer=f=120:t=h:w=350:g=2,equalizer=f=5000:t=h:w=2500:g=-2.5',
    },
    'compress': {
        'label': '07 Compress',
        'desc': 'Compression + limiting',
        'filter': 'asetrate=44100*1.04,aresample=44100,atempo=0.98,acompressor=threshold=-18dB:ratio=3:attack=10:release=100,alimiter=level=0.9,equalizer=f=100:t=h:w=300:g=2',
    },
    'reverse': {
        'label': '09 Reverse',
        'desc': 'Reverse reverb trick',
        'filter': 'areverse,aecho=0.8:0.6:500:0.4,areverse,asetrate=44100*1.03,aresample=44100,atempo=0.97,equalizer=f=150:t=h:w=400:g=2',
    },
    'granular': {
        'label': '10 Granular',
        'desc': 'Granular synthesis',
        'filter': 'afade=t=in:st=0:d=0.05,afade=t=out:st=0.1:d=0.05,asetrate=44100*1.04,aresample=44100,atempo=0.96,aecho=0.3:0.2:400:0.1,equalizer=f=180:t=h:w=450:g=2.5',
    },
    'extreme': {
        'label': '12 Extreme',
        'desc': 'Pitch +7%, tempo -6%',
        'filter': 'asetrate=44100*1.07,aresample=44100,atempo=0.94,aecho=0.6:0.4:700:0.3,equalizer=f=100:t=h:w=300:g=4,equalizer=f=5000:t=h:w=2500:g=-3,stereotools=mlev=0.7',
    },
    'phase': {
        'label': '13 Phase',
        'desc': 'Phase vocoder style',
        'filter': 'asetrate=44100*1.03,aresample=44100,atempo=0.99,aecho=0.3:0.3:200:0.1,equalizer=f=500:t=h:w=800:g=-2,equalizer=f=2000:t=h:w=1500:g=1.5',
    },
    'bitcrush': {
        'label': '14 Bitcrush',
        'desc': 'Bitcrush léger + EQ',
        'filter': 'asetrate=44100*1.05,aresample=44100,atempo=0.97,aecho=0.5:0.4:1000:0.25,equalizer=f=200:t=h:w=600:g=3,stereotools=mlev=0.75:mpan=0.15',
    },
    'ultra': {
        'label': '15 Ultra',
        'desc': 'COMBO ULTIME',
        'filter': 'asetrate=44100*1.05,aresample=44100,atempo=0.96,aecho=0.4:0.3:500:0.2,equalizer=f=100:t=h:w=300:g=3,equalizer=f=3000:t=h:w=2000:g=-2,equalizer=f=8000:t=h:w=4000:g=2,stereotools=mlev=0.8:mpan=0.1,acompressor=threshold=-20dB:ratio=2.5:attack=15:release=150',
    },
}


def run_ffmpeg(args, timeout=FFMPEG_TIMEOUT):
    cmd = ['ffmpeg', '-y'] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr[:300]}")
            return False
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def get_duration(input_path):
    result = subprocess.run(
        [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', input_path
        ],
        capture_output=True,
        text=True,
        timeout=30
    )
    return float(result.stdout.strip())


def apply_filter(input_path, output_path, filter_complex):
    return run_ffmpeg(['-i', input_path, '-af', filter_complex] + OUTPUT_ARGS + [output_path])


def method_noise(input_path, output_path):
    duration = get_duration(input_path)
    return run_ffmpeg([
        '-f', 'lavfi', '-i', f'anoisesrc=d={duration}:a=0.001:c=pink:r=44100',
        '-i', input_path,
        '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=first:weights=0.05 1,asetrate=44100*1.04,aresample=44100,atempo=0.98',
    ] + OUTPUT_ARGS + [output_path])


def method_vocal_shift(input_path, output_path, work_dir, file_id):
    temp_v = os.path.join(work_dir, f'{file_id}_temp_vocals.mp3')
    temp_i = os.path.join(work_dir, f'{file_id}_temp_instru.mp3')

    try:
        if not run_ffmpeg([
            '-i', input_path,
            '-af', 'highpass=f=250,lowpass=f=4000,asetrate=44100*1.08,aresample=44100,volume=0.7',
        ] + OUTPUT_ARGS + [temp_v]):
            return False

        if not run_ffmpeg([
            '-i', input_path,
            '-af', 'equalizer=f=3000:t=h:w=2000:g=3,asetrate=44100*1.02,aresample=44100,volume=1.3',
        ] + OUTPUT_ARGS + [temp_i]):
            return False

        return run_ffmpeg([
            '-i', temp_v, '-i', temp_i,
            '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=first,volume=1.2',
        ] + OUTPUT_ARGS + [output_path])
    finally:
        for path in (temp_v, temp_i):
            if os.path.exists(path):
                os.remove(path)


def process_audio(input_path, output_path, level, file_id):
    if level == 'noise':
        return method_noise(input_path, output_path)
    if level == 'vocal_shift':
        return method_vocal_shift(input_path, output_path, UPLOAD_FOLDER, file_id)

    method = METHODS.get(level)
    if not method:
        method = METHODS['medium']
    return apply_filter(input_path, output_path, method['filter'])


@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'modes': list(METHODS.keys()) + ['noise', 'vocal_shift'],
    })


@app.route('/methods')
def list_methods():
    items = []
    for key, meta in METHODS.items():
        items.append({'id': key, 'label': meta['label'], 'desc': meta['desc']})
    items.append({'id': 'noise', 'label': '08 Noise', 'desc': 'Bruit subtil + pitch'})
    items.append({'id': 'vocal_shift', 'label': '11 Vocal Shift', 'desc': 'Vocal isolation + pitch diff'})
    return jsonify(items)


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
    success = process_audio(input_path, output_path, level, file_id)

    if os.path.exists(input_path):
        os.remove(input_path)

    if not success:
        if os.path.exists(output_path):
            os.remove(output_path)
        return jsonify({'error': 'Processing failed'}), 500

    return jsonify({
        'success': True,
        'file_id': file_id,
        'download_url': f'/download/{file_id}',
        'mode': level,
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
