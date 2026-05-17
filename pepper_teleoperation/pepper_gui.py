# -*- coding: utf-8 -*-
"""
pepper_gui.py - Pepper Teleoperation Control Panel (Modernized)
================================================================
Python 3 / tkinter rewrite of the original legacy GUI.
- Dark theme (deep navy / slate surface / electric-blue accents)
- Segoe UI font - no pyglet dependency
- Grid layout: Connection column | Body + Pepper feeds (side by side) | compact log below feeds
- Session mode badge: IDLE / MIRRORING / DRIVING
- All original control logic preserved (SpeechThread, OkPepperThread,
  PepperApproachControl, voice commands)
- 3-second countdown overlay on Start Moving
- Test Move (Fwd) diagnostic button
"""

try:
    import Tkinter as tk
    import ttk
    import tkFont as tkfont
except ImportError:
    import tkinter as tk
    from tkinter import ttk, font as tkfont
import argparse
import sys
import os
import subprocess
import qi
import json
import webbrowser
import numpy as np
try:
    from Queue import Queue, Empty, Full
except ImportError:
    from queue import Queue, Empty, Full
import threading
import time
import zmq
try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
    try:
        _RESAMPLE_FAST = Image.Resampling.BILINEAR
        _RESAMPLE_PIXEL = Image.Resampling.NEAREST
    except AttributeError:
        _RESAMPLE_FAST = Image.BILINEAR
        _RESAMPLE_PIXEL = Image.NEAREST
except ImportError:
    PIL_AVAILABLE = False
    _RESAMPLE_FAST = None
    _RESAMPLE_PIXEL = None

from GUI_material.image_label import ImageLabel
from utils.speech_thread import SpeechThread
from utils.ok_pepper_thread import OkPepperThread
from utils.pepper_approach_control_thread import PepperApproachControl

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
BG          = "#0d1117"   # window / page background
SURFACE     = "#161b22"   # card / panel background
SURFACE_2   = "#21262d"   # subtle raised surface (inputs, hover)
BORDER      = "#30363d"   # dividers and card borders
ACCENT      = "#388bfd"   # primary blue
ACCENT_DARK = "#1f6feb"   # pressed / darker accent
SUCCESS     = "#3fb950"   # green  - Connected / MIRRORING
WARNING     = "#d29922"   # amber  - DRIVING
DANGER      = "#f85149"   # red    - error states
TEXT_PRI    = "#e6edf3"   # primary text
TEXT_SEC    = "#8b949e"   # secondary / muted text

FONT_BODY   = ("Segoe UI", 11)
FONT_LABEL  = ("Segoe UI", 10)
FONT_SMALL  = ("Segoe UI", 9)
FONT_BOLD   = ("Segoe UI", 11, "bold")
FONT_H1     = ("Segoe UI", 14, "bold")
FONT_MONO   = ("Consolas", 9)

PAD         = 10

# Keep GUI lightweight/reliable: no embedded video previews in Tk.
# Gesture control still works because MediaPipe tracker publishes keypoints
# independently on tcp://127.0.0.1:1234.
EMBED_PREVIEWS_IN_GUI = False

# GUI-side Pepper preview toggle.
ENABLE_PEPPER_CAMERA_IN_GUI = False
# Keep Pepper camera subscription active for Unity (/pepper.jpg) even when GUI
# preview is disabled.
ENABLE_PEPPER_STREAM_SERVER = True

# Primary camera shown in GUI + default /pepper.jpg VR stream (forehead).
PEPPER_CAMERA_INDEX = 0   # 0 = top/forehead, 1 = bottom/mouth
PEPPER_CAM_SUB_NAME = "pepper_gui_camera"

# Extra Pepper cameras for VR (each gets its own subscribeCamera + HTTP path).
# Index 2 = depth sensor on standard Pepper; NAOqi often exposes it as 320x240 + color space 11.
PEPPER_VR_EXTRA_STREAMS = (
    {"name": "bottom", "camera": 1, "mode": "rgb"},
    {"name": "depth", "camera": 2, "mode": "depth_u16"},
)

# Arm mapping mode for MediaPipe arm control:
# True  -> one-to-one (your right arm -> Pepper right arm)
# False -> mirrored  (your right arm -> Pepper left arm)
ARM_ONE_TO_ONE_MAPPING = True

# If True, launching pepper_gui.py directly will also spawn the MediaPipe tracker
# (Python 3) so the operator webcam arm mirroring works without the .bat wrapper.
AUTO_START_MEDIAPIPE_TRACKER = True
TRACKER_PY_CANDIDATES = (
    ["py", "-3.10"],
    ["py", "-3"],
)


def _yuyv_to_rgb_numpy(buf, w, h):
    """UYVY/YUY2 packed 4:2:2 -> RGB uint8 (h, w, 3). buf is length w*h*2."""
    arr = np.asarray(buf, dtype=np.uint8).ravel()
    if arr.size != w * h * 2:
        return None
    yuyv = arr.reshape(h, w // 2, 4)
    y0 = yuyv[:, :, 0].astype(np.float32)
    u = yuyv[:, :, 1].astype(np.float32) - 128.0
    y1 = yuyv[:, :, 2].astype(np.float32)
    v = yuyv[:, :, 3].astype(np.float32) - 128.0
    r0 = y0 + 1.402 * v
    g0 = y0 - 0.344136 * u - 0.714136 * v
    b0 = y0 + 1.772 * u
    r1 = y1 + 1.402 * v
    g1 = y1 - 0.344136 * u - 0.714136 * v
    b1 = y1 + 1.772 * u
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    rgb[:, 0::2, 0] = r0
    rgb[:, 1::2, 0] = r1
    rgb[:, 0::2, 1] = g0
    rgb[:, 1::2, 1] = g1
    rgb[:, 0::2, 2] = b0
    rgb[:, 1::2, 2] = b1
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _blob_to_rgb_image(w, h, raw):
    """Build PIL Image RGB from NAOqi buffer (RGB888 or YUYV 422)."""
    if raw is None:
        return None
    if isinstance(raw, list):
        arr = np.asarray(raw, dtype=np.uint8).ravel()
    else:
        arr = np.frombuffer(raw, dtype=np.uint8) if hasattr(np, "frombuffer") else np.asarray(bytearray(raw), dtype=np.uint8)
    n = arr.size
    if n == w * h * 3:
        try:
            return Image.frombytes("RGB", (w, h), arr.tostring() if hasattr(arr, "tostring") else arr.tobytes())
        except Exception:
            try:
                return Image.fromstring("RGB", (w, h), arr.tostring() if hasattr(arr, "tostring") else arr.tobytes())
            except Exception:
                return None
    if n == w * h * 2:
        rgb = _yuyv_to_rgb_numpy(arr, w, h)
        if rgb is None:
            return None
        return Image.fromarray(rgb, mode="RGB")
    return None


def _pepper_raw_to_pil(w, h, raw, mode):
    """
    Convert NAOqi getImageRemote buffer to RGB PIL Image.
    mode: 'rgb' (uint8 HWC) or 'depth_u16' (try uint16 depth mm -> grayscale RGB).
    """
    if raw is None or w <= 0 or h <= 0:
        return None
    if isinstance(raw, list):
        raw = bytes(bytearray(raw))
    try:
        if mode == "rgb":
            arr = np.frombuffer(raw, dtype=np.uint8)
            if arr.size == w * h * 3:
                return Image.fromarray(arr.reshape(h, w, 3), "RGB")
        elif mode == "depth_u16":
            arr = np.frombuffer(raw, dtype=np.uint16)
            if arr.size == w * h:
                d = arr.reshape(h, w).astype(np.float32)
                valid = d[d > 0]
                if valid.size == 0:
                    return Image.fromarray(np.zeros((h, w, 3), dtype=np.uint8), "RGB")
                if hasattr(np, "percentile"):
                    d_hi = float(np.percentile(valid, 99))
                else:
                    d_hi = float(valid.max())
                d_lo = float(valid.min())
                span = max(d_hi - d_lo, 1.0)
                norm = np.clip((d - d_lo) / span, 0.0, 1.0) * 255.0
                g = norm.astype(np.uint8)
                rgb = np.stack([g, g, g], axis=2)
                return Image.fromarray(rgb, "RGB")
    except Exception:
        pass
    return _blob_to_rgb_image(w, h, raw)


# ---------------------------------------------------------------------------
# Utility widgets
# ---------------------------------------------------------------------------
class Card(tk.Frame):
    """A rounded-looking dark card (Frame with border colouring)."""
    def __init__(self, parent, **kwargs):
        tk.Frame.__init__(self, parent,
                          bg=SURFACE,
                          highlightbackground=BORDER,
                          highlightthickness=1,
                          **kwargs)


class StatusBadge(tk.Label):
    """
    Coloured dot + text badge for connection / mode state.
    Call .set_state("IDLE" | "CONNECTED" | "MIRRORING" | "DRIVING" | "ERROR")
    """
    _STATES = {
        "IDLE":      (TEXT_SEC,  "* IDLE"),
        "CONNECTED": (SUCCESS,   "* CONNECTED"),
        "MIRRORING": (SUCCESS,   "* MIRRORING"),
        "DRIVING":   (WARNING,   "* DRIVING"),
        "ERROR":     (DANGER,    "* ERROR"),
    }

    def __init__(self, parent, **kwargs):
        tk.Label.__init__(self, parent,
                          font=FONT_BOLD,
                          bg=SURFACE,
                          **kwargs)
        self.set_state("IDLE")

    def set_state(self, state):
        colour, label = self._STATES.get(state, (TEXT_SEC, "* " + state))
        self.configure(fg=colour, text=label)


class ModernButton(tk.Button):
    def __init__(self, parent, text="", accent=False, danger=False, **kwargs):
        fg_col  = "white"
        if danger:
            bg_col     = DANGER
            active_col = "#b91c1c"
        elif accent:
            bg_col     = ACCENT
            active_col = ACCENT_DARK
        else:
            bg_col     = SURFACE_2
            active_col = BORDER

        tk.Button.__init__(self, parent,
                           text=text,
                           bg=bg_col,
                           fg=fg_col,
                           activebackground=active_col,
                           activeforeground=fg_col,
                           font=FONT_BODY,
                           relief=tk.FLAT,
                           cursor="hand2",
                           padx=12,
                           pady=6,
                           disabledforeground=TEXT_SEC,
                           **kwargs)


class LogText(tk.Frame):
    """Scrollable log panel."""
    def __init__(self, parent, height_lines=8, **kwargs):
        tk.Frame.__init__(self, parent, bg=SURFACE, **kwargs)
        self.text = tk.Text(self,
                            bg=SURFACE,
                            fg=TEXT_SEC,
                            font=FONT_MONO,
                            relief=tk.FLAT,
                            state=tk.DISABLED,
                            wrap=tk.WORD,
                            bd=0,
                            height=height_lines)
        # Let mouse wheel scroll this log only; main window uses outer scroll.
        self.text._pepper_skip_outer_scroll = True
        sb = tk.Scrollbar(self, command=self.text.yview,
                          bg=SURFACE_2, troughcolor=BG, relief=tk.FLAT, width=8)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def append(self, msg, colour=None):
        ts = time.strftime("%H:%M:%S")
        line = "[%s] %s\n" % (ts, msg)
        self.text.configure(state=tk.NORMAL)
        if colour:
            tag = "c_%s" % colour.replace("#","")
            self.text.tag_configure(tag, foreground=colour)
            self.text.insert(tk.END, line, tag)
        else:
            self.text.insert(tk.END, line)
        self.text.configure(state=tk.DISABLED)
        self.text.see(tk.END)


class LiveFeedSubscriber(object):
    """Receives JPEG preview frames published by azure_body_tracker."""
    def __init__(self, host="127.0.0.1", port=1236):
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.setsockopt(zmq.SUBSCRIBE, b"")
        self.sock.connect("tcp://%s:%d" % (host, port))

    def get_latest_jpeg(self):
        latest = None
        while True:
            try:
                latest = self.sock.recv(zmq.NOBLOCK)
            except zmq.Again:
                break
        return latest

    def close(self):
        self.sock.close()
        self.ctx.term()


# 1x1 grey JPEG placeholder when no frame is available yet
_TINY_JPEG_PLACEHOLDER = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e="
    b"C  2F-\xfc\x00\x01\x01\x01H\x00H\x00\x00\xff\xc0\x00\x0b\x08\x00"
    b"\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01"
    b"\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03"
    b"\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03"
    b"\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04"
    b"\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1"
    b"\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHI"
    b"JKLMNOPQRSTUVWXYZ\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd4P\x00"
    b"\x00\x00\x1f\xff\xd9"
)


