#!/usr/bin/env python3
"""
Suno Camouflage Tester — By Blitzø
Teste 15 méthodes de camouflage audio pour bypasser la détection copyright
"""

import subprocess
import os
import json
import sys

INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "musique.mp3"
OUTPUT_DIR = "camouflage_tests"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_ffmpeg(cmd, output_file):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   FFmpeg: {result.stderr[:150]}")
    return result


def get_duration(input_file):
    result = subprocess.run(
        [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', input_file
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def method_01_light(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'asetrate=44100*1.03,aresample=44100,atempo=0.98', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_02_medium(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'asetrate=44100*1.05,aresample=44100,atempo=0.97,equalizer=f=100:t=h:w=300:g=2,equalizer=f=3000:t=h:w=1500:g=-1.5', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_03_strong(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'asetrate=44100*1.06,aresample=44100,atempo=0.96,aecho=0.5:0.3:800:0.2,equalizer=f=80:t=h:w=250:g=3,equalizer=f=4000:t=h:w=2000:g=-2', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_04_vocoder(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'asetrate=44100*1.04,aresample=44100,atempo=0.97,aecho=0.4:0.2:600:0.15,equalizer=f=150:t=h:w=400:g=2.5,equalizer=f=2500:t=h:w=1200:g=-2,equalizer=f=8000:t=h:w=3000:g=1.5', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_05_blur(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', "afftfilt=real='hypot(re,im)*cos((random(0)*2-1)*2*3.14*0.3)':imag='hypot(re,im)*sin((random(0)*2-1)*2*3.14*0.3)',asetrate=44100*1.04,aresample=44100,atempo=0.98,equalizer=f=200:t=h:w=500:g=1.5", '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_06_stereo(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'stereotools=mlev=0.8:mpan=0.2,asetrate=44100*1.05,aresample=44100,atempo=0.97,equalizer=f=120:t=h:w=350:g=2,equalizer=f=5000:t=h:w=2500:g=-2.5', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_07_compress(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'asetrate=44100*1.04,aresample=44100,atempo=0.98,acompressor=threshold=-18dB:ratio=3:attack=10:release=100,alimiter=level=0.9,equalizer=f=100:t=h:w=300:g=2', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_08_noise(input_file, output_file):
    duration = get_duration(input_file)
    cmd = ['ffmpeg', '-y', '-f', 'lavfi', '-i', f'anoisesrc=d={duration}:a=0.001:c=pink:r=44100', '-i', input_file, '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=first:weights=0.05 1,asetrate=44100*1.04,aresample=44100,atempo=0.98', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_09_reverse(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'areverse,aecho=0.8:0.6:500:0.4,areverse,asetrate=44100*1.03,aresample=44100,atempo=0.97,equalizer=f=150:t=h:w=400:g=2', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_10_granular(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'afade=t=in:st=0:d=0.05,afade=t=out:st=0.1:d=0.05,asetrate=44100*1.04,aresample=44100,atempo=0.96,aecho=0.3:0.2:400:0.1,equalizer=f=180:t=h:w=450:g=2.5', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_11_vocal_shift(input_file, output_file):
    temp_v = os.path.join(OUTPUT_DIR, 'temp_vocals.mp3')
    temp_i = os.path.join(OUTPUT_DIR, 'temp_instru.mp3')
    subprocess.run(['ffmpeg', '-y', '-i', input_file, '-af', 'highpass=f=250,lowpass=f=4000,asetrate=44100*1.08,aresample=44100,volume=0.7', '-ar', '44100', '-ac', '2', '-b:a', '192k', temp_v], capture_output=True)
    subprocess.run(['ffmpeg', '-y', '-i', input_file, '-af', 'equalizer=f=3000:t=h:w=2000:g=3,asetrate=44100*1.02,aresample=44100,volume=1.3', '-ar', '44100', '-ac', '2', '-b:a', '192k', temp_i], capture_output=True)
    cmd = ['ffmpeg', '-y', '-i', temp_v, '-i', temp_i, '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=first,volume=1.2', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    result = run_ffmpeg(cmd, output_file)
    for f in [temp_v, temp_i]:
        if os.path.exists(f):
            os.remove(f)
    return result


def method_12_extreme(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'asetrate=44100*1.07,aresample=44100,atempo=0.94,aecho=0.6:0.4:700:0.3,equalizer=f=100:t=h:w=300:g=4,equalizer=f=5000:t=h:w=2500:g=-3,stereotools=mlev=0.7', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_13_phase_vocoder(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'asetrate=44100*1.03,aresample=44100,atempo=0.99,aecho=0.3:0.3:200:0.1,equalizer=f=500:t=h:w=800:g=-2,equalizer=f=2000:t=h:w=1500:g=1.5', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_14_bitcrush_light(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'asetrate=44100*1.05,aresample=44100,atempo=0.97,aecho=0.5:0.4:1000:0.25,equalizer=f=200:t=h:w=600:g=3,stereotools=mlev=0.75:mpan=0.15', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def method_15_ultra_combo(input_file, output_file):
    cmd = ['ffmpeg', '-y', '-i', input_file, '-af', 'asetrate=44100*1.05,aresample=44100,atempo=0.96,aecho=0.4:0.3:500:0.2,equalizer=f=100:t=h:w=300:g=3,equalizer=f=3000:t=h:w=2000:g=-2,equalizer=f=8000:t=h:w=4000:g=2,stereotools=mlev=0.8:mpan=0.1,acompressor=threshold=-20dB:ratio=2.5:attack=15:release=150', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_file]
    return run_ffmpeg(cmd, output_file)


def main():
    if len(sys.argv) < 2:
        print("Usage: python suno_camouflage.py <fichier_audio.mp3>")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"Fichier non trouve: {input_file}")
        sys.exit(1)

    check = subprocess.run(['ffmpeg', '-version'], capture_output=True)
    if check.returncode != 0:
        print("FFmpeg non installe!")
        sys.exit(1)

    methods = [
        ("01_light", method_01_light, "Pitch +3%, Tempo -2%"),
        ("02_medium", method_02_medium, "Pitch +5%, EQ modere"),
        ("03_strong", method_03_strong, "Pitch +6%, Reverb, EQ fort"),
        ("04_vocoder", method_04_vocoder, "Formant shift, reverb leger"),
        ("05_blur", method_05_blur, "Spectral blur leger + pitch"),
        ("06_stereo", method_06_stereo, "Stereo widening + pitch"),
        ("07_compress", method_07_compress, "Compression + limiting"),
        ("08_noise", method_08_noise, "Bruit subtil + pitch"),
        ("09_reverse", method_09_reverse, "Reverse reverb trick"),
        ("10_granular", method_10_granular, "Granular synthesis"),
        ("11_vocal_shift", method_11_vocal_shift, "Vocal isolation + pitch diff"),
        ("12_extreme", method_12_extreme, "Pitch +7%, tempo -6%"),
        ("13_phase", method_13_phase_vocoder, "Phase vocoder style"),
        ("14_bitcrush", method_14_bitcrush_light, "Bitcrush leger + EQ"),
        ("15_ultra", method_15_ultra_combo, "COMBO ULTIME"),
    ]

    print("SUNO CAMOUFLAGE TESTER — By Blitzo")
    print(f"Source: {input_file}")
    print(f"Sortie: {OUTPUT_DIR}/")
    print("=" * 60)

    results = []
    for name, method, desc in methods:
        output = os.path.join(OUTPUT_DIR, f"test_{name}.mp3")
        print(f"\n{name}: {desc}...", end=" ")

        result = method(input_file, output)

        if result.returncode == 0 and os.path.exists(output):
            size = os.path.getsize(output)
            print(f"OK ({size / 1024:.0f} KB)")
            results.append({"method": name, "desc": desc, "file": output, "status": "OK", "size_kb": round(size / 1024)})
        else:
            print("ECHEC")
            results.append({"method": name, "desc": desc, "file": None, "status": "FAIL"})

    print("\n" + "=" * 60)
    print("RESULTATS:")
    for r in results:
        emoji = "OK" if r["status"] == "OK" else "FAIL"
        size = f"({r.get('size_kb', 0)} KB)" if r["status"] == "OK" else ""
        print(f"{emoji} {r['method']}: {r['desc']} {size}")

    report = os.path.join(OUTPUT_DIR, "report.json")
    with open(report, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f"\nRapport: {report}")


if __name__ == "__main__":
    main()
