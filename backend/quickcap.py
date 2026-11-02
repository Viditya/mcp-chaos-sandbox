"""Windows screen + default playback audio recorder. Python 3.10+.

Install: python -m pip install -r requirements-quickcap.txt
Run: python quickcap.py
"""
import logging
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
import uuid
import wave

# Optional workspace-local installation used by the included launcher.
LOCAL_DEPS = Path(__file__).resolve().parent / '.quickcap-deps'
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))

OUTPUT = Path.home() / 'Videos' / 'Captures'
MAX_SECONDS = 4 * 60 * 60


def hidden():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def ffmpeg_path():
    path = shutil.which('ffmpeg')
    if path:
        return path
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_checked(command, log):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=1800, **hidden())
    with open(log, 'ab') as handle:
        handle.write(result.stdout)
    if result.returncode:
        raise RuntimeError(f'FFmpeg exited with code {result.returncode}. See {log}')
    return result.stdout.decode('utf-8', errors='replace')


class PlaybackAudio:
    """Clocked stereo WAV; reconnects to the default Windows playback endpoint.

    Missing endpoint intervals become silence and are reported, never hidden.
    Audio callbacks only enqueue; file writing stays on this worker thread.
    """
    def __init__(self, path, notify):
        self.path, self.notify = path, notify
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self.work, daemon=True)

    def start(self):
        self.thread.start()
        if not self.ready.wait(12):
            self.stop_event.set()
            raise RuntimeError('Windows playback audio did not initialize in time.')
        if self.error:
            raise RuntimeError(self.error)

    def stop(self):
        self.stop_event.set()
        self.thread.join(12)
        if self.thread.is_alive():
            raise RuntimeError('Audio shutdown timed out; recovery files were kept.')
        if self.error:
            raise RuntimeError(self.error)

    def work(self):
        p = stream = wav = None
        try:
            import numpy as np
            import pyaudiowpatch as pa
            chunks = queue.Queue(maxsize=200)
            wav = wave.open(str(self.path), 'wb')
            wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            pending = bytearray()
            endpoint = None
            next_probe = 0
            started = None
            written = 0
            rate, channels = 48000, 2

            def callback(data, count, timing, status):
                try:
                    chunks.put_nowait(data)
                except queue.Full:
                    pass
                return (None, pa.paContinue)

            while not self.stop_event.is_set():
                now = time.monotonic()
                if now >= next_probe:
                    next_probe = now + 2
                    probe = None
                    try:
                        # New enumeration sees USB/Bluetooth endpoint changes.
                        probe = pa.PyAudio()
                        device = probe.get_default_wasapi_loopback()
                        key = (device['name'], device['defaultSampleRate'],
                               device['maxInputChannels'])
                        if key != endpoint or stream is None or not stream.is_active():
                            if stream:
                                stream.close()
                                stream = None
                            if p:
                                p.terminate()
                            p, probe = probe, None
                            rate = int(device['defaultSampleRate'])
                            channels = int(device['maxInputChannels'])
                            while not chunks.empty():
                                chunks.get_nowait()
                            stream = p.open(format=pa.paInt16, channels=channels,
                                            rate=rate, input=True,
                                            input_device_index=int(device['index']),
                                            frames_per_buffer=1024,
                                            stream_callback=callback)
                            endpoint = key
                            self.notify('Audio: ' + device['name'])
                    except Exception as exc:
                        logging.warning('Playback endpoint unavailable: %s', exc)
                        if started is None:
                            raise RuntimeError(f'Cannot open playback audio: {exc}') from exc
                        self.notify('Audio reconnecting; gap will be silent')
                        if stream:
                            stream.close()
                            stream = None
                        endpoint = None
                    finally:
                        if probe:
                            probe.terminate()
                    if started is None:
                        started = time.monotonic()
                        self.ready.set()
                while not chunks.empty():
                    samples = np.frombuffer(chunks.get_nowait(), dtype=np.int16)
                    samples = samples.reshape(-1, channels)
                    stereo = np.repeat(samples, 2, axis=1) if channels == 1 else samples[:, :2]
                    if rate != 48000:
                        count = round(len(stereo) * 48000 / rate)
                        positions = np.arange(count) * rate / 48000
                        stereo = np.column_stack([np.interp(positions, np.arange(len(stereo)),
                                                            stereo[:, c]) for c in range(2)])
                    pending.extend(stereo.astype('<i2').tobytes())
                # A small buffer absorbs callback jitter; silence preserves time
                # when Windows produces no loopback packets during quiet periods.
                target = max(0, int((time.monotonic() - started - .15) * 48000))
                needed = (target - written) * 4
                if needed > 0:
                    data = bytes(pending[:needed])
                    del pending[:needed]
                    wav.writeframesraw(data + bytes(needed - len(data)))
                    written = target
                if len(pending) > 48000 * 4:
                    del pending[:-48000 * 4]
                self.stop_event.wait(.02)
        except Exception as exc:
            logging.exception('Audio worker failed')
            self.error = str(exc)
            self.ready.set()
        finally:
            if stream:
                stream.close()
            if p:
                p.terminate()
            if wav:
                wav.close()


