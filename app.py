from flask import Flask, render_template, request, send_file, jsonify
import os
import subprocess
import uuid
import shutil
import glob

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

FFMPEG_TIMEOUT = 300
LONG_TIMEOUT = 900
OUTPUT_ARGS = ['-ar', '44100', '-ac', '2', '-b:a', '192k']

METHODS_META = {
    'timbre': {
        'label': '02 Timbre',
        'desc': 'Timbre transfer (spectral / RAVE-DDSP si dispo)',
    },
    'nuclear': {
        'label': '03 Nuclear',
        'desc': 'Demucs separation + transform stems + remix',
    },
    'nonlinear': {
        'label': '04 Nonlinear',
        'desc': 'Time stretch Rubberband + variations locales',
    },
    'vocoder': {
        'label': '05 Vocoder',
        'desc': 'Vocoder + synthèse granulaire simulée',
    },
    'salvation': {
        'label': 'Salvation',
        'desc': 'Pipeline MIDI + resynthèse (approx FFmpeg)',
    },
}


def run_cmd(cmd, timeout=FFMPEG_TIMEOUT):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or '')[:500]
            print(f"CMD error ({cmd[0]}): {err}")
            return False, err
        return True, ''
    except Exception as e:
        print(f"Error: {e}")
        return False, str(e)


def run_ffmpeg(args, timeout=FFMPEG_TIMEOUT):
    ok, _ = run_cmd(['ffmpeg', '-y'] + args, timeout=timeout)
    return ok


def has_tool(name):
    return shutil.which(name) is not None


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


def rubberband_or_ffmpeg(input_path, output_path, tempo=0.92, pitch=1.08):
    if has_tool('rubberband'):
        ok, _ = run_cmd([
            'rubberband', '-t', str(tempo), '-p', str(pitch), '-c', '6',
            input_path, output_path
        ], timeout=FFMPEG_TIMEOUT)
        if ok and os.path.exists(output_path):
            return True

    return run_ffmpeg([
        '-i', input_path,
        '-af', f'asetrate=44100*{pitch},aresample=44100,atempo={tempo}',
    ] + OUTPUT_ARGS + [output_path])


def cleanup_paths(paths):
    for path in paths:
        if path and os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
            except OSError:
                pass


# ============================================================
# 02 TIMBRE TRANSFER
# ============================================================

def method_timbre(input_path, output_path, work_dir, file_id):
    """
    Prefer RAVE/DDSP if installed + model present.
    Fallback: aggressive spectral morphing (afftfilt) + formant-ish EQ.
    """
    rave_model = os.environ.get('RAVE_MODEL', '').strip()
    rave_decode_model = os.environ.get('RAVE_DECODE_MODEL', rave_model).strip()

    if has_tool('rave') and rave_model and os.path.exists(rave_model):
        encoded = os.path.join(work_dir, f'{file_id}_encoded.pt')
        decoded = os.path.join(work_dir, f'{file_id}_rave.wav')
        ok, _ = run_cmd([
            'rave', 'encode', input_path,
            '--model', rave_model, '-o', encoded
        ], timeout=LONG_TIMEOUT)
        if ok:
            ok, _ = run_cmd([
                'rave', 'decode', encoded,
                '--model', rave_decode_model or rave_model, '-o', decoded
            ], timeout=LONG_TIMEOUT)
            if ok and os.path.exists(decoded):
                success = run_ffmpeg(['-i', decoded] + OUTPUT_ARGS + [output_path])
                cleanup_paths([encoded, decoded])
                return success
        cleanup_paths([encoded, decoded])

    if has_tool('ddsp_generate'):
        ddsp_out = os.path.join(work_dir, f'{file_id}_ddsp.wav')
        ok, _ = run_cmd([
            'ddsp_generate', f'--input_audio={input_path}', f'--output={ddsp_out}'
        ], timeout=LONG_TIMEOUT)
        if ok and os.path.exists(ddsp_out):
            success = run_ffmpeg(['-i', ddsp_out] + OUTPUT_ARGS + [output_path])
            cleanup_paths([ddsp_out])
            return success
        cleanup_paths([ddsp_out])

    # Spectral / formant approximation
    filt = (
        "afftfilt=real='hypot(re,im)*cos((random(0)*2-1)*2*3.14*0.45)'"
        ":imag='hypot(re,im)*sin((random(0)*2-1)*2*3.14*0.45)',"
        "asetrate=44100*1.05,aresample=44100,atempo=0.97,"
        "aecho=0.5:0.4:600:0.3,"
        "equalizer=f=120:t=h:w=400:g=4,"
        "equalizer=f=800:t=h:w=600:g=-3,"
        "equalizer=f=2500:t=h:w=1200:g=2,"
        "equalizer=f=7000:t=h:w=3000:g=-3,"
        "stereotools=mlev=0.75:mpan=0.2,"
        "volume=1.1"
    )
    return run_ffmpeg(['-i', input_path, '-af', filt] + OUTPUT_ARGS + [output_path])