class VRDriveThread(threading.Thread):
    """
    Applies VR locomotion commands (received via /vr_move HTTP POST) to ALMotion.
    Runs a tight loop reading the latest command from a shared dict and calling
    moveToward at ~12 Hz.  If no command arrives for > safety_timeout_s the robot
    stops automatically.
    """
    def __init__(self, session, q_feedback, safety_timeout_s=0.6, lock_head=True):
        threading.Thread.__init__(self)
        self.daemon = True
        self.session = session
        self.q_feedback = q_feedback
        self.running = True
        self._lock = threading.Lock()
        self._cmd = {"x": 0.0, "y": 0.0, "theta": 0.0,
                     "head_yaw": 0.0, "head_pitch": 0.0}
        self._last_update = 0.0
        self._safety_timeout = safety_timeout_s
        self._lock_head = bool(lock_head)

    def push_command(self, x, y, theta, head_yaw=0.0, head_pitch=0.0):
        with self._lock:
            self._cmd = {"x": float(x), "y": float(y), "theta": float(theta),
                         "head_yaw": float(head_yaw), "head_pitch": float(head_pitch)}
            self._last_update = time.time()

    def stop(self):
        self.running = False

    def run(self):
        import time as _time
        frames = 0
        try:
            motion = self.session.service("ALMotion")
            motion.wakeUp()
            if self._lock_head:
                try:
                    life = self.session.service("ALAutonomousLife")
                    life.setAutonomousAbilityEnabled("BasicAwareness", False)
                except Exception:
                    pass
                try:
                    motion.setStiffnesses(["HeadYaw", "HeadPitch"], 1.0)
                except Exception:
                    pass
            while self.running:
                with self._lock:
                    cmd = dict(self._cmd)
                    age = _time.time() - self._last_update
                if self._last_update == 0.0 or age > self._safety_timeout:
                    motion.moveToward(0.0, 0.0, 0.0)
                    if self._lock_head:
                        try:
                            motion.setAngles(["HeadYaw", "HeadPitch"], [0.0, -0.1], 0.15)
                        except Exception:
                            pass
                    _time.sleep(0.08)
                    continue
                x = max(-1.0, min(1.0, cmd["x"]))
                y = max(-1.0, min(1.0, cmd["y"]))
                th = max(-1.0, min(1.0, cmd["theta"]))
                motion.moveToward(x, y, th)
                if self._lock_head:
                    try:
                        hy = max(-2.0, min(2.0, cmd.get("head_yaw", 0.0)))
                        hp = max(-0.7, min(0.5, cmd.get("head_pitch", -0.1)))
                        motion.setAngles(["HeadYaw", "HeadPitch"], [hy, hp], 0.12)
                    except Exception:
                        pass
                frames += 1
                if frames % 24 == 0:
                    try:
                        self.q_feedback.put_nowait(
                            "VR-DRIVE x=%.2f y=%.2f th=%.2f hYaw=%.0f"
                            % (x, y, th, cmd["head_yaw"]))
                    except Exception:
                        pass
                _time.sleep(0.08)
        except Exception as e:
            print("[VRDrive] Fatal: %s" % e)
        finally:
            try:
                motion = self.session.service("ALMotion")
                motion.moveToward(0.0, 0.0, 0.0)
            except Exception:
                pass
            print("[VRDrive] Thread stopped (frames=%d)." % frames)


class MjpegServer(threading.Thread):
    """
    HTTP server serving live JPEG frames for tablet + VR / Unity.

    Endpoints:
      /              - HTML page: operator (MediaPipe) feed for Pepper tablet
      /frame.jpg     - latest operator JPEG (Unity / polling)
      /pepper.html        - browser preview: top camera
      /pepper.jpg         - top (forehead) camera
      /pepper_bottom.jpg  - bottom (mouth) camera
      /pepper_depth.jpg   - depth sensor as grayscale (see docs)
      /vr_move            - POST JSON {x, y, theta, head_yaw, head_pitch}
      /stream             - classic MJPEG of operator feed (desktop browsers)

    Android WebView does NOT support MJPEG in <img> tags, so tablet uses JS polling.
    Unity should poll /pepper.jpg with cache-busting (same pattern as tablet).
    """

    # JS fetches /frame.jpg as a Blob via XHR, converts to an object URL and sets it on
    # the <img> directly.  This avoids the double-fetch that caused ~50% broken images:
    # the old approach did img.src = url which triggered a SECOND HTTP request for the
    # same (already replaced) frame.  createObjectURL hands the already-downloaded bytes
    # straight to the renderer - one request, one frame, no race.
    _HTML = (
        b"<html>"
        b"<head>"
        b"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        b"<style>"
        b"*{margin:0;padding:0;box-sizing:border-box}"
        b"body{background:#000;display:flex;align-items:center;justify-content:center;"
        b"width:100vw;height:100vh;overflow:hidden}"
        b"#f{max-width:100vw;max-height:100vh;object-fit:contain}"
        b"#lbl{position:fixed;bottom:6px;right:8px;color:#3fb950;"
        b"font:bold 11px monospace;background:rgba(0,0,0,.6);"
        b"padding:2px 6px;border-radius:4px}"
        b"</style></head>"
        b"<body>"
        b"<img id='f'>"
        b"<span id='lbl'>connecting...</span>"
        b"<script>"
        b"var img=document.getElementById('f'),"
        b"    lbl=document.getElementById('lbl'),"
        b"    fps=0,t0=Date.now(),frames=0,prevUrl=null;"
        b"function load(){"
        b"  var xhr=new XMLHttpRequest();"
        b"  xhr.open('GET','/frame.jpg?t='+Date.now(),true);"
        b"  xhr.responseType='blob';"
        b"  xhr.onload=function(){"
        b"    if(xhr.status===200){"
        b"      var url=URL.createObjectURL(xhr.response);"
        b"      img.src=url;"               # hand decoded bytes directly - no re-fetch
        b"      if(prevUrl)URL.revokeObjectURL(prevUrl);"   # free previous blob memory
        b"      prevUrl=url;"
        b"      frames++;"
        b"      var now=Date.now();"
        b"      if(now-t0>=1000){"
        b"        lbl.textContent=Math.round(frames*1000/(now-t0))+' fps';"
        b"        frames=0;t0=now;"
        b"      }"
        b"      setTimeout(load,100);"      # next frame after 100 ms
        b"    }else{setTimeout(load,400);}" # non-200: back off
        b"  };"
        b"  xhr.onerror=function(){setTimeout(load,500);};"  # network error: back off
        b"  xhr.send();"
        b"}"
        b"load();"
        b"</script>"
        b"</body></html>"
    )

    # Same polling pattern as operator feed, but /pepper.jpg (Pepper's camera for VR)
    _HTML_PEPPER = (
        b"<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
        b"<style>*{margin:0;padding:0}body{background:#000;display:flex;align-items:center;"
        b"justify-content:center;width:100vw;height:100vh}#f{max-width:100vw;max-height:100vh;"
        b"object-fit:contain}#lbl{position:fixed;bottom:6px;right:8px;color:#58a6ff;"
        b"font:bold 11px monospace;background:rgba(0,0,0,.6);padding:2px 6px;border-radius:4px}"
        b"</style></head><body><img id='f'><span id='lbl'>Pepper cam</span><script>"
        b"var img=document.getElementById('f'),lbl=document.getElementById('lbl'),"
        b"fps=0,t0=Date.now(),frames=0,prevUrl=null;"
        b"function load(){var xhr=new XMLHttpRequest();xhr.open('GET','/pepper.jpg?t='+Date.now(),true);"
        b"xhr.responseType='blob';xhr.onload=function(){if(xhr.status===200){"
        b"var url=URL.createObjectURL(xhr.response);img.src=url;if(prevUrl)URL.revokeObjectURL(prevUrl);"
        b"prevUrl=url;frames++;var now=Date.now();if(now-t0>=1000){"
        b"lbl.textContent=Math.round(frames*1000/(now-t0))+' fps';frames=0;t0=now;}"
        b"setTimeout(load,100);}else{setTimeout(load,400);}};"
        b"xhr.onerror=function(){setTimeout(load,500);};xhr.send();}load();</script>"
        b"</body></html>"
    )

    def __init__(self, port=8080):
        threading.Thread.__init__(self)
        self.daemon = True
        self._port = port
        self._frame = b""                 # operator / MediaPipe JPEG
        self._frame_pepper = b""          # Pepper top (forehead) - /pepper.jpg
        self._frame_pepper_bottom = b""   # mouth camera - /pepper_bottom.jpg
        self._frame_pepper_depth = b""    # depth sensor (grayscale) - /pepper_depth.jpg
        self._lock = threading.Lock()
        self.vr_drive = None              # set externally to a VRDriveThread instance
        self.gui = None                   # set by PepperGui for remote control callbacks

    def push(self, jpeg_bytes):
        """Update the latest operator (MediaPipe) frame."""
        with self._lock:
            self._frame = jpeg_bytes

    def push_pepper(self, jpeg_bytes):
        """Pepper top camera (forehead) - /pepper.jpg"""
        with self._lock:
            self._frame_pepper = jpeg_bytes

    def push_pepper_bottom(self, jpeg_bytes):
        with self._lock:
            self._frame_pepper_bottom = jpeg_bytes

    def push_pepper_depth(self, jpeg_bytes):
        with self._lock:
            self._frame_pepper_depth = jpeg_bytes

    def clear_pepper(self):
        with self._lock:
            self._frame_pepper = b""
            self._frame_pepper_bottom = b""
            self._frame_pepper_depth = b""

    def get_local_ip(self):
        import socket as _s
        try:
            sock = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def run(self):
        import socket as _s
        srv = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        srv.setsockopt(_s.SOL_SOCKET, _s.SO_REUSEADDR, 1)
        try:
            srv.bind(("", self._port))
        except Exception as e:
            print("[MjpegServer] bind failed: %s" % e)
            return
        srv.listen(10)
        srv.settimeout(1.0)
        print("[MjpegServer] Listening on port %d" % self._port)
        while True:
            try:
                conn, _ = srv.accept()
                t = threading.Thread(target=self._handle, args=(conn,))
                t.daemon = True
                t.start()
            except Exception:
                continue

    def _send_jpeg_response(self, conn, frame):
        """Send one JPEG response; use tiny placeholder if frame is empty."""
        if not frame:
            frame = _TINY_JPEG_PLACEHOLDER
        resp = (b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-store, no-cache\r\n"
                b"Connection: close\r\n"
                b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                + frame)
        conn.sendall(resp)

    def _handle(self, conn):
        import time as _t
        try:
            import urlparse
            _urlparse = urlparse
        except Exception:
            from urllib import parse as _urlparse
        try:
            req = conn.recv(4096).decode("utf-8", errors="replace")
            request_line = req.split("\r\n", 1)[0]
            parts = request_line.split(" ")
            target = parts[1] if len(parts) >= 2 else "/"
            parsed = _urlparse.urlparse(target)
            path = parsed.path if parsed.path else "/"
            q = _urlparse.parse_qs(parsed.query)

            if path == "/frame.jpg":
                with self._lock:
                    frame = self._frame
                self._send_jpeg_response(conn, frame)

            elif path == "/pepper.jpg":
                with self._lock:
                    frame = self._frame_pepper
                self._send_jpeg_response(conn, frame)

            elif path == "/pepper_bottom.jpg":
                with self._lock:
                    frame = self._frame_pepper_bottom
                self._send_jpeg_response(conn, frame)

            elif path == "/pepper_depth.jpg":
                with self._lock:
                    frame = self._frame_pepper_depth
                self._send_jpeg_response(conn, frame)

            elif path == "/vr_status":
                vr = self.vr_drive
                active = vr is not None and getattr(vr, "is_alive", lambda: False)()
                status = '{"vr_drive_active":%s}' % ("true" if active else "false")
                resp_body = status.encode()
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Access-Control-Allow-Origin: *\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: " + str(len(resp_body)).encode() + b"\r\n\r\n"
                    + resp_body)

            elif path == "/status":
                gui = self.gui
                if gui is not None and hasattr(gui, "get_remote_status"):
                    try:
                        status_obj = gui.get_remote_status()
                    except Exception as _e:
                        status_obj = {"ok": False, "err": str(_e)}
                else:
                    vr = self.vr_drive
                    active = vr is not None and getattr(vr, "is_alive", lambda: False)()
                    status_obj = {"ok": True, "vr_drive": bool(active)}
                resp_body = json.dumps(status_obj).encode()
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Access-Control-Allow-Origin: *\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: " + str(len(resp_body)).encode() + b"\r\n\r\n"
                    + resp_body)

            elif path == "/control":
                action = (q.get("action", [""])[0] or "").strip().lower()
                gui = self.gui
                ok = False
                err = ""
                if not action:
                    err = "missing action"
                elif gui is None or not hasattr(gui, "request_remote_action"):
                    err = "gui not attached"
                else:
                    try:
                        ok = bool(gui.request_remote_action(action))
                        if not ok:
                            err = "unknown or rejected action"
                    except Exception as _e:
                        err = str(_e)
                resp_body = json.dumps({"ok": bool(ok), "action": action, "err": err}).encode()
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Access-Control-Allow-Origin: *\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: " + str(len(resp_body)).encode() + b"\r\n\r\n"
                    + resp_body)

            elif path == "/vr_move":
                vr = self.vr_drive
                if vr is not None:
                    try:
                        d = {}
                        if q:
                            d["x"] = float(q.get("x", [0])[0])
                            d["y"] = float(q.get("y", [0])[0])
                            d["theta"] = float(q.get("theta", [0])[0])
                            d["head_yaw"] = float(q.get("head_yaw", [0])[0])
                            d["head_pitch"] = float(q.get("head_pitch", [0])[0])
                        else:
                            content_length = 0
                            for line in req.split("\r\n"):
                                if line.lower().startswith("content-length:"):
                                    try:
                                        content_length = int(line.split(":", 1)[1].strip())
                                    except Exception:
                                        pass
                            body_start = req.find("\r\n\r\n")
                            body = ""
                            if body_start >= 0:
                                body = req[body_start + 4:]
                            while len(body) < content_length:
                                extra = conn.recv(4096).decode("utf-8", errors="replace")
                                if not extra:
                                    break
                                body += extra
                            d = json.loads(body) if body else {}
                        vr.push_command(
                            d.get("x", 0), d.get("y", 0), d.get("theta", 0),
                            d.get("head_yaw", 0), d.get("head_pitch", 0))
                        n = getattr(self, "_vr_recv_count", 0) + 1
                        self._vr_recv_count = n
                        if n == 1 or n % 50 == 0:
                            print("[MjpegServer] /vr_move #%d x=%.2f y=%.2f th=%.2f"
                                  % (n, d.get("x", 0), d.get("y", 0), d.get("theta", 0)))
                        resp_body = b'{"ok":true}'
                    except Exception as _e:
                        print("[MjpegServer] /vr_move error: %s" % _e)
                        resp_body = ('{"ok":false,"err":"%s"}' % str(_e)).encode()
                else:
                    resp_body = b'{"ok":false,"err":"vr_drive not active"}'
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Access-Control-Allow-Origin: *\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: " + str(len(resp_body)).encode() + b"\r\n\r\n"
                    + resp_body)

            elif path == "/stream":
                # Classic MJPEG - works in desktop Chrome/Firefox but not Android WebView
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: multipart/x-mixed-replace;boundary=mjpeg\r\n"
                    b"Cache-Control: no-cache\r\n\r\n"
                )
                while True:
                    with self._lock:
                        frame = self._frame
                    if frame:
                        hdr = (b"--mjpeg\r\nContent-Type: image/jpeg\r\n"
                               b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n")
                        conn.sendall(hdr + frame + b"\r\n")
                    _t.sleep(0.08)

            elif path == "/pepper.html":
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: " + str(len(self._HTML_PEPPER)).encode() + b"\r\n\r\n"
                    + self._HTML_PEPPER
                )

            else:
                # HTML page - operator (MediaPipe) feed for Pepper tablet
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: " + str(len(self._HTML)).encode() + b"\r\n\r\n"
                    + self._HTML
                )
        except Exception as e:
            print("[MjpegServer] request handling error: %s" % e)
        finally:
            try:
                conn.close()
            except Exception:
                pass


