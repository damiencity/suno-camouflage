from flask import Flask, render_template, request, send_file, jsonify
import os
import subprocess
import uuid
import shutil

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

FFMPEG_TIMEOUT = 180
LONG_TIMEOUT = 300


def run_ffmpeg(args, timeout=FFMPEG_TIMEOUT):
    cmd = ['ffmpeg', '-y'] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def has_rubberband():
    return shutil.which('rubberband') is not None


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


def output_args(output_path):
    return ['-ar', '44100', '-ac', '2', '-b:a', '192k', output_path]


def pitch_shift_fallback(input_path, output_path, tempo, pitch):
    filter_complex = (
        f"asetrate=44100*{pitch},aresample=44100,"
        f"atempo={tempo}"
    )
    return run_ffmpeg(['-i', input_path, '-af', filter_complex] + output_args(output_path))


def rubberband_process(input_path, output_path, tempo, pitch, crispness=6):
    if not has_rubberband():
        return pitch_shift_fallback(input_path, output_path, tempo, pitch)

    cmd = [
        'rubberband',
        '-t', str(tempo),
        '-p', str(pitch),
        '-c', str(crispness),
        input_path,
        output_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
        if result.returncode != 0:
            print(f"Rubberband error: {result.stderr}")
            return pitch_shift_fallback(input_path, output_path, tempo, pitch)
        return True
    except Exception as e:
        print(f"Rubberband error: {e}")
        return pitch_shift_fallback(input_path, output_path, tempo, pitch)


def camouflage_basic(input_path, output_path, level="medium"):
    presets = {
        "light": {
            "pitch": 1.02, "tempo": 1.01,
            "reverb_delay": 800, "reverb_decay": 0.2,
            "eq_low": 1, "eq_high": -0.5
        },
        "medium": {
            "pitch": 1.04, "tempo": 0.98,
            "reverb_delay": 1200, "reverb_decay": 0.3,
            "eq_low": 2, "eq_high": -1
        },
        "strong": {
            "pitch": 1.06, "tempo": 0.96,
            "reverb_delay": 1500, "reverb_decay": 0.4,
            "eq_low": 3, "eq_high": -2
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
    return run_ffmpeg(['-i', input_path, '-af', filter_complex] + output_args(output_path))


def camouflage_spectral(input_path, output_path):
    filter_complex = (
        "afftfilt=real='hypot(re,im)*cos((random(0)*2-1)*2*3.14)'"
        ":imag='hypot(re,im)*sin((random(0)*2-1)*2*3.14)',"
        "asetrate=44100*1.05,aresample=44100,"
        "atempo=0.97,"
        "aecho=0.5:0.4:800:0.3,"
        "equalizer=f=80:t=h:w=300:g=4,"
        "equalizer=f=400:t=h:w=500:g=-3,"
        "equalizer=f=2000:t=h:w=1000:g=2,"
        "equalizer=f=8000:t=h:w=3000:g=-4,"
        "stereotools=mlev=0.8,"
        "anlmdn=s=2:p=0.005:r=0.005,"
        "volume=1.2"
    )
    return run_ffmpeg(['-i', input_path, '-af', filter_complex] + output_args(output_path))


def camouflage_vocoder(input_path, output_path, work_dir, file_id):
    step1 = os.path.join(work_dir, f"{file_id}_voc_step1.mp3")
    if not rubberband_process(input_path, step1, tempo=0.95, pitch=1.08):
        return False

    filter_complex = (
        "aecho=0.6:0.5:600:0.4,"
        "equalizer=f=100:t=h:w=400:g=5,"
        "equalizer=f=3000:t=h:w=2000:g=-5,"
        "stereotools=mlev=0.7:mpan=0.3,"
        "volume=1.1"
    )
    ok = run_ffmpeg(['-i', step1, '-af', filter_complex] + output_args(output_path))
    if os.path.exists(step1):
        os.remove(step1)
    return ok


def camouflage_segments(input_path, output_path, work_dir, file_id, num_segments=8):
    duration = get_duration(input_path)
    num_segments = min(num_segments, max(2, int(duration / 3)))
    segment_duration = duration / num_segments
    segments = []
    transitions = []
    fade_d = min(0.5, segment_duration / 3)
    fade_out_start = max(segment_duration - fade_d, 0)

    try:
        for i in range(num_segments):
            start = i * segment_duration
            seg_file = os.path.join(work_dir, f"{file_id}_seg_{i}.mp3")
            if not run_ffmpeg([
                '-i', input_path,
                '-ss', str(start), '-t', str(segment_duration),
                '-af', 'volume=1.1',
                seg_file
            ]):
                return False
            segments.append(seg_file)

        concat_list = os.path.join(work_dir, f"{file_id}_concat.txt")

        with open(concat_list, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(segments):
                transition = os.path.join(work_dir, f"{file_id}_trans_{i}.mp3")
                if not run_ffmpeg([
                    '-i', seg,
                    '-af', f'afade=t=in:ss=0:d={fade_d},afade=t=out:st={fade_out_start}:d={fade_d}',
                    transition
                ]):
                    return False
                transitions.append(transition)
                abs_path = os.path.abspath(transition).replace('\\', '/')
                f.write(f"file '{abs_path}'\n")

        return run_ffmpeg([
            '-f', 'concat', '-safe', '0', '-i', concat_list,
            '-af', 'asetrate=44100*1.03,aresample=44100,atempo=0.98'
        ] + output_args(output_path), timeout=LONG_TIMEOUT)
    finally:
        for path in segments + transitions:
            if os.path.exists(path):
                os.remove(path)
        concat_path = os.path.join(work_dir, f"{file_id}_concat.txt")
        if os.path.exists(concat_path):
            os.remove(concat_path)


def camouflage_ultimate(input_path, output_path, work_dir, file_id):
    step1 = os.path.join(work_dir, f"{file_id}_ult_step1.mp3")
    step2 = os.path.join(work_dir, f"{file_id}_ult_step2.mp3")
    step3 = os.path.join(work_dir, f"{file_id}_ult_step3.mp3")
    temp_files = [step1, step2, step3]

    try:
        if not rubberband_process(input_path, step1, tempo=0.94, pitch=1.06):
            return False

        filter_step2 = (
            "afftfilt=real='hypot(re,im)*cos((random(0)*2-1)*2*3.14)'"
            ":imag='hypot(re,im)*sin((random(0)*2-1)*2*3.14)',"
            "aecho=0.7:0.6:500:0.5,"
            "equalizer=f=60:t=h:w=200:g=6,"
            "equalizer=f=250:t=h:w=300:g=-4,"
            "equalizer=f=1000:t=h:w=800:g=3,"
            "equalizer=f=4000:t=h:w=2000:g=-6,"
            "equalizer=f=12000:t=h:w=4000:g=4,"
            "stereotools=mlev=0.6:mpan=0.4,"
            "anlmdn=s=3:p=0.008:r=0.008,"
            "volume=1.3"
        )
        if not run_ffmpeg(['-i', step1, '-af', filter_step2] + output_args(step2), timeout=LONG_TIMEOUT):
            return False

        noise_duration = get_duration(step2)
        if not run_ffmpeg([
            '-i', step2,
            '-f', 'lavfi', '-i', f'anoisesrc=d={noise_duration}:c=brown:a=0.003',
            '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=first:weights=0.15 1',
        ] + output_args(step3), timeout=LONG_TIMEOUT):
            return False

        filter_step4 = (
            "acompressor=threshold=-20dB:ratio=4:attack=5:release=100,"
            "alimiter=level=1,"
            "volume=0.9"
        )
        return run_ffmpeg(['-i', step3, '-af', filter_step4] + output_args(output_path), timeout=LONG_TIMEOUT)
    finally:
        for path in temp_files:
            if os.path.exists(path):
                os.remove(path)


def process_audio(input_path, output_path, level, file_id):
    work_dir = UPLOAD_FOLDER

    if level in ('light', 'medium', 'strong'):
        return camouflage_basic(input_path, output_path, level)
    if level == 'spectral':
        return camouflage_spectral(input_path, output_path)
    if level == 'vocoder':
        return camouflage_vocoder(input_path, output_path, work_dir, file_id)
    if level == 'segments':
        return camouflage_segments(input_path, output_path, work_dir, file_id)
    if level == 'ultimate':
        return camouflage_ultimate(input_path, output_path, work_dir, file_id)

    return camouflage_basic(input_path, output_path, 'medium')


@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'rubberband': has_rubberband(),
        'modes': ['light', 'medium', 'strong', 'spectral', 'vocoder', 'segments', 'ultimate']
    })


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
        'mode': level
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