# ============================================================
# 03 SOURCE SEPARATION (DEMUCS) → NUCLEAR
# ============================================================

def find_demucs_stems(work_dir, base_name):
    patterns = [
        os.path.join(work_dir, 'separated', 'htdemucs', base_name, '*.wav'),
        os.path.join(work_dir, 'separated', 'htdemucs_ft', base_name, '*.wav'),
        os.path.join(work_dir, 'separated', '*', base_name, '*.wav'),
    ]
    stems = {}
    for pattern in patterns:
        for path in glob.glob(pattern):
            name = os.path.splitext(os.path.basename(path))[0].lower()
            stems[name] = path
        if stems:
            break
    return stems


def method_nuclear(input_path, output_path, work_dir, file_id):
    """Demucs 4-stem split → transform each → remix."""
    separated_root = os.path.join(work_dir, f'{file_id}_sep')
    os.makedirs(separated_root, exist_ok=True)
    temps = []

    try:
        if not has_tool('demucs'):
            # Fallback without Demucs: strong multi-band transform
            filt = (
                "asetrate=44100*1.08,aresample=44100,atempo=0.92,"
                "aecho=0.7:0.5:400:0.4,aecho=0.4:0.3:900:0.25,"
                "equalizer=f=60:t=h:w=120:g=5,"
                "equalizer=f=200:t=h:w=600:g=3,"
                "equalizer=f=3000:t=h:w=2000:g=-3,"
                "equalizer=f=8000:t=h:w=4000:g=-3,"
                "stereotools=mlev=0.6,"
                "acompressor=threshold=-16dB:ratio=3:attack=10:release=100,"
                "alimiter=limit=0.95"
            )
            return run_ffmpeg(['-i', input_path, '-af', filt] + OUTPUT_ARGS + [output_path], timeout=LONG_TIMEOUT)

        ok, err = run_cmd([
            'demucs', '-n', 'htdemucs', '-o', separated_root, input_path
        ], timeout=LONG_TIMEOUT)
        if not ok:
            print(f'Demucs failed: {err}')
            return False

        base_name = os.path.splitext(os.path.basename(input_path))[0]
        stems = find_demucs_stems(separated_root, base_name)
        if not stems:
            # try folder names demucs creates from filename
            for root, _dirs, files in os.walk(separated_root):
                for f in files:
                    if f.endswith('.wav'):
                        stems[os.path.splitext(f)[0].lower()] = os.path.join(root, f)
            if len(stems) < 2:
                return False

        vocals = stems.get('vocals')
        drums = stems.get('drums')
        bass = stems.get('bass')
        other = stems.get('other') or stems.get('accompaniment')

        v_out = os.path.join(work_dir, f'{file_id}_vocals_t.wav')
        d_out = os.path.join(work_dir, f'{file_id}_drums_t.wav')
        b_out = os.path.join(work_dir, f'{file_id}_bass_t.wav')
        o_out = os.path.join(work_dir, f'{file_id}_other_t.wav')
        temps.extend([v_out, d_out, b_out, o_out])

        if vocals:
            if not run_ffmpeg([
                '-i', vocals,
                '-af',
                'asetrate=44100*1.12,aresample=44100,atempo=0.90,'
                'aecho=0.7:0.5:400:0.4,'
                'equalizer=f=200:t=h:w=600:g=4,'
                'equalizer=f=3000:t=h:w=2000:g=-3,'
                'stereotools=mlev=0.6,'
                'anlmdn=s=4:p=0.01:r=0.01',
                '-ar', '44100', '-ac', '2', v_out
            ], timeout=FFMPEG_TIMEOUT):
                return False

        if drums:
            if not run_ffmpeg([
                '-i', drums,
                '-af',
                'equalizer=f=60:t=h:w=100:g=5,'
                'equalizer=f=8000:t=h:w=4000:g=-4,'
                'asetrate=44100*1.03,aresample=44100',
                '-ar', '44100', '-ac', '2', d_out
            ], timeout=FFMPEG_TIMEOUT):
                return False

        if bass:
            if not run_ffmpeg([
                '-i', bass,
                '-af',
                'asetrate=44100*1.05,aresample=44100,'
                'equalizer=f=100:t=h:w=300:g=3',
                '-ar', '44100', '-ac', '2', b_out
            ], timeout=FFMPEG_TIMEOUT):
                return False

        if other:
            if not run_ffmpeg([
                '-i', other,
                '-af',
                'asetrate=44100*1.04,aresample=44100,'
                'equalizer=f=1000:t=h:w=1500:g=2,'
                'equalizer=f=6000:t=h:w=3000:g=-2',
                '-ar', '44100', '-ac', '2', o_out
            ], timeout=FFMPEG_TIMEOUT):
                return False

        inputs = []
        volumes = []
        labels = []
        for path, vol, lab in [
            (v_out, '0.8', 'v'),
            (d_out, '1.0', 'd'),
            (b_out, '1.1', 'b'),
            (o_out, '0.9', 'o'),
        ]:
            if os.path.exists(path):
                inputs.extend(['-i', path])
                volumes.append(f'[{len(labels)}:a]volume={vol}[{lab}]')
                labels.append(f'[{lab}]')

        if len(labels) < 2:
            return False

        mix = (
            ';'.join(volumes) + ';'
            + ''.join(labels) + f'amix=inputs={len(labels)}:duration=first,'
            'acompressor=threshold=-16dB:ratio=3:attack=10:release=100,'
            'alimiter=limit=0.95,'
            'equalizer=f=100:t=h:w=400:g=2'
        )
        return run_ffmpeg(
            inputs + ['-filter_complex', mix] + OUTPUT_ARGS + [output_path],
            timeout=LONG_TIMEOUT
        )
    finally:
        cleanup_paths(temps + [separated_root])