class Recorder:
    """UI-independent engine; suitable for a later MCP wrapper."""
    def __init__(self, notify=lambda text: None):
        self.notify = notify
        self.ffmpeg = ffmpeg_path()
        OUTPUT.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y-%m-%d_%H-%M-%S') + '_' + uuid.uuid4().hex[:6]
        self.folder = OUTPUT / ('Recovery_' + stamp)
        self.folder.mkdir()
        self.final = OUTPUT / ('Capture_' + stamp + '.mp4')
        self.log = self.folder / 'ffmpeg.log'
        self.parts = []
        self.process = self.audio = self.handle = None

    def start_segment(self, audio=True):
        index = len(self.parts)
        self.video = self.folder / f'{index:04d}.mkv'
        self.wav = self.folder / f'{index:04d}.wav'
        self.audio = PlaybackAudio(self.wav, self.notify) if audio else None
        try:
            if self.audio:
                self.audio.start()
            self.handle = open(self.log, 'ab', buffering=0)
            command = [self.ffmpeg, '-hide_banner', '-y', '-thread_queue_size', '512',
                       '-f', 'gdigrab', '-framerate', '15', '-draw_mouse', '1',
                       '-i', 'desktop', '-an', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
                       '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
                       '-pix_fmt', 'yuv420p', '-r', '15', str(self.video)]
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                            stdout=subprocess.DEVNULL, stderr=self.handle,
                                            **hidden())
            time.sleep(.8)
            if self.process.poll() is not None:
                raise RuntimeError(f'Screen capture could not start. See {self.log}')
        except Exception:
            self.stop_segment()
            raise

    def stop_segment(self):
        error = None
        process, self.process = self.process, None
        if process:
            try:
                if process.poll() is None:
                    process.stdin.write(b'q\n')
                    process.stdin.flush()
                process.wait(timeout=20)
                if process.returncode:
                    error = RuntimeError(f'Screen recording exited with code {process.returncode}. See {self.log}')
            except (OSError, subprocess.TimeoutExpired) as exc:
                process.kill()
                process.wait()
                error = RuntimeError(f'Recording did not close cleanly: {exc}. Recovery: {self.folder}')
            finally:
                process.stdin.close()
        if self.audio:
            try:
                self.audio.stop()
            except Exception as exc:
                error = error or exc
            self.audio = None
        if self.handle:
            self.handle.close()
            self.handle = None
        if process and self.video.exists() and self.video.stat().st_size > 0:
            self.parts.append((self.video, self.wav if self.wav.exists() else None))
        if error:
            raise error

    def save(self):
        if not self.parts:
            raise RuntimeError(f'No recording segments. Diagnostics: {self.log}')
        normalized = []
        for index, (video, audio) in enumerate(self.parts):
            probe = subprocess.run([self.ffmpeg, '-hide_banner', '-i', str(video)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=30, **hidden())
            metadata = probe.stderr.decode('utf-8', errors='replace')
            match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', metadata)
            if not match:
                raise RuntimeError(f'Cannot determine segment duration: {video}. Recovery files kept.')
            hours, minutes, seconds = map(float, match.groups())
            duration = hours * 3600 + minutes * 60 + seconds
            if duration <= 0:
                raise RuntimeError(f'Empty video segment: {video}')
            target = self.folder / f'part_{index:04d}.mp4'
            command = [self.ffmpeg, '-hide_banner', '-y', '-i', str(video)]
            command += ['-i', str(audio)] if audio else ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
            command += ['-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
                        '-af', 'apad', '-c:a', 'aac', '-ar', '48000', '-ac', '2',
                        '-b:a', '160k', '-t', str(duration), str(target)]
            run_checked(command, self.log)
            normalized.append(target)
        manifest = self.folder / 'concat.txt'
        manifest.write_text(''.join(f"file '{p.name}'\n" for p in normalized), encoding='utf-8')
        temporary = self.folder / 'assembled.mp4'
        run_checked([self.ffmpeg, '-hide_banner', '-y', '-f', 'concat', '-safe', '0',
                     '-i', str(manifest), '-c', 'copy', '-movflags', '+faststart',
                     str(temporary)], self.log)
        # Decode both streams, rather than trusting file size or extension.
        run_checked([self.ffmpeg, '-hide_banner', '-v', 'error', '-xerror',
                     '-i', str(temporary), '-map', '0:v:0', '-map', '0:a:0',
                     '-f', 'null', '-'], self.log)
        temporary.replace(self.final)
        return self.final


class QuickCap:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.recorder = None
        self.state = 'idle'
        self.busy = False
        self.closing = False
        self.destroyed = False
        self.elapsed = 0
        root.title('QuickCap')
        root.attributes('-topmost', True)
        root.resizable(False, False)
        root.configure(bg='#181818')
        bar = tk.Frame(root, bg='#181818')
        bar.pack(padx=8, pady=6)
        self.record = tk.Button(bar, text='● REC', width=10, command=self.toggle)
        self.record.pack(side='left', padx=3)
        self.pause = tk.Button(bar, text='Ⅱ PAUSE', width=11, state='disabled', command=self.toggle_pause)
        self.pause.pack(side='left', padx=3)
        self.audio_var = tk.BooleanVar(value=True)
        self.audio = tk.Checkbutton(bar, text='System audio', variable=self.audio_var)
        self.audio.pack(side='left', padx=3)
        self.timer = tk.Label(bar, text='00:00:00', bg='#181818', fg='white', width=10)
        self.timer.pack(side='left')
        self.status = tk.Label(root, text='Ready — captions must be visible on screen',
                               bg='#181818', fg='#dddddd', wraplength=520)
        self.status.pack(padx=8, pady=(0, 6))
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.last_tick = time.monotonic()
        self.poll()

    def background(self, action, success):
        self.busy = True
        self.record.config(state='disabled')
        self.pause.config(state='disabled')
        self.audio.config(state='disabled')
        def worker():
            try:
                result = action()
                self.events.put(('done', (success, result)))
            except Exception as exc:
                logging.exception('Recorder action failed')
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def toggle(self):
        if self.busy:
            return
        if self.state == 'idle':
            audio = self.audio_var.get()
            def start():
                self.recorder = Recorder(lambda text: self.events.put(('status', text)))
                self.recorder.start_segment(audio)
            self.elapsed = 0
            self.background(start, lambda _: self.set_state('recording'))
        else:
            self.stop()

    def toggle_pause(self):
        if self.busy:
            return
        if self.state == 'recording':
            self.set_state('paused')
            self.background(self.recorder.stop_segment, lambda _: self.set_state('paused'))
        elif self.state == 'paused':
            audio = self.audio_var.get()
            self.background(lambda: self.recorder.start_segment(audio),
                            lambda _: self.set_state('recording'))

    def stop(self):
        active = self.state == 'recording'
        self.set_state('saving')
        self.status.config(text='Saving and checking video/audio…')
        def finish():
            if active:
                self.recorder.stop_segment()
            return self.recorder.save()
        self.background(finish, self.saved)

    def saved(self, path):
        self.set_state('idle')
        self.status.config(text=f'Saved: {path}')
        if self.closing:
            self.destroyed = True
            self.root.destroy()

    def set_state(self, state):
        self.state = state
        self.last_tick = time.monotonic()
        self.record.config(text='● REC' if state == 'idle' else '■ STOP', state='normal')
        self.pause.config(text='▶ RESUME' if state == 'paused' else 'Ⅱ PAUSE',
                          state='normal' if state in ('paused', 'recording') else 'disabled')
        self.audio.config(state='normal' if state == 'idle' else 'disabled')

    def poll(self):
        now = time.monotonic()
        if self.state == 'recording':
            self.elapsed += now - self.last_tick
        self.last_tick = now
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'status':
                self.status.config(text=value)
            elif kind == 'done':
                self.busy = False
                callback, result = value
                callback(result)
                if self.destroyed:
                    return
            elif kind == 'error':
                self.busy = False
                self.closing = False
                self.set_state('idle')
                self.status.config(text='Error — recovery files kept')
                messagebox.showerror('QuickCap', value)
        if self.state == 'recording' and not self.busy:
            if self.recorder.process.poll() is not None or (self.recorder.audio and self.recorder.audio.error):
                self.stop()
            elif self.elapsed >= MAX_SECONDS:
                self.stop()
        seconds = int(self.elapsed)
        self.timer.config(text=f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}')
        if self.root.winfo_exists():
            self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            self.status.config(text='Please wait for the current operation, then close again.')
        elif self.state in ('recording', 'paused'):
            self.closing = True
            self.stop()
        else:
            self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    QuickCap(root)
    root.mainloop()
