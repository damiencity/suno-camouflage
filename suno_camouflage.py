#!/usr/bin/env python3
"""CLI batch for the 5 advanced camouflage methods."""

import os
import sys
import uuid

from app import (
    METHODS_META,
    process_audio,
)

OUTPUT_DIR = 'camouflage_tests'


def main():
    if len(sys.argv) < 2:
        print('Usage: python suno_camouflage.py <audio.mp3> [method]')
        print('Methods:', ', '.join(METHODS_META.keys()))
        sys.exit(1)

    input_file = sys.argv[1]
    method = sys.argv[2] if len(sys.argv) > 2 else 'all'

    if not os.path.exists(input_file):
        print(f'File not found: {input_file}')
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    methods = list(METHODS_META.keys()) if method == 'all' else [method]

    for m in methods:
        if m not in METHODS_META:
            print(f'Unknown method: {m}')
            continue
        file_id = str(uuid.uuid4())[:8]
        out = os.path.join(OUTPUT_DIR, f'{m}_{file_id}.mp3')
        print(f'{METHODS_META[m]["label"]}: {METHODS_META[m]["desc"]}...', end=' ', flush=True)
        ok = process_audio(input_file, out, m, file_id)
        print('OK' if ok else 'FAIL')


if __name__ == '__main__':
    main()