class BodyDriveThread(threading.Thread):
    """Gesture-to-locomotion control from BODY_25 keypoints on tcp://127.0.0.1:1234."""
    def __init__(self, session, q_feedback, q_gesture=None):
        threading.Thread.__init__(self)
        self.daemon = True
        self.session = session
        self.q_feedback = q_feedback
        self.q_gesture = q_gesture
        self.running = True

        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.connect("tcp://127.0.0.1:1234")
        self.sock.setsockopt(zmq.SUBSCRIBE, b"")
        self.sock.setsockopt(zmq.RCVTIMEO, 100)

        self.x_cmd = 0.0
        self.y_cmd = 0.0
        self.t_cmd = 0.0
        self.base_dz = None

    def stop(self):
        self.running = False

    def _decode(self, msg):
        try:
            data = json.loads(msg)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
        return {}

    def _getp(self, d, k):
        v = d.get(k)
        if isinstance(v, list) and len(v) >= 3:
            return v
        return None

    def run(self):
        import time as _time
        _GEST_HOLD     = 2.5    # seconds to hold T-pose before switching
        _gest_t0       = None
        _gest_cooldown = 0.0
        _gest_last_msg = 0.0
        try:
            motion = self.session.service("ALMotion")
            while self.running:
                wp = {}
                try:
                    raw = self.sock.recv()
                    wp = self._decode(raw)
                except Exception:
                    wp = {}

                # fail-safe on missing keypoints
                if not wp:
                    self.x_cmd *= 0.7
                    self.y_cmd *= 0.7
                    self.t_cmd *= 0.7
                    motion.moveToward(0.0, 0.0, 0.0)
                    continue

                neck = self._getp(wp, '1')
                hip = self._getp(wp, '8')
                ls = self._getp(wp, '5')
                rs = self._getp(wp, '2')
                lw = self._getp(wp, '7')
                rw = self._getp(wp, '4')
                if neck is None or hip is None:
                    motion.moveToward(0.0, 0.0, 0.0)
                    continue

                # -- Mode-switch gesture: T-pose (arms spread wide at shoulder height) --
                # Distinct from the "hands-up emergency stop" used by Body Drive.
                # Both wrists far out to the sides AND roughly level with the shoulders.
                now = _time.time()
                _t_pose = (float(lw[0] - ls[0]) >  0.30 and   # left wrist out to the left
                           float(rw[0] - rs[0]) < -0.30 and   # right wrist out to the right
                           abs(float(lw[1] - ls[1])) < 0.18 and  # left wrist at shoulder height
                           abs(float(rw[1] - rs[1])) < 0.18)     # right wrist at shoulder height
                if _t_pose and now > _gest_cooldown and self.q_gesture is not None:
                    if _gest_t0 is None:
                        _gest_t0 = now
                    held = now - _gest_t0
                    if held >= _GEST_HOLD:
                        try:
                            self.q_gesture.put_nowait("switch_mode")
                        except Exception:
                            pass
                        _gest_t0 = None
                        _gest_cooldown = now + 6.0
                    elif now - _gest_last_msg > 0.6:
                        secs_left = max(1, int(_GEST_HOLD - held) + 1)
                        try:
                            self.q_feedback.put_nowait(
                                "SWITCH GESTURE: keep hands up - %ds..." % secs_left)
                        except Exception:
                            pass
                        _gest_last_msg = now
                else:
                    _gest_t0 = None

                # torso lean controls
                dx = float(neck[0] - hip[0])  # left/right lean
                dz = float(neck[2] - hip[2])  # forward/back lean
                if self.base_dz is None:
                    self.base_dz = dz
                # Slowly adapt neutral depth when mostly stationary.
                self.base_dz = 0.98 * self.base_dz + 0.02 * dz
                dz_delta = dz - self.base_dz

                x = 0.0
                y = 0.0
                theta = 0.0

                # Deadzones + scaling
                if dz_delta < -0.020:
                    x = min(0.60, (-dz_delta - 0.020) * 3.0)
                elif dz_delta > 0.020:
                    x = -min(0.45, (dz_delta - 0.020) * 2.5)

                if dx > 0.03:
                    y = min(0.45, (dx - 0.03) * 2.2)
                elif dx < -0.03:
                    y = -min(0.45, (-dx - 0.03) * 2.2)

                # Shoulder depth asymmetry as turn cue
                if ls is not None and rs is not None:
                    dsz = float(rs[2] - ls[2])
                    if abs(dsz) > 0.07:
                        theta = max(-0.45, min(0.45, dsz * 1.6))

                # Safety gesture: both hands above shoulders => hard stop
                if (lw is not None and rw is not None and ls is not None and rs is not None and
                        lw[1] > ls[1] + 0.04 and rw[1] > rs[1] + 0.04):
                    x = y = theta = 0.0
                # Gesture overrides for forward/backward:
                # right hand up => forward, left hand up => backward
                elif lw is not None and rw is not None and ls is not None and rs is not None:
                    right_up = rw[1] > rs[1] + 0.06
                    left_up = lw[1] > ls[1] + 0.06
                    if right_up and not left_up:
                        x = 0.55
                        y = 0.0
                        theta = 0.0
                    elif left_up and not right_up:
                        x = -0.40
                        y = 0.0
                        theta = 0.0

                # Smooth commands to reduce jitter
                a = 0.6
                self.x_cmd = a * x + (1.0 - a) * self.x_cmd
                self.y_cmd = a * y + (1.0 - a) * self.y_cmd
                self.t_cmd = a * theta + (1.0 - a) * self.t_cmd

                motion.moveToward(float(self.x_cmd), float(self.y_cmd), float(self.t_cmd))
                self.q_feedback.put(
                    "BODY-DRIVE x=%.2f y=%.2f th=%.2f"
                    % (self.x_cmd, self.y_cmd, self.t_cmd)
                )
        finally:
            try:
                motion = self.session.service("ALMotion")
                motion.moveToward(0.0, 0.0, 0.0)
            except Exception:
                pass
            self.sock.close()
            self.ctx.term()


class ArmMirrorThread(threading.Thread):
    """
    Direct arm mirroring from BODY_25 keypoints.
    Calls ALMotion.setAngles() directly from the thread - same pattern as
    BodyDriveThread (moveToward), which is confirmed to work.
    """
    def __init__(self, session, q_feedback, q_gesture=None, one_to_one=True):
        threading.Thread.__init__(self)
        self.daemon = True
        self.session = session
        self.q_feedback = q_feedback
        self.q_gesture = q_gesture
        self.one_to_one = bool(one_to_one)
        self.running = True
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.connect("tcp://127.0.0.1:1234")
        self.sock.setsockopt(zmq.SUBSCRIBE, b"")
        self.sock.setsockopt(zmq.RCVTIMEO, 150)

    def stop(self):
        self.running = False

    def _decode(self, msg):
        try:
            d = json.loads(msg)
            if isinstance(d, dict):
                return d
        except Exception:
            return {}
        return {}

    def _p(self, d, key):
        v = d.get(key)
        if isinstance(v, list) and len(v) >= 3:
            return np.array([float(v[0]), float(v[1]), float(v[2])], dtype=np.float32)
        return None

    def _clip(self, x, lo, hi):
        return max(lo, min(hi, x))

    def _elbow_roll(self, s, e, w, left=True):
        v1 = s - e
        v2 = w - e
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 < 1e-5 or n2 < 1e-5:
            return -0.35 if left else 0.35
        c = float(np.dot(v1, v2) / (n1 * n2))
        c = max(-1.0, min(1.0, c))
        ang = np.arccos(c)
        if left:
            return self._clip(-(np.pi - ang), -1.50, -0.05)
        return self._clip((np.pi - ang), 0.05, 1.50)

    def _shoulder_angles(self, s, w, left, x_sign, y_up_sign):
        """
        Compute Pepper (ShoulderPitch, ShoulderRoll) from a shoulder point `s`
        and a wrist point `w`, normalised into a canonical body frame where
          +X = user-LEFT, +Y = UP, +Z = user-FORWARD (away from user's back).

        `x_sign`    = +1 if source frame has user-LEFT at +X (Azure Kinect),
                      -1 if source frame has user-LEFT at -X (MediaPipe with
                      cv2.flip selfie view).
        `y_up_sign` = +1 if source frame has UP at +Y (MediaPipe after -wm.y),
                      -1 if source frame has UP at -Y, i.e. Y-DOWN (Azure).
        Both trackers use +Z = away from camera; the user faces the camera, so
        user-FORWARD is always -Z_source, independent of tracker.

        Pepper joint conventions (Aldebaran):
          LShoulderPitch: 0 = arm forward, -pi/2 = arm UP, +pi/2 = arm DOWN.
          LShoulderRoll : 0 = sagittal, + = abducted to user's LEFT.
          RShoulderRoll : 0 = sagittal, - = abducted to user's RIGHT.
        """
        ax = float(w[0] - s[0]) * float(x_sign)       # + = arm toward user-left
        ay = float(w[1] - s[1]) * float(y_up_sign)    # + = arm up
        az = -float(w[2] - s[2])                      # + = arm toward user-forward
        arm_len = float(np.sqrt(ax * ax + ay * ay + az * az))
        if arm_len < 1e-4:
            return (0.0, 0.05 if left else -0.05)

        # Roll: abduction angle in the frontal plane (sideways spread).
        # asin of normalised lateral component gives angle in [-pi/2, +pi/2].
        # For left arm, abduction TO user's left -> ax > 0 -> roll > 0.
        # For right arm, abduction TO user's right -> ax < 0 -> roll < 0.
        lat_norm = max(-1.0, min(1.0, ax / arm_len))
        if left:
            roll = self._clip(float(np.arcsin(lat_norm)), 0.05, 1.50)
        else:
            roll = self._clip(float(np.arcsin(lat_norm)), -1.50, -0.05)

        # Pitch in the sagittal plane:
        #   arm forward (ay=0, az>0) -> atan2(0, +)    = 0     -> Pepper pitch = 0
        #   arm up      (ay>0, az=0) -> atan2(+, 0)    = +pi/2 -> Pepper pitch = -pi/2
        #   arm down    (ay<0, az=0) -> atan2(-, 0)    = -pi/2 -> Pepper pitch = +pi/2
        # So pitch = -atan2(ay, az).
        sag = float(np.sqrt(ay * ay + az * az))
        pitch = -float(np.arctan2(ay, az)) if sag > 1e-4 else 0.0
        pitch = self._clip(pitch, -2.0, 1.6)
        return (pitch, roll)

    def _detect_frame_signs(self, wp):
        """
        Auto-detect the source frame's sign conventions from the keypoints:
          x_sign    = sign(LShoulder.x - RShoulder.x)
                      (+1 if user-LEFT is at +X in source; -1 otherwise).
          y_up_sign = sign(Shoulder.y - MidHip.y)
                      (+1 if UP is +Y; -1 if Y-down, i.e. Azure).
        Returns (x_sign, y_up_sign) each in {+1, -1}, with safe defaults.
        """
        x_sign = 1.0
        y_up_sign = 1.0
        ls = self._p(wp, "5")  # user's anatomical LEFT shoulder
        rs = self._p(wp, "2")  # user's anatomical RIGHT shoulder
        if ls is not None and rs is not None:
            dx = float(ls[0] - rs[0])
            if abs(dx) > 1e-4:
                x_sign = 1.0 if dx > 0 else -1.0
        hip = self._p(wp, "8")  # MidHip
        shoulder = ls if ls is not None else rs
        if shoulder is not None and hip is not None:
            dy = float(shoulder[1] - hip[1])
            if abs(dy) > 1e-4:
                y_up_sign = 1.0 if dy > 0 else -1.0
        return (x_sign, y_up_sign)

    def run(self):
        names = ["LShoulderPitch", "LShoulderRoll", "LElbowRoll",
                 "RShoulderPitch", "RShoulderRoll", "RElbowRoll"]
        motion = None
        frames = 0
        empty = 0
        try:
            # Kill Autonomous Life so it stops fighting setAngles.
            try:
                life = self.session.service("ALAutonomousLife")
                current_state = life.getState()
                if current_state != "solitary":
                    life.setState("solitary")
                print("[ArmMirror] AutonomousLife -> solitary (was: %s)." % current_state)
            except Exception as _e:
                print("[ArmMirror] AutonomousLife setState warning: %s" % _e)

            motion = self.session.service("ALMotion")
            motion.wakeUp()
            motion.setStiffnesses(
                ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll",
                 "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll"], 1.0)
            motion.setExternalCollisionProtectionEnabled("Arms", False)
            print("[ArmMirror] Motors primed, stiffness=1, collision protection off.")

            import time as _time
            # EMA smoothing on joint angles - filters out MediaPipe frame-to-frame jitter
            # without adding the lag that a higher setAngles fraction would cause.
            _ANG_ALPHA  = 0.45   # 0=frozen, 1=no smoothing; 0.45 is a good balance
            _prev_angles = None  # initialised on first frame

            _GEST_HOLD     = 2.5    # seconds to hold before switching mode
            _gest_t0       = None
            _gest_cooldown = 0.0
            _gest_last_msg = 0.0

            while self.running:
                wp = {}
                try:
                    raw = self.sock.recv()
                    wp = self._decode(raw)
                except Exception:
                    empty += 1
                    if empty % 30 == 1:
                        print("[ArmMirror] No keypoints (empty=%d). Is MediaPipe running?" % empty)
                    continue

                # BODY_25 keys: 2/3/4 = user's anatomical RIGHT shoulder/elbow/wrist,
                #               5/6/7 = user's anatomical LEFT.
                # one_to_one = True  -> anatomical same-side (user L -> Pepper L).
                # one_to_one = False -> mirror mode         (user R -> Pepper L).
                if self.one_to_one:
                    ls = self._p(wp, "5"); le = self._p(wp, "6"); lw = self._p(wp, "7")
                    rs = self._p(wp, "2"); re = self._p(wp, "3"); rw = self._p(wp, "4")
                else:
                    ls = self._p(wp, "2"); le = self._p(wp, "3"); lw = self._p(wp, "4")
                    rs = self._p(wp, "5"); re = self._p(wp, "6"); rw = self._p(wp, "7")
                if any(v is None for v in (ls, le, lw, rs, re, rw)):
                    empty += 1
                    if empty % 30 == 1:
                        present = [k for k in ("2","3","4","5","6","7") if self._p(wp, k) is not None]
                        print("[ArmMirror] Missing arm keypoints. Present keys: %s" % present)
                    continue

                empty = 0
                # Auto-detect source frame conventions (Azure Kinect vs MediaPipe
                # webcam both publish to port 1234 with different X/Y sign meanings).
                x_sign, y_up_sign = self._detect_frame_signs(wp)
                if frames < 1:
                    print("[ArmMirror] Detected frame signs: x_sign=%+d y_up_sign=%+d"
                          % (int(x_sign), int(y_up_sign)))

                # Full-3D shoulder angles (supports forward, up AND lateral stretch).
                l_pitch, l_roll = self._shoulder_angles(ls, lw, left=True,
                                                        x_sign=x_sign, y_up_sign=y_up_sign)
                r_pitch, r_roll = self._shoulder_angles(rs, rw, left=False,
                                                        x_sign=x_sign, y_up_sign=y_up_sign)
                l_eroll = self._elbow_roll(ls, le, lw, left=True)
                r_eroll = self._elbow_roll(rs, re, rw, left=False)

                angles = [float(l_pitch), float(l_roll), float(l_eroll),
                          float(r_pitch), float(r_roll), float(r_eroll)]

                # EMA smoothing: blend toward new angles, don't jump instantly
                if _prev_angles is None:
                    _prev_angles = angles[:]
                angles = [_ANG_ALPHA * a + (1.0 - _ANG_ALPHA) * p
                          for a, p in zip(angles, _prev_angles)]
                _prev_angles = angles[:]

                try:
                    motion.setAngles(names, angles, 0.25)
                except Exception as e:
                    print("[ArmMirror] setAngles error: %s" % e)
                    try:
                        motion = self.session.service("ALMotion")
                    except Exception:
                        pass
                    continue

                frames += 1
                if frames == 1:
                    print("[ArmMirror] First setAngles sent: %s" % angles)
                elif frames % 100 == 0:
                    print("[ArmMirror] frames=%d L[p%.2f r%.2f e%.2f] R[p%.2f r%.2f e%.2f]"
                          % (frames, l_pitch, l_roll, l_eroll, r_pitch, r_roll, r_eroll))

                # -- Mode-switch gesture: T-pose --
                # Signed lateral spread in canonical frame: +x = toward user-left.
                now = _time.time()
                _dlx = float(lw[0] - ls[0]) * float(x_sign)
                _drx = float(rw[0] - rs[0]) * float(x_sign)
                _t_pose = (_dlx >  0.30 and
                           _drx < -0.30 and
                           abs(float(lw[1] - ls[1])) < 0.18 and
                           abs(float(rw[1] - rs[1])) < 0.18)
                if _t_pose and now > _gest_cooldown and self.q_gesture is not None:
                    if _gest_t0 is None:
                        _gest_t0 = now
                    held = now - _gest_t0
                    if held >= _GEST_HOLD:
                        try:
                            self.q_gesture.put_nowait("switch_mode")
                        except Exception:
                            pass
                        _gest_t0 = None
                        _gest_cooldown = now + 6.0
                    elif now - _gest_last_msg > 0.6:
                        secs_left = max(1, int(_GEST_HOLD - held) + 1)
                        try:
                            self.q_feedback.put_nowait(
                                "SWITCH GESTURE: keep hands up - %ds..." % secs_left)
                        except Exception:
                            pass
                        _gest_last_msg = now
                else:
                    _gest_t0 = None
                    try:
                        self.q_feedback.put_nowait(
                            "ARM-MIRROR L[p %.2f r %.2f e %.2f] R[p %.2f r %.2f e %.2f]" %
                            (l_pitch, l_roll, l_eroll, r_pitch, r_roll, r_eroll)
                        )
                    except Exception:
                        pass

        except Exception as e:
            print("[ArmMirror] Fatal error in run(): %s" % e)
        finally:
            print("[ArmMirror] Thread ending (frames=%d). Restoring defaults." % frames)
            try:
                if motion is not None:
                    motion.setAngles(
                        ["LShoulderRoll", "RShoulderRoll"], [0.2, -0.2], 0.1)
                    motion.setExternalCollisionProtectionEnabled("Arms", True)
            except Exception:
                pass
            self.sock.close()
            self.ctx.term()


