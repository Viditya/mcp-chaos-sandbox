import os
from pathlib import Path
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox

# Output Directory: Videos/Captures
OUTPUT_DIR = Path.home() / "Videos" / "Captures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = Path(__file__).resolve().parent / "ffmpeg_error.log"

MAX_RECORDING_SECONDS = 4 * 60 * 60  # 4 Hours hard limit


def get_hidden_startupinfo():
  si = subprocess.STARTUPINFO()
  si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
  si.wShowWindow = subprocess.SW_HIDE
  return si


class QuickCap:

  def __init__(self, root: tk.Tk):
    self.root = root
    self.root.title("QuickCap")
    self.root.geometry("320x54+60+60")
    self.root.overrideredirect(True)
    self.root.wm_attributes("-topmost", True)
    self.root.wm_attributes("-alpha", 0.95)
    self.root.config(bg="#181818")

    self.process = None
    self.is_recording = False
    self.start_time = 0
    self.temp_mkv = None
    self.final_mp4 = None

    # Dragging logic
    self._offset_x = 0
    self._offset_y = 0
    self.root.bind("<Button-1>", self._click_window)
    self.root.bind("<B1-Motion>", self._drag_window)

    self._build_ui()

  def _build_ui(self):
    self.drag_grip = tk.Label(
        self.root, text="⋮⋮", fg="#666666", bg="#181818", cursor="fleur"
    )
    self.drag_grip.pack(side=tk.LEFT, padx=(8, 4))

    # REC / STOP Button
    self.record_btn = tk.Button(
        self.root,
        text="● REC",
        bg="#e53935",
        fg="white",
        activebackground="#b71c1c",
        activeforeground="white",
        font=("Segoe UI", 9, "bold"),
        relief=tk.FLAT,
        padx=12,
        pady=3,
        command=self.toggle_recording,
    )
    self.record_btn.pack(side=tk.LEFT, padx=4)

    # Timer Label
    self.timer_label = tk.Label(
        self.root,
        text="00:00:00",
        fg="#dddddd",
        bg="#181818",
        font=("Consolas", 10),
    )
    self.timer_label.pack(side=tk.LEFT, padx=6)

    # Close Button
    self.close_btn = tk.Button(
        self.root,
        text="✕",
        bg="#181818",
        fg="#777777",
        activebackground="#2a2a2a",
        activeforeground="white",
        relief=tk.FLAT,
        font=("Segoe UI", 9),
        command=self._exit_app,
    )
    self.close_btn.pack(side=tk.RIGHT, padx=(0, 8))

  def _click_window(self, event):
    self._offset_x = event.x
    self._offset_y = event.y

  def _drag_window(self, event):
    x = self.root.winfo_pointerx() - self._offset_x
    y = self.root.winfo_pointery() - self._offset_y
    self.root.geometry(f"+{x}+{y}")

  def toggle_recording(self):
    if not self.is_recording:
      self.start_recording()
    else:
      self.stop_recording()

  def start_recording(self):
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    self.temp_mkv = OUTPUT_DIR / f"_temp_{timestamp}.mkv"
    self.final_mp4 = OUTPUT_DIR / f"Capture_{timestamp}.mp4"

    # Clean, bulletproof screen capture command (Zero audio driver dependencies)
    cmd = [
        "ffmpeg",
        "-y",
        "-use_wallclock_as_timestamps",
        "1",
        "-f",
        "gdigrab",
        "-framerate",
        "15",
        "-draw_mouse",
        "1",
        "-i",
        "desktop",
        "-vf",
        "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-level",
        "4.0",
        "-preset",
        "ultrafast",
        "-crf",
        "24",
        "-pix_fmt",
        "yuv420p",
        str(self.temp_mkv),
    ]

    try:
      with open(LOG_FILE, "w") as log:
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=log,
            startupinfo=get_hidden_startupinfo(),
        )

      self.is_recording = True
      self.start_time = time.time()
      self.record_btn.config(text="■ STOP", bg="#212121")
      self._update_timer()
    except Exception as e:
      messagebox.showerror("Error", f"Failed to start FFmpeg: {e}")

  def _update_timer(self):
    if self.is_recording:
      elapsed = int(time.time() - self.start_time)
      if elapsed >= MAX_RECORDING_SECONDS:
        self.stop_recording()
        return

      mins, secs = divmod(elapsed, 60)
      hrs, mins = divmod(mins, 60)
      self.timer_label.config(
          text=f"{hrs:02d}:{mins:02d}:{secs:02d}", fg="#dddddd"
      )
      self.root.after(1000, self._update_timer)

  def stop_recording(self):
    if not self.is_recording or not self.process:
      return

    self.record_btn.config(text="Saving...", state=tk.DISABLED)
    self.root.update()

    def _finalize():
      try:
        if self.process.stdin:
          self.process.stdin.write(b"q\r\n")
          self.process.stdin.flush()
        self.process.wait(timeout=5)
      except Exception:
        self.process.terminate()
        try:
          self.process.wait(timeout=2)
        except Exception:
          self.process.kill()

      # Remux MKV -> Playable MP4 with FastStart
      if (
          self.temp_mkv
          and self.temp_mkv.exists()
          and self.temp_mkv.stat().st_size > 1024
      ):
        remux_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(self.temp_mkv),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(self.final_mp4),
        ]
        subprocess.run(
            remux_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=get_hidden_startupinfo(),
        )
        if (
            self.final_mp4.exists()
            and self.final_mp4.stat().st_size > 1024
        ):
          try:
            self.temp_mkv.unlink()
          except Exception:
            pass

      self.is_recording = False
      self.root.after(0, self._on_stopped)

    threading.Thread(target=_finalize, daemon=True).start()

  def _on_stopped(self):
    self.record_btn.config(text="● REC", bg="#e53935", state=tk.NORMAL)

    target = (
        self.final_mp4
        if (self.final_mp4 and self.final_mp4.exists())
        else self.temp_mkv
    )
    if target and target.exists() and target.stat().st_size > 1024:
      size_mb = target.stat().st_size / (1024 * 1024)
      self.timer_label.config(text=f"{size_mb:.1f} MB", fg="#81c784")
      subprocess.run(["explorer", f"/select,{str(target)}"])
    else:
      self.timer_label.config(text="Failed", fg="#e53935")
      if LOG_FILE.exists():
        os.startfile(LOG_FILE)

  def _exit_app(self):
    if self.is_recording:
      self.stop_recording()
      self.root.after(1200, self.root.destroy)
    else:
      self.root.destroy()


if __name__ == "__main__":
  app = tk.Tk()
  recorder = QuickCap(app)
  app.mainloop()