# ============================================================
# 04 TIME STRETCH NON-LINÉAIRE
# ============================================================

def method_nonlinear(input_path, output_path, work_dir, file_id):
    temp = os.path.join(work_dir, f'{file_id}_nonlinear_temp.wav')
    try:
        if not rubberband_or_ffmpeg(input_path, temp, tempo=0.92, pitch=1.08):
            return False
        filt = (
            'atempo=1.0,'
            'aecho=0.5:0.3:300:0.2,'
            'equalizer=f=150:t=h:w=500:g=3,'
            'equalizer=f=4000:t=h:w=2500:g=-2'
        )
        return run_ffmpeg(['-i', temp, '-af', filt] + OUTPUT_ARGS + [output_path])
    finally:
        cleanup_paths([temp])


# ============================================================
# 05 VOCODER + GRANULAIRE
# ============================================================

def method_vocoder(input_path, output_path, work_dir, file_id):
    filt = (
        'asetrate=44100*1.06,aresample=44100,'
        'atempo=0.94,'
        'aecho=0.8:0.6:200:0.5,'
        'aecho=0.4:0.3:800:0.3,'
        'equalizer=f=80:t=h:w=300:g=5,'
        'equalizer=f=500:t=h:w=800:g=-3,'
        'equalizer=f=2500:t=h:w=2000:g=2,'
        'equalizer=f=10000:t=h:w=5000:g=-4,'
        'stereotools=mlev=0.5:mpan=0.3,'
        'acompressor=threshold=-14dB:ratio=4:attack=5:release=80,'
        'alimiter=limit=0.9,'
        'volume=1.1'
    )
    return run_ffmpeg(['-i', input_path, '-af', filt] + OUTPUT_ARGS + [output_path])