# ---------------------------------------------------------------------------
# Main GUI class
# ---------------------------------------------------------------------------
class PepperGui:
    def __init__(self, master, session):
        self.master  = master
        self.session = session

        self.teleop   = tk.IntVar(value=1)
        self.approach = tk.IntVar(value=0)

        # Queues
        self.q_speech      = Queue()
        self.q_record      = Queue()
        self.q_button      = Queue()
        self.q_stop        = Queue()
        self.q_pepper      = Queue()
        self.q_appr_teleop = Queue()
        self.q_gesture     = Queue()  # gesture-based mode switching

        # MJPEG server - streams MediaPipe preview to Pepper's tablet
        self.mjpeg_server = MjpegServer(port=8080)
        self.mjpeg_server.gui = self
        self.mjpeg_server.start()
        self._mjpeg_ip = self.mjpeg_server.get_local_ip()
        self._tablet_feed_on = False
        print("[GUI] MJPEG server started at http://%s:8080/" % self._mjpeg_ip)
        # ALMotion.setAngles must run on the Tk main thread for reliable NAOqi behaviour.
        self.q_motion = Queue(maxsize=64)

        # Thread handles
        self.st  = None
        self.pac = None
        self.body_drive = None
        self.arm_mirror = None
        self.vr_drive = None
        self.user_tracking_on = False
        # Pepper camera: NAOqi must be used from the GUI thread only (worker thread crashes qi).
        self._pepper_video = None
        self._pepper_subscriptions = []  # list of dicts: link, key, mode, gui
        self._pepper_cam_enabled = False
        self._pepper_cam_bgr = False
        self._pepper_tick_id = None
        self._pepper_photo = None
        self._pepper_view_var = tk.StringVar(value="main")
        self._live_feed_tick_id = None
        self._live_video_item = None
        self._live_feed_queue = Queue(maxsize=2)
        self._live_feed_worker_run = False
        self._live_feed_thread = None
        self._live_dim_lock = threading.Lock()
        self._live_dw, self._live_dh = 480, 270
        self._pepper_video_item = None
        self._tracker_proc = None
        self._tracker_autostart_attempted = False
        self._tracker_last_exit = None

        # Init voice recognition for button pressing
        self.ok_pepper = OkPepperThread(self.q_button, self.q_stop)
        self.ok_pepper.start()
        self.q_stop.put("Rec")

        self._build_ui()
        self._apply_style()

        self.feed_sub = LiveFeedSubscriber() if PIL_AVAILABLE else None
        self._live_photo = None
        self.keyboard_teleop_on = False
        self._teleop_pressed = set()

    def _tracker_script_path(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        return os.path.join(root, "openpose_wrap", "mediapipe_body_tracker.py")

    def _start_mediapipe_tracker(self):
        if self._tracker_proc is not None:
            if self._tracker_proc.poll() is None:
                return True
            self._tracker_proc = None

        script = self._tracker_script_path()
        if not os.path.exists(script):
            self.log.append("MediaPipe tracker script not found: %s" % script, DANGER)
            return False

        last_err = None
        for py_cmd in TRACKER_PY_CANDIDATES:
            cmd = list(py_cmd) + [script]
            try:
                proc = subprocess.Popen(cmd, cwd=os.path.dirname(script))
                self._tracker_proc = proc
                self.log.append(
                    "Started MediaPipe tracker: %s" % " ".join(cmd),
                    SUCCESS,
                )
                return True
            except Exception as e:
                last_err = e
                continue

        self.log.append(
            "Could not start MediaPipe tracker automatically (%s). "
            "Please run Start_Pepper_Azure.bat or install Python launcher 'py'."
            % (last_err,),
            DANGER,
        )
        return False

    def _tracker_ports_in_use(self):
        """
        True if another process already owns MediaPipe PUB ports (1234/1236).
        Avoid launching a duplicate tracker instance.
        """
        ctx = None
        s1 = None
        s2 = None
        try:
            ctx = zmq.Context()
            s1 = ctx.socket(zmq.PUB)
            s2 = ctx.socket(zmq.PUB)
            s1.setsockopt(zmq.LINGER, 0)
            s2.setsockopt(zmq.LINGER, 0)
            s1.bind("tcp://*:1234")
            s2.bind("tcp://*:1236")
            return False
        except Exception:
            return True
        finally:
            try:
                if s1 is not None:
                    s1.close()
            except Exception:
                pass
            try:
                if s2 is not None:
                    s2.close()
            except Exception:
                pass
            try:
                if ctx is not None:
                    ctx.term()
            except Exception:
                pass

    def _maybe_autostart_tracker(self):
        if self._tracker_autostart_attempted:
            return
        self._tracker_autostart_attempted = True
        if not AUTO_START_MEDIAPIPE_TRACKER:
            return
        if self._tracker_ports_in_use():
            self.log.append(
                "MediaPipe tracker already running (ports 1234/1236 in use). Reusing existing tracker.",
                SUCCESS,
            )
            return
        # GUI subscribes to tcp://127.0.0.1:1234/1236 but does not launch trackers
        # by default; auto-start MediaPipe for webcam-only setups.
        self._start_mediapipe_tracker()

    def _stop_mediapipe_tracker(self):
        p = self._tracker_proc
        self._tracker_proc = None
        if p is None:
            return
        try:
            if p.poll() is None:
                p.terminate()
                for _ in range(20):
                    if p.poll() is not None:
                        break
                    time.sleep(0.05)
                if p.poll() is None:
                    p.kill()
        except Exception:
            pass

    def _poll_tracker_process(self):
        p = self._tracker_proc
        if p is None:
            return
        code = p.poll()
        if code is None:
            return
        self._tracker_proc = None
        if self._tracker_last_exit != code:
            self._tracker_last_exit = code
            self.log.append(
                "MediaPipe tracker exited (code %s). Webcam may be busy; close camera apps and restart tracker."
                % code,
                DANGER,
            )

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        m = self.master
        m.title("Pepper Control Panel")
        sw = max(m.winfo_screenwidth(), 800)
        sh = max(m.winfo_screenheight(), 600)
        win_w = min(1180, sw - 24)
        win_h = min(680, max(520, sh - 72))
        m.geometry("%dx%d" % (win_w, win_h))
        m.minsize(760, 420)
        m.configure(bg=BG)
        m.resizable(True, True)

        # -- Top header bar ---------------------------------------------
        header = tk.Frame(m, bg=SURFACE, height=52)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        tk.Label(header, text="Pepper Control Panel",
                 font=FONT_H1, bg=SURFACE, fg=TEXT_PRI).pack(side=tk.LEFT, padx=PAD*2, pady=PAD)

        self.badge_conn = StatusBadge(header)
        self.badge_conn.pack(side=tk.RIGHT, padx=PAD*2)

        self.badge_mode = StatusBadge(header)
        self.badge_mode.pack(side=tk.RIGHT, padx=4)

        sep = tk.Frame(m, bg=BORDER, height=1)
        sep.pack(fill=tk.X)

        # -- Scrollable main area (fits small laptop screens) ------------
        scroll_outer = tk.Frame(m, bg=BG)
        scroll_outer.pack(fill=tk.BOTH, expand=True)

        self._scroll_canvas = tk.Canvas(scroll_outer, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(scroll_outer, orient="vertical",
                            command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=vsb.set)

        self._scroll_inner = tk.Frame(self._scroll_canvas, bg=BG)
        self._scroll_canvas_window = self._scroll_canvas.create_window(
            (0, 0), window=self._scroll_inner, anchor="nw")

        self._scroll_inner.bind("<Configure>", self._on_scroll_inner_configure)
        self._scroll_canvas.bind("<Configure>", self._on_scroll_canvas_configure)

        self._scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # -- Main body: controls | feeds + log (inside scroll region) -----
        body = tk.Frame(self._scroll_inner, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=PAD, pady=PAD)
        body.columnconfigure(0, weight=0, minsize=220)
        body.columnconfigure(1, weight=1, minsize=420)
        body.rowconfigure(0, weight=1)

        # -- LEFT PANEL --------------------------------------------------
        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, PAD))
        self._build_left(left)

        # -- RIGHT: feeds OR debug panel, feedback bar, compact log --------
        main_col = tk.Frame(body, bg=BG)
        main_col.grid(row=0, column=1, sticky="nsew")
        main_col.rowconfigure(0, weight=1)
        main_col.rowconfigure(1, weight=0)
        main_col.rowconfigure(2, weight=0)
        main_col.columnconfigure(0, weight=1)

        if EMBED_PREVIEWS_IN_GUI:
            feeds_row = tk.Frame(main_col, bg=BG)
            feeds_row.grid(row=0, column=0, sticky="nsew")
            feeds_row.columnconfigure(0, weight=1)
            feeds_row.columnconfigure(1, weight=1)
            feeds_row.rowconfigure(0, weight=1)
            self._build_feed_panels(feeds_row)
        else:
            self._build_debug_panel(main_col)

        self.lbl_feedback = tk.Label(main_col,
                                     text="No feedback",
                                     font=FONT_LABEL, bg=SURFACE_2, fg=TEXT_SEC,
                                     anchor="w", padx=PAD, pady=4, relief=tk.FLAT)
        self.lbl_feedback.grid(row=1, column=0, sticky="ew", padx=1, pady=(PAD // 2, 0))

        self._build_log_panel(main_col)

        self._bind_scroll_mousewheel()

    def _on_scroll_inner_configure(self, event):
        self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

    def _on_scroll_canvas_configure(self, event):
        try:
            self._scroll_canvas.itemconfigure(self._scroll_canvas_window, width=event.width)
        except Exception:
            pass

    def _wheel_should_skip_outer(self, widget):
        w = widget
        while w is not None:
            if getattr(w, "_pepper_skip_outer_scroll", False):
                return True
            w = getattr(w, "master", None)
        return False

    def _bind_scroll_mousewheel(self):
        def on_wheel(event):
            if self._wheel_should_skip_outer(event.widget):
                return
            if getattr(event, "delta", 0):
                self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_wheel_linux_up(event):
            if self._wheel_should_skip_outer(event.widget):
                return
            self._scroll_canvas.yview_scroll(-1, "units")

        def on_wheel_linux_down(event):
            if self._wheel_should_skip_outer(event.widget):
                return
            self._scroll_canvas.yview_scroll(1, "units")

        self.master.bind_all("<MouseWheel>", on_wheel)
        self.master.bind_all("<Button-4>", on_wheel_linux_up)
        self.master.bind_all("<Button-5>", on_wheel_linux_down)

    def _build_left(self, parent):
        P = PAD        # 10
        S = PAD // 2   # 5  - tight spacing used throughout

        # -- Connection card --
        conn_card = Card(parent)
        conn_card.pack(fill=tk.X, pady=(0, S))

        tk.Label(conn_card, text="Connection", font=FONT_BOLD,
                 bg=SURFACE, fg=TEXT_PRI).pack(anchor="w", padx=P, pady=(S, 2))
        tk.Frame(conn_card, bg=BORDER, height=1).pack(fill=tk.X, padx=P)

        # IP + Port on the same row to save vertical space
        ip_row = tk.Frame(conn_card, bg=SURFACE)
        ip_row.pack(fill=tk.X, padx=P, pady=(S, 2))
        tk.Label(ip_row, text="IP", font=FONT_LABEL, bg=SURFACE, fg=TEXT_SEC,
                 width=4, anchor="w").pack(side=tk.LEFT)
        self.text_ip = tk.Entry(ip_row, bg=SURFACE_2, fg=TEXT_PRI,
                                insertbackground=TEXT_PRI, relief=tk.FLAT,
                                font=FONT_LABEL, width=14)
        self.text_ip.insert(tk.END, "192.168.1.61")
        self.text_ip.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(ip_row, text="  Port", font=FONT_LABEL, bg=SURFACE,
                 fg=TEXT_SEC).pack(side=tk.LEFT)
        self.text_port = tk.Entry(ip_row, bg=SURFACE_2, fg=TEXT_PRI,
                                  insertbackground=TEXT_PRI, relief=tk.FLAT,
                                  font=FONT_LABEL, width=5)
        self.text_port.insert(tk.END, "9559")
        self.text_port.pack(side=tk.LEFT, padx=(2, 0))

        self.btn_connect = ModernButton(conn_card, text="Connect",
                                        accent=True, command=self.connect_pepper)
        self.btn_connect.pack(fill=tk.X, padx=P, pady=S)

        self.lbl_conn = tk.Label(conn_card, text="",
                                 font=FONT_SMALL, bg=SURFACE, fg=TEXT_SEC,
                                 wraplength=210, justify=tk.LEFT)
        self.lbl_conn.pack(anchor="w", padx=P, pady=(0, S))

        # -- Quick Actions card - most-used buttons right at the top --
        qa_card = Card(parent)
        qa_card.pack(fill=tk.X, pady=(0, S))

        tk.Label(qa_card, text="Quick Actions", font=FONT_BOLD,
                 bg=SURFACE, fg=TEXT_PRI).pack(anchor="w", padx=P, pady=(S, 2))
        tk.Frame(qa_card, bg=BORDER, height=1).pack(fill=tk.X, padx=P)

        self.btn_arm_mirror = ModernButton(
            qa_card, text="Start Arm Mirror (MediaPipe)",
            accent=True, state=tk.DISABLED, command=self.toggle_arm_mirror
        )
        self.btn_arm_mirror.pack(fill=tk.X, padx=P, pady=(S, 2))

        # Body Drive + Keyboard Teleop side by side
        qa_row = tk.Frame(qa_card, bg=SURFACE)
        qa_row.pack(fill=tk.X, padx=P, pady=(0, 2))
        qa_row.columnconfigure(0, weight=1)
        qa_row.columnconfigure(1, weight=1)

        self.btn_body_drive = ModernButton(
            qa_row, text="Body Drive",
            state=tk.DISABLED, command=self.toggle_body_drive
        )
        self.btn_body_drive.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self.btn_keyboard_teleop = ModernButton(
            qa_row, text="Keyboard (WASD)",
            state=tk.DISABLED, command=self.toggle_keyboard_teleop
        )
        self.btn_keyboard_teleop.grid(row=0, column=1, sticky="ew", padx=(2, 0))

        self.btn_vr_drive = ModernButton(
            qa_card, text="VR Drive (Unity Headset)",
            state=tk.DISABLED, command=self.toggle_vr_drive
        )
        self.btn_vr_drive.pack(fill=tk.X, padx=P, pady=(0, 2))

        self.btn_track_user = ModernButton(
            qa_card, text="Track User (Pepper Camera)",
            state=tk.DISABLED, command=self.toggle_user_tracking
        )
        self.btn_track_user.pack(fill=tk.X, padx=P, pady=(0, 2))

        self.btn_tablet = ModernButton(
            qa_card, text="Show Operator on Pepper Tablet",
            state=tk.DISABLED, command=self.toggle_tablet_feed
        )
        self.btn_tablet.pack(fill=tk.X, padx=P, pady=(0, S))

        self.btn_pepper_preview = ModernButton(
            qa_card, text="Open Pepper Camera Preview",
            command=self.open_pepper_preview
        )
        self.btn_pepper_preview.pack(fill=tk.X, padx=P, pady=(0, S))
        if not ENABLE_PEPPER_CAMERA_IN_GUI:
            self.btn_pepper_preview.configure(state=tk.DISABLED)

        # -- Manual Locomotion card --
        move_card = Card(parent)
        move_card.pack(fill=tk.X, pady=(0, S))
        tk.Label(move_card, text="Manual Locomotion", font=FONT_BOLD,
                 bg=SURFACE, fg=TEXT_PRI).pack(anchor="w", padx=P, pady=(S, 2))
        tk.Frame(move_card, bg=BORDER, height=1).pack(fill=tk.X, padx=P)

        grid = tk.Frame(move_card, bg=SURFACE)
        grid.pack(fill=tk.X, padx=P, pady=S)
        grid.columnconfigure((0, 1, 2), weight=1)

        self.btn_fwd = ModernButton(grid, text="Fwd", state=tk.DISABLED,
                                    command=lambda: self._motion_nudge(0.25, 0.0, 0.0))
        self.btn_fwd.grid(row=0, column=1, padx=2, pady=2, sticky="ew")

        self.btn_left = ModernButton(grid, text="Left", state=tk.DISABLED,
                                     command=lambda: self._motion_nudge(0.0, 0.20, 0.0))
        self.btn_left.grid(row=1, column=0, padx=2, pady=2, sticky="ew")

        self.btn_stopmove = ModernButton(grid, text="Stop", danger=True, state=tk.DISABLED,
                                         command=lambda: self._motion_nudge(0.0, 0.0, 0.0))
        self.btn_stopmove.grid(row=1, column=1, padx=2, pady=2, sticky="ew")

        self.btn_right = ModernButton(grid, text="Right", state=tk.DISABLED,
                                      command=lambda: self._motion_nudge(0.0, -0.20, 0.0))
        self.btn_right.grid(row=1, column=2, padx=2, pady=2, sticky="ew")

        self.btn_back = ModernButton(grid, text="Back", state=tk.DISABLED,
                                     command=lambda: self._motion_nudge(-0.20, 0.0, 0.0))
        self.btn_back.grid(row=2, column=1, padx=2, pady=2, sticky="ew")

        self.btn_rotl = ModernButton(grid, text="Rot L", state=tk.DISABLED,
                                     command=lambda: self._motion_nudge(0.0, 0.0, 0.40))
        self.btn_rotl.grid(row=3, column=0, padx=2, pady=2, sticky="ew")

        self.btn_rotr = ModernButton(grid, text="Rot R", state=tk.DISABLED,
                                     command=lambda: self._motion_nudge(0.0, 0.0, -0.40))
        self.btn_rotr.grid(row=3, column=2, padx=2, pady=2, sticky="ew")

        # -- Advanced card (less-used) --
        adv_card = Card(parent)
        adv_card.pack(fill=tk.X, pady=(0, S))
        tk.Label(adv_card, text="Advanced", font=FONT_BOLD,
                 bg=SURFACE, fg=TEXT_PRI).pack(anchor="w", padx=P, pady=(S, 2))
        tk.Frame(adv_card, bg=BORDER, height=1).pack(fill=tk.X, padx=P)

        # Options checkboxes
        opt_frame = tk.Frame(adv_card, bg=SURFACE)
        opt_frame.pack(fill=tk.X, padx=P, pady=(S, 2))

        self.c_approach = tk.Checkbutton(opt_frame, text="Search User",
                                         variable=self.approach, onvalue=1, offvalue=0,
                                         font=FONT_LABEL, bg=SURFACE, fg=TEXT_PRI,
                                         activebackground=SURFACE, selectcolor=SURFACE_2,
                                         highlightthickness=0, relief=tk.FLAT,
                                         activeforeground=TEXT_PRI)
        self.c_approach.pack(side=tk.LEFT)

        self.c_teleop = tk.Checkbutton(opt_frame, text="Teleoperate",
                                       variable=self.teleop, onvalue=1, offvalue=0,
                                       font=FONT_LABEL, bg=SURFACE, fg=TEXT_PRI,
                                       activebackground=SURFACE, selectcolor=SURFACE_2,
                                       highlightthickness=0, relief=tk.FLAT,
                                       activeforeground=TEXT_PRI, state=tk.DISABLED)
        self.c_teleop.pack(side=tk.LEFT, padx=(P, 0))

        adv_row = tk.Frame(adv_card, bg=SURFACE)
        adv_row.pack(fill=tk.X, padx=P, pady=(0, 2))
        adv_row.columnconfigure(0, weight=1)
        adv_row.columnconfigure(1, weight=1)

        self.btn_locomotion = ModernButton(adv_row, text="Search+Approach",
                                           state=tk.DISABLED, command=self.start_locomotion)
        self.btn_locomotion.grid(row=0, column=0, sticky="ew", padx=(0, 2), pady=2)

        self.btn_test = ModernButton(adv_row, text="Test Move (Fwd)",
                                     state=tk.DISABLED, command=self.test_move)
        self.btn_test.grid(row=0, column=1, sticky="ew", padx=(2, 0), pady=2)

        self.btn_stop = ModernButton(adv_card, text="Stop",
                                     danger=True, state=tk.DISABLED,
                                     command=self.stop_pepper)
        self.btn_stop.pack(fill=tk.X, padx=P, pady=(0, S))

        # -- Voice card --
        voice_card = Card(parent)
        voice_card.pack(fill=tk.X, pady=(0, S))

        tk.Label(voice_card, text="Voice", font=FONT_BOLD,
                 bg=SURFACE, fg=TEXT_PRI).pack(anchor="w", padx=P, pady=(S, 2))
        tk.Frame(voice_card, bg=BORDER, height=1).pack(fill=tk.X, padx=P)

        self.lbl_speech_title = tk.Label(voice_card, text="Recognised text",
                                         font=FONT_SMALL, bg=SURFACE, fg=TEXT_SEC)
        self.lbl_speech_title.pack(anchor="w", padx=P, pady=(S, 2))

        self.lbl_speech = tk.Label(voice_card, text="-",
                                   font=FONT_LABEL, bg=SURFACE_2, fg=TEXT_PRI,
                                   wraplength=210, justify=tk.LEFT,
                                   anchor="w", relief=tk.FLAT, padx=6, pady=4)
        self.lbl_speech.pack(fill=tk.X, padx=P, pady=(0, S))

        self.btn_rec = ModernButton(voice_card, text="Start Talking",
                                    state=tk.DISABLED, command=self.start_talk)
        self.btn_rec.pack(fill=tk.X, padx=P, pady=(0, S))

    def _build_feed_panels(self, parent):
        """Body tracker (left) and Pepper camera (right), same row."""
        S = PAD // 2

        # -- Live feed canvas (body tracker) --
        feed_card = Card(parent)
        feed_card.grid(row=0, column=0, sticky="nsew", padx=(0, S))
        feed_card.rowconfigure(2, weight=1)
        feed_card.columnconfigure(0, weight=1)

        tk.Label(feed_card, text="Live Feed - Body Tracker",
                 font=FONT_BOLD, bg=SURFACE, fg=TEXT_PRI).grid(
                     row=0, column=0, sticky="w", padx=PAD, pady=(PAD, 4))
        tk.Frame(feed_card, bg=BORDER, height=1).grid(
            row=1, column=0, sticky="ew", padx=PAD, pady=(0, 4))

        self.canvas = tk.Canvas(feed_card,
                                bg="#0a0e14",
                                highlightthickness=0,
                                height=220)
        self.canvas.grid(row=2, column=0, sticky="nsew", padx=1, pady=1)

        self._canvas_placeholder()

        self.lbl_countdown = tk.Label(self.canvas,
                                      text="",
                                      font=("Segoe UI", 72, "bold"),
                                      bg="#0a0e14", fg=ACCENT)
        self._countdown_win = None
        if not EMBED_PREVIEWS_IN_GUI:
            self.canvas.create_text(
                8, 8, anchor="nw", fill=TEXT_SEC, font=FONT_SMALL,
                text="Preview disabled in GUI (performance mode).\nUse tracker/OpenCV window or http://%s:8080/"
                     % getattr(self, "_mjpeg_ip", "127.0.0.1"),
                tags="preview_disabled",
            )

        # -- Pepper onboard camera + view selector --
        pepper_card = Card(parent)
        pepper_card.grid(row=0, column=1, sticky="nsew", padx=(S, 0))
        pepper_card.rowconfigure(2, weight=1)
        pepper_card.columnconfigure(0, weight=1)

        hdr = tk.Frame(pepper_card, bg=SURFACE)
        hdr.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(PAD, 2))
        tk.Label(hdr, text="Pepper camera (connect to view)",
                 font=FONT_BOLD, bg=SURFACE, fg=TEXT_PRI).pack(anchor="w")
        rb_fr = tk.Frame(hdr, bg=SURFACE)
        rb_fr.pack(anchor="w", pady=(4, 0))
        rb_kw = dict(
            font=FONT_SMALL, bg=SURFACE, fg=TEXT_PRI,
            activebackground=SURFACE, activeforeground=TEXT_PRI,
            selectcolor=SURFACE_2, highlightthickness=0,
        )
        for val, lab in (("main", "Top"), ("bottom", "Mouth"), ("depth", "Depth")):
            tk.Radiobutton(
                rb_fr, text=lab, variable=self._pepper_view_var, value=val, **rb_kw
            ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Frame(pepper_card, bg=BORDER, height=1).grid(
            row=1, column=0, sticky="ew", padx=PAD, pady=(0, 4))

        self.canvas_pepper = tk.Canvas(pepper_card,
                                       bg="#0a0e14",
                                       highlightthickness=0,
                                       height=220)
        self.canvas_pepper.grid(row=2, column=0, sticky="nsew", padx=1, pady=1)
        self._pepper_canvas_placeholder()
        if not EMBED_PREVIEWS_IN_GUI:
            self.canvas_pepper.create_text(
                8, 8, anchor="nw", fill=TEXT_SEC, font=FONT_SMALL,
                text="Preview disabled in GUI (performance mode).\nUse Unity/browser: /pepper.html",
                tags="preview_disabled",
            )

    def _build_debug_panel(self, parent):
        """Compact runtime status panel when embedded previews are disabled."""
        dbg_card = Card(parent)
        dbg_card.grid(row=0, column=0, sticky="nsew")
        dbg_card.columnconfigure(0, weight=1)

        tk.Label(dbg_card, text="Runtime Debug",
                 font=FONT_BOLD, bg=SURFACE, fg=TEXT_PRI).grid(
                     row=0, column=0, sticky="w", padx=PAD, pady=(PAD, 4))
        tk.Frame(dbg_card, bg=BORDER, height=1).grid(
            row=1, column=0, sticky="ew", padx=PAD, pady=(0, 4))

        self.lbl_dbg_tracker = tk.Label(
            dbg_card, text="Tracker: unknown", font=FONT_LABEL,
            bg=SURFACE, fg=TEXT_SEC, anchor="w", justify=tk.LEFT, wraplength=700)
        self.lbl_dbg_tracker.grid(row=2, column=0, sticky="ew", padx=PAD, pady=(2, 2))

        self.lbl_dbg_streams = tk.Label(
            dbg_card, text="Streams: unknown", font=FONT_LABEL,
            bg=SURFACE, fg=TEXT_SEC, anchor="w", justify=tk.LEFT, wraplength=700)
        self.lbl_dbg_streams.grid(row=3, column=0, sticky="ew", padx=PAD, pady=(2, 2))

        self.lbl_dbg_modes = tk.Label(
            dbg_card, text="Modes: unknown", font=FONT_LABEL,
            bg=SURFACE, fg=TEXT_SEC, anchor="w", justify=tk.LEFT, wraplength=700)
        self.lbl_dbg_modes.grid(row=4, column=0, sticky="ew", padx=PAD, pady=(2, PAD))

    def _build_log_panel(self, parent):
        log_card = Card(parent)
        log_card.grid(row=2, column=0, sticky="ew", pady=(PAD // 2, 0))
        log_card.columnconfigure(0, weight=1)

        tk.Label(log_card, text="Session Log",
                 font=FONT_BOLD, bg=SURFACE, fg=TEXT_PRI).grid(
                     row=0, column=0, sticky="w", padx=PAD, pady=(PAD, 4))
        tk.Frame(log_card, bg=BORDER, height=1).grid(
            row=1, column=0, sticky="ew", padx=PAD, pady=(0, 4))

        self.log = LogText(log_card, height_lines=7)
        self.log.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 4))

    def _canvas_placeholder(self):
        self.canvas.update_idletasks()
        w = max(self.canvas.winfo_width(),  240)
        h = max(self.canvas.winfo_height(), 180)
        self.canvas.delete("video")
        self._live_video_item = None
        self.canvas.delete("placeholder")
        self.canvas.create_text(w//2, h//2,
                                text="No feed\nStart a body tracker (MediaPipe/Azure)",
                                fill=TEXT_SEC, font=FONT_BODY, justify="center",
                                tags="placeholder")

    def _pepper_canvas_placeholder(self, msg=None):
        self.canvas_pepper.update_idletasks()
        w = max(self.canvas_pepper.winfo_width(), 240)
        h = max(self.canvas_pepper.winfo_height(), 180)
        self.canvas_pepper.delete("placeholder")
        self.canvas_pepper.delete("pepper_video")
        self._pepper_video_item = None
        lines = "No Pepper feed\nConnect to the robot"
        if msg:
            lines = msg
        self.canvas_pepper.create_text(w//2, h//2,
                                       text=lines,
                                       fill=TEXT_SEC, font=FONT_BODY, justify="center",
                                       tags="placeholder")

    def _live_feed_worker_loop(self):
        """ZMQ + JPEG decode + resize off the Tk thread; main thread only assigns PhotoImage."""
        while self._live_feed_worker_run:
            sub = self.feed_sub
            if sub is None:
                time.sleep(0.05)
                continue
            jpg = sub.get_latest_jpeg()
            if not jpg:
                time.sleep(0.001)
                continue
            ms = getattr(self, "mjpeg_server", None)
            if ms is not None:
                try:
                    ms.push(jpg)
                except Exception:
                    pass
            if not EMBED_PREVIEWS_IN_GUI:
                continue
            if not PIL_AVAILABLE:
                continue
            try:
                with self._live_dim_lock:
                    tw, th = self._live_dw, self._live_dh
                tw = max(1, int(tw))
                th = max(1, int(th))
                im = Image.open(BytesIO(jpg))
                if im.mode != "RGB":
                    im = im.convert("RGB")
                mw, mh = im.size
                cap = max(tw, th, 420)
                if max(mw, mh) > cap:
                    r = cap / float(max(mw, mh))
                    im = im.resize(
                        (max(1, int(mw * r)), max(1, int(mh * r))),
                        _RESAMPLE_FAST,
                    )
                im = im.resize((tw, th), _RESAMPLE_PIXEL)
                try:
                    self._live_feed_queue.put_nowait(im)
                except Full:
                    try:
                        self._live_feed_queue.get_nowait()
                    except Empty:
                        pass
                    try:
                        self._live_feed_queue.put_nowait(im)
                    except Full:
                        pass
            except Exception:
                pass

    def _tick_live_feed(self):
        """Apply the latest decoded body-tracker frame (worker does ZMQ + PIL)."""
        self._live_feed_tick_id = None
        if not EMBED_PREVIEWS_IN_GUI:
            return
        if not PIL_AVAILABLE or self.feed_sub is None:
            self._live_feed_tick_id = self.master.after(200, self._tick_live_feed)
            return
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            self.canvas.update_idletasks()
        w = max(self.canvas.winfo_width(), 240)
        h = max(self.canvas.winfo_height(), 180)
        with self._live_dim_lock:
            self._live_dw, self._live_dh = w, h
        latest = None
        try:
            while True:
                latest = self._live_feed_queue.get_nowait()
        except Empty:
            pass
        if latest is not None:
            try:
                self._live_photo = ImageTk.PhotoImage(latest)
                vid = self._live_video_item
                if vid is None:
                    self._live_video_item = self.canvas.create_image(
                        0, 0, image=self._live_photo, anchor=tk.NW, tags="video")
                else:
                    self.canvas.itemconfig(vid, image=self._live_photo)
                self.canvas.delete("placeholder")
                if self._countdown_win:
                    self.canvas.tag_raise(self._countdown_win)
            except Exception:
                pass
        self._live_feed_tick_id = self.master.after(16, self._tick_live_feed)

    def _stop_pepper_camera(self):
        """Unsubscribe and cancel timer; safe to call multiple times."""
        self._pepper_cam_enabled = False
        tid = getattr(self, "_pepper_tick_id", None)
        self._pepper_tick_id = None
        if tid is not None:
            try:
                self.master.after_cancel(tid)
            except Exception:
                pass
        try:
            if self._pepper_video is not None:
                for sub in getattr(self, "_pepper_subscriptions", []):
                    try:
                        self._pepper_video.unsubscribe(sub["link"])
                    except Exception:
                        pass
        except Exception:
            pass
        self._pepper_video = None
        self._pepper_subscriptions = []
        self._pepper_placeholder_view = ""
        if getattr(self, "mjpeg_server", None) is not None:
            self.mjpeg_server.clear_pepper()

    def _start_pepper_camera(self):
        """Subscribe on the GUI thread; frames polled via _pepper_camera_tick."""
        self._stop_pepper_camera()
        if not PIL_AVAILABLE:
            self.log.append("Pepper camera skipped (Pillow not installed).", WARNING)
            return
        _K_QVGA = 1   # kQVGA = 320x240
        _K_RGB  = 11  # kRGBColorSpace
        import time as _time
        _ts = int(_time.time())
        try:
            v = self.session.service("ALVideoDevice")
            self._pepper_video = v
            self._pepper_subscriptions = []
            # Main stream (GUI + /pepper.jpg)
            _specs = [
                {"key": "main", "camera": PEPPER_CAMERA_INDEX, "mode": "rgb"},
            ]
            for _ex in PEPPER_VR_EXTRA_STREAMS:
                _specs.append({
                    "key": _ex["name"],
                    "camera": int(_ex["camera"]),
                    "mode": _ex["mode"],
                })
            for sp in _specs:
                _sub_name = "pepper_gui_%s_%d" % (sp["key"], _ts)
                try:
                    if hasattr(v, "subscribeCamera"):
                        link = v.subscribeCamera(
                            _sub_name, sp["camera"], _K_QVGA, _K_RGB, 10)
                    else:
                        if sp["key"] != "main":
                            continue
                        link = v.subscribe(_sub_name, _K_QVGA, _K_RGB, 10)
                    self._pepper_subscriptions.append(dict(sp, link=link))
                    self.log.append(
                        "Pepper cam %s subscribed (index %d, handle=%r)."
                        % (sp["key"], sp["camera"], link),
                        SUCCESS,
                    )
                except Exception as _e:
                    self.log.append(
                        "Pepper cam '%s' not available: %s" % (sp["key"], _e),
                        WARNING,
                    )
            if not self._pepper_subscriptions:
                raise RuntimeError("no camera subscriptions succeeded")
            self._pepper_cam_enabled = True
            self._pepper_cam_frame_err = 0
            self._pepper_sz_logged = 0
            self._pepper_tick_id = self.master.after(33, self._pepper_camera_tick)
        except Exception as e:
            self._pepper_canvas_placeholder("Pepper camera:\n%s" % e)
            self.log.append("Pepper camera subscribe failed: %s" % e, DANGER)

    def _pepper_camera_tick(self):
        """Poll getImageRemote on the GUI thread (required for stable qi/NAOqi)."""
        self._pepper_tick_id = None
        if not self._pepper_cam_enabled or self._pepper_video is None:
            return
        if not PIL_AVAILABLE:
            return
        want = self._pepper_view_var.get()
        sub_keys = {sp["key"] for sp in self._pepper_subscriptions}
        if want not in sub_keys:
            if getattr(self, "_pepper_placeholder_view", "") != want:
                self._pepper_canvas_placeholder("This view is not subscribed")
                self._pepper_placeholder_view = want
        else:
            self._pepper_placeholder_view = ""
        gui_image = None
        try:
            for sp in self._pepper_subscriptions:
                try:
                    img = self._pepper_video.getImageRemote(sp["link"])
                except Exception:
                    continue
                if not img or len(img) < 7:
                    continue
                w0, h0 = int(img[0]), int(img[1])
                raw = img[6]
                if w0 <= 0 or h0 <= 0 or raw is None:
                    continue
                image = _pepper_raw_to_pil(w0, h0, raw, sp["mode"])
                if image is None:
                    b = getattr(self, "_pepper_sz_logged", 0)
                    if b < 8:
                        self.log.append(
                            "Pepper cam '%s' decode failed (len=%s)."
                            % (sp["key"], len(raw) if hasattr(raw, "__len__") else "?"),
                            WARNING,
                        )
                        self._pepper_sz_logged = b + 1
                    continue
                try:
                    jbuf = BytesIO()
                    try:
                        image.save(jbuf, format="JPEG", quality=60, subsampling=2)
                    except TypeError:
                        image.save(jbuf, format="JPEG", quality=60)
                    jpg = jbuf.getvalue()
                    ms = getattr(self, "mjpeg_server", None)
                    if ms is not None:
                        if sp["key"] == "main":
                            ms.push_pepper(jpg)
                        elif sp["key"] == "bottom":
                            ms.push_pepper_bottom(jpg)
                        elif sp["key"] == "depth":
                            ms.push_pepper_depth(jpg)
                except Exception:
                    pass
                if sp["key"] == want:
                    gui_image = image
            if EMBED_PREVIEWS_IN_GUI and want in sub_keys and gui_image is not None:
                w = self.canvas_pepper.winfo_width()
                h = self.canvas_pepper.winfo_height()
                if w <= 1 or h <= 1:
                    self.canvas_pepper.update_idletasks()
                cw = max(self.canvas_pepper.winfo_width(), 240)
                ch = max(self.canvas_pepper.winfo_height(), 180)
                disp = gui_image.resize((cw, ch), _RESAMPLE_PIXEL)
                self._pepper_photo = ImageTk.PhotoImage(disp)
                self.canvas_pepper.delete("placeholder")
                pv = self._pepper_video_item
                if pv is None:
                    self._pepper_video_item = self.canvas_pepper.create_image(
                        0, 0, image=self._pepper_photo, anchor=tk.NW, tags="pepper_video")
                else:
                    self.canvas_pepper.itemconfig(pv, image=self._pepper_photo)
                self._pepper_cam_frame_err = 0
                if not getattr(self, "_pepper_first_frame", False):
                    self._pepper_first_frame = True
                    _ip = getattr(self, "_mjpeg_ip", "127.0.0.1")
                    self.log.append(
                        "Pepper VR streams (connect GUI PC): "
                        "http://%s:8080/pepper.jpg  top | "
                        "/pepper_bottom.jpg  mouth | "
                        "/pepper_depth.jpg  depth (grayscale). "
                        "Browser: /pepper.html" % _ip,
                        SUCCESS,
                    )
        except Exception as e:
            n = getattr(self, "_pepper_cam_frame_err", 0) + 1
            self._pepper_cam_frame_err = n
            if n <= 5 or n % 60 == 0:
                self.log.append("Pepper camera frame: %s" % e, DANGER)
        if self._pepper_cam_enabled:
            self._pepper_tick_id = self.master.after(33, self._pepper_camera_tick)

    def _apply_style(self):
        """Configure ttk styles (unused widgets future-proofing)."""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TScrollbar", background=SURFACE_2, troughcolor=BG,
                        arrowcolor=TEXT_SEC, borderwidth=0)

    def _apply_queued_motion(self):
        """Apply ALMotion commands posted from worker threads (NAOqi is reliable on GUI thread)."""
        cmds = []
        while True:
            try:
                cmds.append(self.q_motion.get_nowait())
            except Empty:
                break
        if not cmds:
            return
        try:
            motion = self.session.service("ALMotion")
            for c in cmds:
                kind = c[0]
                if kind == "mirror":
                    _, names, angles, frac = c
                    motion.setAngles(names, angles, frac)
                elif kind == "wrist":
                    motion.setAngles(["RWristYaw"], [-1.3], 0.15)
                elif kind == "arm_mirror":
                    _, names, angles, frac = c
                    motion.setAngles(names, angles, frac)
        except Exception as e:
            n = getattr(self, "_motion_apply_err", 0) + 1
            self._motion_apply_err = n
            if n <= 8:
                self.log.append("Motion (GUI thread): %s" % e, DANGER)

    def _wake_pepper_motion_on_main(self):
        try:
            m = self.session.service("ALMotion")
            m.wakeUp()
            self.log.append("ALMotion.wakeUp() OK.", SUCCESS)
        except Exception as e:
            self.log.append("wakeUp: %s" % e, WARNING)
        try:
            life = self.session.service("ALAutonomousLife")
            current = life.getState()
            if current != "solitary":
                life.setState("solitary")
                self.log.append("AutonomousLife -> solitary (was: %s)." % current, SUCCESS)
            else:
                self.log.append("AutonomousLife already solitary.", SUCCESS)
        except Exception as e:
            self.log.append("AutonomousLife: %s" % e, WARNING)

    def _prime_arm_mirror_motors(self):
        try:
            m = self.session.service("ALMotion")
            m.wakeUp()
            m.setStiffnesses(
                ["LShoulderPitch", "LShoulderRoll", "LElbowRoll",
                 "RShoulderPitch", "RShoulderRoll", "RElbowRoll"],
                1.0,
            )
            self.log.append("Arm mirror: motors primed on GUI thread.", SUCCESS)
        except Exception as e:
            self.log.append("Arm mirror prime: %s" % e, DANGER)

    # ---------------------------------------------------------------- Actions
    def connect_pepper(self):
        self.lbl_conn.configure(text="Connecting...")
        self.log.append("Attempting connection...")

        try:
            ip   = self.text_ip.get().strip()
            port = int(self.text_port.get().strip())
        except ValueError:
            self.lbl_conn.configure(text="Invalid port number.")
            self.badge_conn.set_state("ERROR")
            return

        try:
            self.session.connect("tcp://%s:%d" % (ip, port))
        except RuntimeError:
            self.lbl_conn.configure(text="Cannot connect - check IP/port.")
            self.badge_conn.set_state("ERROR")
            self.log.append("Connection FAILED to %s:%d" % (ip, port), DANGER)
            return

        # Success
        self.badge_conn.set_state("CONNECTED")
        self.btn_connect.configure(text="Connected (OK)", state=tk.DISABLED,
                                   bg=SUCCESS)
        self.text_ip.configure(state=tk.DISABLED)
        self.text_port.configure(state=tk.DISABLED)
        self.lbl_conn.configure(text="Connected to %s:%d" % (ip, port))
        self.btn_locomotion.configure(state=tk.NORMAL)
        self.btn_test.configure(state=tk.NORMAL)
        self.btn_rec.configure(state=tk.NORMAL)
        self.btn_fwd.configure(state=tk.NORMAL)
        self.btn_back.configure(state=tk.NORMAL)
        self.btn_left.configure(state=tk.NORMAL)
        self.btn_right.configure(state=tk.NORMAL)
        self.btn_rotl.configure(state=tk.NORMAL)
        self.btn_rotr.configure(state=tk.NORMAL)
        self.btn_stopmove.configure(state=tk.NORMAL)
        self.btn_track_user.configure(state=tk.NORMAL)
        self.btn_tablet.configure(state=tk.NORMAL)
        self.btn_keyboard_teleop.configure(state=tk.NORMAL)
        self.btn_body_drive.configure(state=tk.NORMAL)
        self.btn_arm_mirror.configure(state=tk.NORMAL)
        self.btn_vr_drive.configure(state=tk.NORMAL)
        self.log.append("Connected to %s:%d" % (ip, port), SUCCESS)
        self.master.after(0, self._wake_pepper_motion_on_main)

        # Start speech thread
        self.st = SpeechThread(self.session, self.q_speech, self.q_record, self.q_button)
        self.st.start()

        # Pepper onboard camera preview/stream.
        self._pepper_first_frame = False
        self._pepper_sz_logged = 0
        if ENABLE_PEPPER_CAMERA_IN_GUI or ENABLE_PEPPER_STREAM_SERVER:
            self._start_pepper_camera()
            if not ENABLE_PEPPER_CAMERA_IN_GUI:
                self.log.append("Pepper GUI preview disabled; Unity stream remains active.", WARNING)
        else:
            self.log.append("Pepper camera preview disabled in GUI.", WARNING)

    def _start_mode(self, teleoperate):
        if self.pac and self.pac.is_alive():
            self.lbl_feedback.configure(text="Already running. Press Stop first.")
            return

        # Locomotion mode relies on approach behavior.
        if (not teleoperate) and self.approach.get() == 0:
            self.lbl_feedback.configure(text="Enable 'Search User' before Start Locomotion.")
            return

        approach_req = bool(self.approach.get())
        approach_only = approach_req and (not teleoperate)

        self.pac = PepperApproachControl(
            self.session, False, approach_req, approach_only,
            self.q_pepper, self.q_appr_teleop, None)
        self.pac.start()

        self.log.append(
            "Tracker must publish body keypoints on tcp://127.0.0.1:1234 (Start_Pepper_Azure.bat).",
            ACCENT,
        )
        self.btn_locomotion.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)

        mode = "MIRRORING" if teleoperate else "DRIVING"
        self.badge_mode.set_state(mode)
        self.log.append("Started - mode: %s" % mode, SUCCESS)
        self._run_countdown(3)

    def start_mirroring(self):
        self._start_mode(teleoperate=True)

    def start_locomotion(self):
        self._start_mode(teleoperate=False)

    def stop_pepper(self):
        self.q_pepper.put(True)
        self.btn_stop.configure(state=tk.DISABLED)
        self.btn_locomotion.configure(state=tk.NORMAL)
        self.badge_mode.set_state("IDLE")
        self.log.append("Stopped.", WARNING)

    def test_move(self):
        """Fire a raw move(0.25, 0, 0) for 2 s to confirm locomotion API."""
        self.log.append("TEST: firing move(0.25,0,0) for 2 s...")
        self.btn_test.configure(state=tk.DISABLED)

        def _do():
            try:
                motion = self.session.service("ALMotion")
                motion.move(0.25, 0.0, 0.0)
                time.sleep(2.0)
                motion.move(0.0, 0.0, 0.0)
                self.q_appr_teleop.put("TEST move done.")
                self.log.append("TEST: done.", SUCCESS)
            except Exception as e:
                self.q_appr_teleop.put("TEST ERROR: %s" % e)
                self.log.append("TEST ERROR: %s" % e, DANGER)
            finally:
                self.master.after(0, lambda: self.btn_test.configure(state=tk.NORMAL))

        t = threading.Thread(target=_do)
        t.daemon = True
        t.start()

    def _motion_nudge(self, x, y, theta, log_cmd=True):
        try:
            motion = self.session.service("ALMotion")
            motion.moveToward(float(x), float(y), float(theta))
            if log_cmd:
                self.log.append("Move cmd: x=%.2f y=%.2f th=%.2f" % (x, y, theta))
        except Exception as e:
            self.log.append("Move ERROR: %s" % e, DANGER)

    def toggle_user_tracking(self):
        try:
            life = self.session.service("ALAutonomousLife")
            if not self.user_tracking_on:
                life.setAutonomousAbilityEnabled("BasicAwareness", True)
                self.user_tracking_on = True
                self.btn_track_user.configure(text="Stop User Tracking", bg=DANGER)
                self.log.append("Pepper user tracking enabled.", SUCCESS)
            else:
                life.setAutonomousAbilityEnabled("BasicAwareness", False)
                self.user_tracking_on = False
                self.btn_track_user.configure(text="Track User (Pepper Camera)", bg=SURFACE_2)
                self.log.append("Pepper user tracking disabled.", WARNING)
        except Exception as e:
            self.log.append("Tracking ERROR: %s" % e, DANGER)

    def toggle_tablet_feed(self):
        """Show/hide the operator's MediaPipe feed on Pepper's chest tablet."""
        try:
            tablet = self.session.service("ALTabletService")
        except Exception as e:
            self.log.append("Tablet service unavailable: %s" % e, DANGER)
            return

        if self._tablet_feed_on:
            try:
                tablet.hideWebview()
                tablet.resetTablet()
            except Exception:
                pass
            self._tablet_feed_on = False
            self.btn_tablet.configure(text="Show Operator on Pepper Tablet", bg=SURFACE_2)
            self.log.append("Tablet feed hidden.", WARNING)
        else:
            url = "http://%s:8080/" % self._mjpeg_ip
            try:
                # Reset first so any previous page is fully cleared
                try:
                    tablet.resetTablet()
                except Exception:
                    pass
                tablet.showWebview(url)
                self._tablet_feed_on = True
                self.btn_tablet.configure(text="Hide Tablet Feed", bg=DANGER)
                self.log.append(
                    "Tablet feed ON -> %s  (JS polling, ~8 fps). "
                    "Make sure Pepper is on the same network as this PC." % url,
                    SUCCESS,
                )
            except Exception as e:
                self.log.append("Tablet showWebview failed: %s" % e, DANGER)

    def open_pepper_preview(self):
        """Open Pepper camera preview page in default browser."""
        url = "http://%s:8080/pepper.html" % getattr(self, "_mjpeg_ip", "127.0.0.1")
        try:
            webbrowser.open_new(url)
            self.log.append("Opened Pepper preview: %s" % url, SUCCESS)
        except Exception as e:
            self.log.append("Open preview failed: %s" % e, DANGER)

    def request_remote_action(self, action):
        """
        Schedule a GUI action from HTTP thread onto Tk main thread.
        Returns True if action is accepted.
        """
        act = (action or "").strip().lower()
        dispatch = {
            "toggle_vr_drive": self.toggle_vr_drive,
            "toggle_arm_mirror": self.toggle_arm_mirror,
            "toggle_body_drive": self.toggle_body_drive,
            "toggle_keyboard": self.toggle_keyboard_teleop,
            "toggle_keyboard_teleop": self.toggle_keyboard_teleop,
            "stop_all_drive": self._remote_stop_all_drive,
        }
        fn = dispatch.get(act)
        if fn is None:
            return False
        self.master.after(0, fn)
        return True

    def _remote_stop_all_drive(self):
        if self.vr_drive and self.vr_drive.is_alive():
            self.toggle_vr_drive()
        if self.body_drive and self.body_drive.is_alive():
            self.toggle_body_drive()

    def get_remote_status(self):
        conn_txt = ""
        try:
            conn_txt = self.lbl_conn.cget("text")
        except Exception:
            pass
        mode_txt = ""
        try:
            mode_txt = self.badge_mode.cget("text")
        except Exception:
            pass
        return {
            "ok": True,
            "connected": conn_txt.startswith("Connected"),
            "mode": mode_txt.replace("*", "").strip() if mode_txt else "IDLE",
            "arm_mirror": bool(self.arm_mirror and self.arm_mirror.is_alive()),
            "body_drive": bool(self.body_drive and self.body_drive.is_alive()),
            "vr_drive": bool(self.vr_drive and self.vr_drive.is_alive()),
            "keyboard_teleop": bool(self.keyboard_teleop_on),
            "mjpeg_ip": getattr(self, "_mjpeg_ip", "127.0.0.1"),
        }

    def toggle_keyboard_teleop(self):
        self.keyboard_teleop_on = not self.keyboard_teleop_on
        if self.keyboard_teleop_on:
            self.btn_keyboard_teleop.configure(text="Disable Keyboard Teleop", bg=DANGER)
            self.log.append("Keyboard teleop ON (WASD move, Q/E rotate, X stop).", SUCCESS)
        else:
            self.btn_keyboard_teleop.configure(text="Enable Keyboard Teleop (WASD/QE)", bg=SURFACE_2)
            self._teleop_pressed.clear()
            self._motion_nudge(0.0, 0.0, 0.0)
            self.log.append("Keyboard teleop OFF.", WARNING)

    def toggle_body_drive(self):
        if self.body_drive and self.body_drive.is_alive():
            self.body_drive.stop()
            self.body_drive = None
            self.btn_body_drive.configure(text="Start Body Drive (Gestures)", bg=SURFACE_2)
            self.log.append("Body Drive OFF.", WARNING)
            return

        # Mutually exclusive with VR Drive (both call motion.moveToward and
        # would otherwise fight each other at ~10 Hz causing jittery/intermittent motion).
        if self.vr_drive and self.vr_drive.is_alive():
            self.vr_drive.stop()
            try:
                self.mjpeg_server.vr_drive = None
            except Exception:
                pass
            self.vr_drive = None
            self.btn_vr_drive.configure(text="VR Drive (Unity Headset)", bg=SURFACE_2)
            self.log.append("Auto-stopped VR Drive (mutually exclusive with Body Drive).", WARNING)

        self.body_drive = BodyDriveThread(self.session, self.q_appr_teleop, self.q_gesture)
        self.body_drive.start()
        self.btn_body_drive.configure(text="Stop Body Drive", bg=DANGER)
        self.log.append("Body Drive ON (lean to move, hands-up to stop).", SUCCESS)

    def toggle_arm_mirror(self):
        if self.arm_mirror and self.arm_mirror.is_alive():
            self.arm_mirror.stop()
            self.arm_mirror = None
            self.btn_arm_mirror.configure(text="Start Arm Mirror (MediaPipe)", bg=SURFACE_2)
            self.log.append("Arm Mirror OFF.", WARNING)
            return

        self.arm_mirror = ArmMirrorThread(
            self.session,
            self.q_appr_teleop,
            self.q_gesture,
            one_to_one=ARM_ONE_TO_ONE_MAPPING,
        )
        self.arm_mirror.start()
        self.btn_arm_mirror.configure(text="Stop Arm Mirror", bg=DANGER)
        self.badge_mode.set_state("MIRRORING")
        mode_label = "one-to-one" if ARM_ONE_TO_ONE_MAPPING else "mirrored"
        self.log.append("Arm Mirror ON (%s MediaPipe mapping)." % mode_label, SUCCESS)

    def toggle_vr_drive(self):
        if self.vr_drive and self.vr_drive.is_alive():
            self.vr_drive.stop()
            self.mjpeg_server.vr_drive = None
            self.vr_drive = None
            self.btn_vr_drive.configure(text="VR Drive (Unity Headset)", bg=SURFACE_2)
            self.badge_mode.set_state("IDLE")
            self.log.append("VR Drive OFF.", WARNING)
            return

        # Mutually exclusive with Body Drive (both drive motion.moveToward).
        if self.body_drive and self.body_drive.is_alive():
            self.body_drive.stop()
            self.body_drive = None
            self.btn_body_drive.configure(text="Start Body Drive (Gestures)", bg=SURFACE_2)
            self.log.append("Auto-stopped Body Drive (mutually exclusive with VR Drive).", WARNING)

        self.vr_drive = VRDriveThread(self.session, self.q_appr_teleop)
        self.mjpeg_server.vr_drive = self.vr_drive
        self.vr_drive.start()
        self.btn_vr_drive.configure(text="Stop VR Drive", bg=DANGER)
        self.badge_mode.set_state("DRIVING")
        _ip = getattr(self, "_mjpeg_ip", "127.0.0.1")
        self.log.append(
            "VR Drive ON. Unity should POST to http://%s:8080/vr_move" % _ip,
            SUCCESS,
        )

    def _on_key_press(self, event):
        if not self.keyboard_teleop_on:
            return
        k = (event.keysym or "").lower()
        if k in ("w", "a", "s", "d", "q", "e", "x"):
            self._teleop_pressed.add(k)

    def _on_key_release(self, event):
        k = (event.keysym or "").lower()
        if k in self._teleop_pressed:
            self._teleop_pressed.remove(k)

    def _keyboard_teleop_tick(self):
        if self.keyboard_teleop_on:
            x = y = theta = 0.0
            if "w" in self._teleop_pressed:
                x += 0.35
            if "s" in self._teleop_pressed:
                x -= 0.35
            if "a" in self._teleop_pressed:
                y += 0.25
            if "d" in self._teleop_pressed:
                y -= 0.25
            if "q" in self._teleop_pressed:
                theta += 0.50
            if "e" in self._teleop_pressed:
                theta -= 0.50
            if "x" in self._teleop_pressed:
                x = y = theta = 0.0
                self._teleop_pressed.clear()
            self._motion_nudge(x, y, theta, log_cmd=False)
        self.master.after(120, self._keyboard_teleop_tick)

    def start_talk(self):
        self.q_stop.put("StopRec")
        self.btn_rec.configure(text="Stop Talking", command=self.stop_talk, bg=DANGER)
        self.q_record.put("Rec")
        self.log.append("Voice recording started.", ACCENT)

    def stop_talk(self):
        self.q_record.put("StopRec")
        self.btn_rec.configure(text="Start Talking", command=self.start_talk,
                               bg=SURFACE_2)
        self.q_stop.put("Rec")
        self.log.append("Voice recording stopped.")

    # ---------------------------------------------------------------- Countdown
    def _run_countdown(self, count):
        if count <= 0:
            if self._countdown_win:
                self.canvas.delete(self._countdown_win)
                self._countdown_win = None
            return

        self.canvas.update_idletasks()
        w = max(self.canvas.winfo_width(), 240)
        h = max(self.canvas.winfo_height(), 180)

        if self._countdown_win:
            self.canvas.delete(self._countdown_win)

        self._countdown_win = self.canvas.create_text(
            w // 2, h // 2,
            text=str(count),
            font=("Segoe UI", 80, "bold"),
            fill=ACCENT,
            tags="countdown"
        )
        self.master.after(1000, lambda: self._run_countdown(count - 1))

    # ---------------------------------------------------------------- Closing
    def on_closing(self):
        lf_tid = getattr(self, "_live_feed_tick_id", None)
        self._live_feed_tick_id = None
        if lf_tid is not None:
            try:
                self.master.after_cancel(lf_tid)
            except Exception:
                pass

        self._live_feed_worker_run = False
        lt = getattr(self, "_live_feed_thread", None)
        if lt is not None and lt.is_alive():
            lt.join(timeout=1.5)

        self.q_record.put("StopRun")
        self.q_stop.put("StopRun")

        if self.st and self.st.is_alive():
            self.st.join(timeout=2)

        if self.ok_pepper and self.ok_pepper.is_alive():
            self.ok_pepper.join(timeout=2)

        if self.pac and self.pac.is_alive():
            self.q_pepper.put(True)
            self.pac.join(timeout=3)
        if self.body_drive and self.body_drive.is_alive():
            self.body_drive.stop()
            self.body_drive.join(timeout=2)
        if self.arm_mirror and self.arm_mirror.is_alive():
            self.arm_mirror.stop()
            self.arm_mirror.join(timeout=2)
        if self.vr_drive and self.vr_drive.is_alive():
            self.vr_drive.stop()
            self.mjpeg_server.vr_drive = None
            self.vr_drive.join(timeout=2)

        self._stop_pepper_camera()

        if self.feed_sub is not None:
            self.feed_sub.close()
        self._stop_mediapipe_tracker()

        self.master.destroy()

    # ---------------------------------------------------------------- Queue polling
    def start(self):
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.master.bind("<KeyPress>", self._on_key_press)
        self.master.bind("<KeyRelease>", self._on_key_release)
        self.master.after(120, self._keyboard_teleop_tick)
        if self.feed_sub is not None:
            self._live_feed_worker_run = True
            self._live_feed_thread = threading.Thread(target=self._live_feed_worker_loop)
            self._live_feed_thread.daemon = True
            self._live_feed_thread.start()
        if EMBED_PREVIEWS_IN_GUI:
            self._live_feed_tick_id = self.master.after(16, self._tick_live_feed)
        self.master.after(800, self._maybe_autostart_tracker)
        self.master.after(250, self._poll_queues)
        self.master.mainloop()

    def _poll_queues(self):
        self._poll_tracker_process()
        self._apply_queued_motion()
        if not EMBED_PREVIEWS_IN_GUI:
            tracker_on = self._tracker_proc is not None and self._tracker_proc.poll() is None
            body_on = self.body_drive is not None and self.body_drive.is_alive()
            arm_on = self.arm_mirror is not None and self.arm_mirror.is_alive()
            vr_on = self.vr_drive is not None and self.vr_drive.is_alive()
            self.lbl_dbg_tracker.configure(
                text="Tracker: %s (ZMQ keypoints tcp://127.0.0.1:1234, frames tcp://127.0.0.1:1236)"
                     % ("RUNNING" if tracker_on else "not running"))
            self.lbl_dbg_streams.configure(
                text="HTTP streams: http://%s:8080/frame.jpg | /pepper.jpg | /pepper_bottom.jpg | /pepper_depth.jpg"
                     % getattr(self, "_mjpeg_ip", "127.0.0.1"))
            self.lbl_dbg_modes.configure(
                text="Modes: arm_mirror=%s, body_drive=%s, vr_drive=%s, keyboard=%s"
                     % ("ON" if arm_on else "off",
                        "ON" if body_on else "off",
                        "ON" if vr_on else "off",
                        "ON" if self.keyboard_teleop_on else "off"))

        # Speech recognition text
        if not self.q_speech.empty():
            text = self.q_speech.get(block=False)
            if text:
                self.lbl_speech.configure(text=text)
                self.log.append("Speech: " + text)

        # Feedback from approach/teleop thread
        if not self.q_appr_teleop.empty():
            msg = self.q_appr_teleop.get(block=False)
            if msg:
                self.lbl_feedback.configure(text=msg)
                # Update mode badge from status messages
                if "MIRRORING" in msg.upper():
                    self.badge_mode.set_state("MIRRORING")
                elif "DRIVING" in msg.upper():
                    self.badge_mode.set_state("DRIVING")
                elif "stopped" in msg.lower() or "terminated" in msg.lower():
                    self.badge_mode.set_state("IDLE")
                self.log.append(msg)

        # Gesture-triggered mode switch (both-hands-high held for 2.5 s)
        if not self.q_gesture.empty():
            try:
                cmd = self.q_gesture.get_nowait()
                if cmd == "switch_mode":
                    arm_on   = self.arm_mirror  is not None and self.arm_mirror.is_alive()
                    drive_on = self.body_drive  is not None and self.body_drive.is_alive()
                    if arm_on:
                        self.log.append("GESTURE -> switching: Arm Mirror OFF, Body Drive ON.", SUCCESS)
                        self.toggle_arm_mirror()
                        self.master.after(300, self.toggle_body_drive)
                    elif drive_on:
                        self.log.append("GESTURE -> switching: Body Drive OFF, Arm Mirror ON.", SUCCESS)
                        self.toggle_body_drive()
                        self.master.after(300, self.toggle_arm_mirror)
            except Exception:
                pass

        # Voice button commands
        if not self.q_button.empty():
            cmd = self.q_button.get(block=False)
            if cmd:
                self.lbl_speech.configure(text=cmd)
                cmd_l = cmd.lower()
                if cmd_l == 'connect':
                    self.btn_connect.invoke()
                elif cmd_l == 'stop talking' and "Stop" in self.btn_rec.cget('text'):
                    self.btn_rec.invoke()
                elif cmd_l == 'start talking' and "Start" in self.btn_rec.cget('text'):
                    self.btn_rec.invoke()
                elif cmd_l == 'stop pepper' and self.btn_stop.cget('state') == tk.NORMAL:
                    self.btn_stop.invoke()

        self.master.after(250, self._poll_queues)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    session = qi.Session()

    root = tk.Tk()
    app  = PepperGui(root, session)
    app.start()