import argparse
import base64
import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests


def parse_ids(ids_arg: str | None) -> set[str] | None:
    """
    --ids "1,2,3"  or  --ids "1 2 3"
    Returns set of ids as strings, or None meaning "all".
    """
    if not ids_arg:
        return None
    parts = [p.strip() for p in ids_arg.replace(",", " ").split()]
    parts = [p for p in parts if p]
    return set(parts) if parts else None


def synthesize_ssml_wav(api_key: str, voice_name: str, language_code: str, ssml: str) -> bytes:
    """
    Synthesize SSML via Google Cloud TTS REST using an API key.
    Returns WAV bytes (LINEAR16).
    """
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    payload = {
        "input": {"ssml": ssml},
        "voice": {"languageCode": language_code, "name": voice_name},
        "audioConfig": {"audioEncoding": "LINEAR16"},
    }

    r = requests.post(url, json=payload, timeout=60)
    if r.status_code != 200:
        try:
            err = r.json()
        except Exception:
            err = {"raw": r.text}
        raise RuntimeError(f"TTS failed ({r.status_code}): {err}")

    audio_b64 = r.json()["audioContent"]
    return base64.b64decode(audio_b64)


def ffmpeg_exists() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def convert_wav_bytes_with_ffmpeg(
    wav_bytes: bytes,
    out_path: Path,
    fmt: str,
    delete_temp: bool = True,
) -> None:
    """
    Converts WAV bytes to mp3/ogg/wav using ffmpeg.
    For wav, this still passes through ffmpeg (handy if you want consistency).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)

    try:
        with open(tmp_wav_path, "wb") as f:
            f.write(wav_bytes)

        if fmt == "wav":
            cmd = ["ffmpeg", "-y", "-i", tmp_wav_path, "-c:a", "pcm_s16le", str(out_path)]
        elif fmt == "mp3":
            cmd = ["ffmpeg", "-y", "-i", tmp_wav_path, "-codec:a", "libmp3lame", "-q:a", "2", str(out_path)]
        elif fmt == "ogg":
            cmd = ["ffmpeg", "-y", "-i", tmp_wav_path, "-codec:a", "libvorbis", "-q:a", "5", str(out_path)]
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        subprocess.run(cmd, check=True)
    finally:
        if delete_temp and os.path.exists(tmp_wav_path):
            os.remove(tmp_wav_path)


def write_direct_wav(wav_bytes: bytes, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(wav_bytes)


def main():
    parser = argparse.ArgumentParser(
        description="Batch synthesize SSML from transcripts.csv using Google Cloud TTS (API key), with optional ffmpeg conversion."
    )
    parser.add_argument("--api-key", required=True, help="Google Cloud API key")
    parser.add_argument("--csv", default="transcripts.csv", help="Path to transcripts.csv")
    parser.add_argument("--outdir", default="out_audio", help="Output directory")
    parser.add_argument("--ids", default=None, help='Comma/space separated list of ids to regenerate, e.g. "1,2,3"')
    parser.add_argument("--id-col", default="id", help="ID column name (default: id)")
    parser.add_argument("--ssml-col", default="ssml", help="SSML column name")
    parser.add_argument("--voice", default="en-GB-Chirp3-HD-Leda", help="Voice name")
    parser.add_argument("--lang", default="en-GB", help="Language code")

    parser.add_argument("--format", choices=["wav", "mp3", "ogg"], default="mp3", help="Output format")
    parser.add_argument(
        "--use-ffmpeg",
        action="store_true",
        help="Use ffmpeg to produce the final file (required for mp3/ogg; optional for wav).",
    )
    parser.add_argument(
        "--delete-original-wav",
        action="store_true",
        help="If --format is mp3/ogg, delete the intermediate wav file if it was written to disk.",
    )

    args = parser.parse_args()

    wanted_ids = parse_ids(args.ids)
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV not found: {csv_path.resolve()}", file=sys.stderr)
        sys.exit(1)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.format in ("mp3", "ogg") and not args.use_ffmpeg:
        print("For mp3/ogg, you must pass --use-ffmpeg.", file=sys.stderr)
        sys.exit(2)

    if args.use_ffmpeg and not ffmpeg_exists():
        print("ffmpeg not found on PATH. Install ffmpeg and ensure 'ffmpeg' works in PowerShell.", file=sys.stderr)
        sys.exit(3)

    generated = 0
    skipped = 0
    seen_ids: set[str] = set()

    # newline="" is essential so multiline quoted SSML fields read correctly
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError("CSV appears empty or missing header row.")

        if args.id_col not in reader.fieldnames:
            raise KeyError(f"Missing id column '{args.id_col}'. Found: {reader.fieldnames}")
        if args.ssml_col not in reader.fieldnames:
            raise KeyError(f"Missing SSML column '{args.ssml_col}'. Found: {reader.fieldnames}")

        for row in reader:
            row_id = str(row.get(args.id_col, "")).strip()
            if not row_id:
                skipped += 1
                continue

            seen_ids.add(row_id)

            if wanted_ids is not None and row_id not in wanted_ids:
                continue

            ssml = (row.get(args.ssml_col) or "").strip()
            if not ssml:
                skipped += 1
                print(f"Skipping id={row_id}: empty SSML")
                continue

            wav_bytes = synthesize_ssml_wav(
                api_key=args.api_key,
                voice_name=args.voice,
                language_code=args.lang,
                ssml=ssml,
            )

            # Output
            if args.format == "wav" and not args.use_ffmpeg:
                out_path = outdir / f"{row_id}.wav"
                write_direct_wav(wav_bytes, out_path)
                print(f"Wrote {out_path}")
            elif args.format == "wav" and args.use_ffmpeg:
                out_path = outdir / f"{row_id}.wav"
                convert_wav_bytes_with_ffmpeg(wav_bytes, out_path, "wav")
                print(f"Wrote {out_path}")
            else:
                # mp3/ogg: optionally write intermediate wav to disk first (so user can keep it)
                intermediate_wav = outdir / f"{row_id}.wav"
                if args.delete_original_wav:
                    # Don't keep wav on disk: convert from bytes via temp file
                    out_path = outdir / f"{row_id}.{args.format}"
                    convert_wav_bytes_with_ffmpeg(wav_bytes, out_path, args.format, delete_temp=True)
                    print(f"Wrote {out_path} (no intermediate wav kept)")
                else:
                    # Keep intermediate wav on disk
                    write_direct_wav(wav_bytes, intermediate_wav)
                    out_path = outdir / f"{row_id}.{args.format}"
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(intermediate_wav), str(out_path)],
                        check=True,
                    )
                    print(f"Wrote {out_path} (kept {intermediate_wav})")

            generated += 1

    if wanted_ids is not None:
        not_found = sorted(list(wanted_ids - seen_ids))
        if not_found:
            print("\nIDs not found in CSV:", ", ".join(not_found))

    print(f"\nDone. Generated: {generated} | Skipped: {skipped}")


if __name__ == "__main__":
    main()
