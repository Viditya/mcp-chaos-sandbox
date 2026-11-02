# QuickCap

Run **Start QuickCap.cmd**. If dependencies are missing, install them using:

    python -m pip install --target .quickcap-deps -r requirements-quickcap.txt

Python 3.10 or newer on Windows is required. FFmpeg is supplied by imageio-ffmpeg when it is not on PATH.

Press REC, PAUSE / RESUME, then STOP. Closing during a recording stops and saves it; closing while an operation is running asks you to wait. The timer excludes pauses. Captures stop after four recorded hours.

Audio means **system playback audio**, including Chrome, rather than the microphone. Keep Chrome on the Windows default playback device. Poly headphones and built-in speakers are supported through their Windows WASAPI loopback endpoints. The recorder checks the default endpoint every two seconds. Device changes can leave a short silent gap; unplugged or unavailable devices cannot produce audio. These gaps are reported in the status line. Other applications' audio playing through the same endpoint is also captured. The Audio checkbox deliberately permits silent recording.

Chrome captions must already be enabled and visible. The entire desktop is recorded, including visible captions and the recorder window. Captions are embedded in the video image, not exported as a separate transcript. Protected video surfaces may appear black.

Results are saved under your Windows **Videos/Captures** folder as H.264/AAC MP4. Each save is decoded to check for errors before the final MP4 is published. Large recordings can take time to check. Recovery folders retain the source MKV/WAV segments and ffmpeg.log, even after success; remove them manually when you no longer need them. They can use substantial disk space. Do not delete them while saving.

The Recorder class is independent of Tk and can be wrapped by a future MCP tool. It does not yet send files to Gemini or expose an MCP server. A caller should serialize start_segment, stop_segment, and save calls.
