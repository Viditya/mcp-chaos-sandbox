from __future__ import annotations

import os
import math
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


TARGET_BYTES = 90_000_000
MAX_BYTES = 95_000_000
MIN_SPLIT_SECONDS = 0.5
MAX_SIZE_ATTEMPTS = 12


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


def is_temp_file(path: Path) -> bool:
    return (
        path.is_file()
        and path.name.startswith(".video_chunk_")
        and path.suffix.lower() == ".mp4"
    )


def prepare_output_folder(source: Path) -> Path:
    original_name_folder = source.parent / source.stem
    original_name_folder.mkdir(parents=True, exist_ok=True)

    entries = list(original_name_folder.iterdir())
    stale_temps = [path for path in entries if is_temp_file(path)]
    other_files = [path for path in entries if path not in stale_temps]

    if not other_files:
        if stale_temps:
            print(f"\nFound abandoned temporary files in:\n{original_name_folder}")
            for path in stale_temps:
                print(f"  {path.name}")

            answer = input("Delete only these temporary files? [y/N] ")
            if answer.strip().lower() != "y":
                raise RuntimeError("Cancelled; no files were changed.")

            for path in stale_temps:
                path.unlink()

        return original_name_folder

    # Keep existing chunks untouched; use a separate folder for the new set.
    output_dir = source.parent / f"{source.stem}_90MB"
    output_dir.mkdir(parents=True, exist_ok=True)

    if any(output_dir.iterdir()):
        raise RuntimeError(
            f"The new output folder already contains files; nothing was "
            f"overwritten:\n{output_dir}"
        )

    print(f"\nPreserving existing files in:\n{original_name_folder}")
    print(f"Writing the new ~90 MB chunks to:\n{output_dir}")
    return output_dir


def run_encode_trial(
    source: Path,
    output_dir: Path,
    start: float,
    duration: float,
) -> tuple[Path, int]:
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

        return temp_path, temp_path.stat().st_size
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def encode_chunk_near_target(
    source: Path,
    output_dir: Path,
    start: float,
    remaining: float,
    initial_duration: float,
    chunk_number: int,
) -> tuple[Path, float, int]:
    candidate_duration = min(initial_duration, remaining)
    candidate_duration = max(
        min(MIN_SPLIT_SECONDS, remaining),
        candidate_duration,
    )

    for _ in range(MAX_SIZE_ATTEMPTS):
        temp_path, size = run_encode_trial(
            source,
            output_dir,
            start,
            candidate_duration,
        )

        if size > MAX_BYTES:
            temp_path.unlink(missing_ok=True)

            if candidate_duration <= MIN_SPLIT_SECONDS:
                raise RuntimeError(
                    f"Could not get chunk {chunk_number} below 95 MB."
                )

            # Reduce duration according to the measured encoded size.
            candidate_duration *= TARGET_BYTES / size * 0.98
            candidate_duration = max(
                min(MIN_SPLIT_SECONDS, remaining),
                min(candidate_duration, remaining),
            )
            continue

        # If this is not the final piece and it is well below target,
        # try a longer duration.
        if (
            size < TARGET_BYTES * 0.90
            and candidate_duration < remaining - 0.05
        ):
            larger_duration = min(
                remaining,
                candidate_duration * TARGET_BYTES / max(size, 1) * 0.98,
            )

            if larger_duration > candidate_duration * 1.05:
                temp_path.unlink(missing_ok=True)
                candidate_duration = larger_duration
                continue

        return temp_path, candidate_duration, size

    raise RuntimeError(
        f"Could not find a safe chunk size after {MAX_SIZE_ATTEMPTS} attempts "
        f"for {source.name}. No original files were changed."
    )


def split_video(source: Path) -> None:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    duration = get_duration(source)
    output_dir = prepare_output_folder(source)

    # Starting estimate only; each trial is adjusted using its actual size.
    first_guess = duration * min(
        1.0,
        TARGET_BYTES / max(source.stat().st_size, 1),
    )
    first_guess = max(min(MIN_SPLIT_SECONDS, duration), first_guess)

    print(f"\nProcessing: {source.name}")
    print(f"Output folder: {output_dir}")

    start = 0.0
    chunk_number = 1
    next_guess = first_guess

    while start < duration - 0.01:
        remaining = duration - start

        temp_path, piece_duration, size = encode_chunk_near_target(
            source=source,
            output_dir=output_dir,
            start=start,
            remaining=remaining,
            initial_duration=next_guess,
            chunk_number=chunk_number,
        )

        final_path = output_dir / f"chunk_{chunk_number:03d}.mp4"
        temp_path.replace(final_path)

        print(f"  {final_path.name}: {size / 1_000_000:.1f} MB")

        start += piece_duration
        next_guess = piece_duration
        chunk_number += 1

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

    print("\nDone. Original videos and existing chunks were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