# ============================================================
# SALVATION (approx — full MIDI/AI voice pipeline is manual)
# ============================================================

def method_salvation(input_path, output_path, work_dir, file_id):
    """
    Full Salvation = MIDI (basic-pitch) + AI voice + DAW rebuild.
    Automated approx: isolate mid/voice band, heavy pitch, rebuild with
    filtered accompaniment — closest FFmpeg-only stand-in.
    """
    vocals = os.path.join(work_dir, f'{file_id}_sal_v.wav')
    instru = os.path.join(work_dir, f'{file_id}_sal_i.wav')
    try:
        if not run_ffmpeg([
            '-i', input_path,
            '-af',
            'highpass=f=180,lowpass=f=4500,'
            'asetrate=44100*1.15,aresample=44100,atempo=0.88,'
            'aecho=0.6:0.4:350:0.35,volume=0.75',
            '-ar', '44100', '-ac', '2', vocals
        ]):
            return False

        if not run_ffmpeg([
            '-i', input_path,
            '-af',
            'equalizer=f=250:t=h:w=400:g=-6,'
            'equalizer=f=3000:t=h:w=2000:g=-4,'
            'asetrate=44100*1.03,aresample=44100,atempo=0.97,'
            'equalizer=f=80:t=h:w=200:g=3,volume=1.15',
            '-ar', '44100', '-ac', '2', instru
        ]):
            return False

        return run_ffmpeg([
            '-i', vocals, '-i', instru,
            '-filter_complex',
            '[0:a][1:a]amix=inputs=2:duration=first:weights=0.85 1,'
            'acompressor=threshold=-18dB:ratio=3:attack=8:release=120,'
            'alimiter=limit=0.92,volume=1.05',
        ] + OUTPUT_ARGS + [output_path])
    finally:
        cleanup_paths([vocals, instru])


def process_audio(input_path, output_path, level, file_id):
    handlers = {
        'timbre': method_timbre,
        'nuclear': method_nuclear,
        'nonlinear': method_nonlinear,
        'vocoder': method_vocoder,
        'salvation': method_salvation,
    }
    handler = handlers.get(level, method_vocoder)
    return handler(input_path, output_path, UPLOAD_FOLDER, file_id)


@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'tools': {
            'ffmpeg': has_tool('ffmpeg'),
            'rubberband': has_tool('rubberband'),
            'demucs': has_tool('demucs'),
            'rave': has_tool('rave'),
            'ddsp_generate': has_tool('ddsp_generate'),
        },
        'modes': list(METHODS_META.keys()),
    })


@app.route('/methods')
def list_methods():
    return jsonify([
        {'id': k, 'label': v['label'], 'desc': v['desc']}
        for k, v in METHODS_META.items()
    ])


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    if 'audio' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['audio']
    level = request.form.get('level', 'vocoder')

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if level not in METHODS_META:
        return jsonify({'error': f'Unknown method: {level}'}), 400

    file_id = str(uuid.uuid4())[:8]
    input_path = os.path.join(UPLOAD_FOLDER, f'{file_id}_input.mp3')
    output_path = os.path.join(UPLOAD_FOLDER, f'{file_id}_camouflé.mp3')

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
    output_path = os.path.join(UPLOAD_FOLDER, f'{file_id}_camouflé.mp3')
    if not os.path.exists(output_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(
        output_path,
        as_attachment=True,
        download_name=f'camouflé_{file_id}.mp3',
        mimetype='audio/mpeg'
    )


@app.route('/preview/<file_id>')
def preview(file_id):
    output_path = os.path.join(UPLOAD_FOLDER, f'{file_id}_camouflé.mp3')
    if not os.path.exists(output_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(output_path, mimetype='audio/mpeg')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
