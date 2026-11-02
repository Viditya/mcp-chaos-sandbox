from __future__ import annotations

import os
import math
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


MAX_CHUNK_BYTES = 95_000_000
TARGET_CHUNK_BYTES = 85_000_000
MIN_SPLIT_SECONDS = 0.5


def choose_videos() -> list[Path]:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    selected = filedialog.askopenfilenames(
        title="Select only the videos to split",
        filetypes=[
            ("Video files", "*.mp4 *.mov *.mkv *.webm *.avi"),
            ("All files", "*.*"),
        ],
    )

    root.destroy()
    return [Path(path) for path in selected]


def get_duration(video: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    duration = float(result.stdout.strip())
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"Could not determine duration: {video}")

    return duration


def prepare_output_folder(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = list(output_dir.iterdir())

    stale_temps = [
        path for path in existing
        if path.is_file()
        and path.name.startswith(".video_chunk_")
        and path.suffix.lower() == ".mp4"
    ]
    other_files = [path for path in existing if path not in stale_temps]

    if other_files:
        names = ", ".join(path.name for path in other_files[:5])
        raise RuntimeError(
            f"Output folder already contains files; nothing was overwritten:\n"
            f"{output_dir}\n"
            f"Existing: {names}"
        )

    if stale_temps:
        print(f"\nFound abandoned temporary file(s) in:\n{output_dir}")
        for path in stale_temps:
            print(f"  {path.name}")

        answer = input("Delete only these temporary files and continue? [y/N] ")
        if answer.strip().lower() != "y":
            raise RuntimeError("Cancelled; no files were changed.")

        for path in stale_temps:
            path.unlink()


def encode_piece(
    source: Path,
    output_dir: Path,
    start: float,
    duration: float,
    next_number: int,
) -> int:
    # UUID filenames avoid collisions; no open temporary-file handle is kept.
    temp_path = output_dir / f".video_chunk_{uuid.uuid4().hex}.mp4"

    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{start:.6f}",
        "-i", str(source),
        "-t", f"{duration:.6f}",
        "-map", "0:v:0",
        "-map", "0:a?",
        "-sn",
        "-dn",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(temp_path),
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0 or not temp_path.exists():
            detail = result.stderr.strip()[-2000:]
            raise RuntimeError(f"FFmpeg failed for {source.name}:\n{detail}")

        size = temp_path.stat().st_size

        if size <= MAX_CHUNK_BYTES:
            final_path = output_dir / f"chunk_{next_number:03d}.mp4"
            temp_path.replace(final_path)
            print(f"  {final_path.name}: {size / 1_000_000:.1f} MB")
            return next_number + 1

        if duration <= MIN_SPLIT_SECONDS:
            raise RuntimeError(
                f"Could not make a piece smaller than 95 MB near "
                f"{start:.2f} seconds in {source.name}."
            )

        print(
            f"  Piece was {size / 1_000_000:.1f} MB; "
            "splitting it into smaller pieces."
        )

    finally:
        # Remove only this run's temporary file, never completed chunks.
        temp_path.unlink(missing_ok=True)

    first_duration = duration / 2
    next_number = encode_piece(
        source, output_dir, start, first_duration, next_number
    )
    return encode_piece(
        source,
        output_dir,
        start + first_duration,
        duration - first_duration,
        next_number,
    )


def split_video(source: Path) -> None:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    output_dir = source.parent / source.stem
    prepare_output_folder(output_dir)

    duration = get_duration(source)
    estimated_parts = max(
        1,
        math.ceil(source.stat().st_size / TARGET_CHUNK_BYTES),
    )
    estimated_duration = duration / estimated_parts

    print(f"\nProcessing: {source.name}")
    print(f"Output folder: {output_dir}")

    chunk_number = 1
    for part in range(estimated_parts):
        start = part * estimated_duration
        piece_duration = min(estimated_duration, duration - start)

        if piece_duration > 0:
            chunk_number = encode_piece(
                source,
                output_dir,
                start,
                piece_duration,
                chunk_number,
            )

    print(f"Finished: {chunk_number - 1} chunk(s).")


def main() -> int:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("FFmpeg and ffprobe must be installed and available on PATH.")
        return 1

    try:
        videos = (
            [Path(arg) for arg in sys.argv[1:]]
            if len(sys.argv) > 1
            else choose_videos()
        )

        if not videos:
            print("No videos selected.")
            return 0

        for video in videos:
            split_video(video)

    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    print("\nDone. Original videos were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
