# -*- coding: utf-8 -*-
"""
web_app.py - browser control panel for Pepper / NAO
====================================================
Replaces the Tk window with a web UI (pepper_teleoperation/web/) served from
this process. The robot logic is unchanged: the arm-mirror / body-drive /
VR-drive threads, the :8080 stream server used by Unity and the tablet, and
the NAO dance-study engine are all reused from pepper_gui.py / utils/.

Why it is faster than the Tk GUI: the browser renders on its own, and all
NAOqi calls (camera polling, wake-up, toggles) run on one dedicated loop thread
instead of blocking the window.

Run (pepper27_32 env, Choregraphe lib on PYTHONPATH - see Start_Pepper_Azure.bat):
    python web_app.py                 # opens http://127.0.0.1:8000
    python web_app.py --tab study --no-tracker
    python web_app.py --lan           # also reachable from other devices on the LAN

The previous Tk GUI is still available:  python pepper_gui.py
"""

from __future__ import print_function

import argparse
import heapq
import itertools
import json
import os
import sys
import threading
import time
import traceback
import webbrowser
from collections import deque

try:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn
    import urlparse
except ImportError:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
    from urllib import parse as urlparse

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty

import qi

# Importing the legacy GUI module gives us the robot threads and the stream
# server; it does not open a window.
import pepper_gui as legacy
from utils.nao_dance import (
    DEFAULT_CONFIG, MOVES, ROBOT_LANGUAGE, ROUND, SCENARIOS,
    DanceController, NaoRobot, SimRobot, detect_robot_type, format_captured_pose,
    set_tts_language,
)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
STUDY_LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             "..", "study_logs"))


class ActionError(Exception):
    """An action was refused or failed; the message is shown to the operator."""


# ---------------------------------------------------------------------------
# Main loop: one thread owns NAOqi (replaces Tk's mainloop / master.after)
# ---------------------------------------------------------------------------
class MainLoop(object):
    def __init__(self):
        self._q = []
        self._cv = threading.Condition()
        self._seq = itertools.count()
        self.running = True
        self.thread = None

    def after(self, delay_s, fn, *args):
        with self._cv:
            heapq.heappush(self._q, (time.time() + delay_s, next(self._seq), fn, args))
            self._cv.notify()

    def call_soon(self, fn, *args):
        self.after(0.0, fn, *args)

    def every(self, interval_s, fn):
        def _tick():
            try:
                fn()
            finally:
                if self.running:
                    self.after(interval_s, _tick)
        self.after(interval_s, _tick)

    def call_sync(self, fn, timeout=30.0):
        """Run fn on the loop thread and return its result (or raise its error)."""
        if threading.current_thread() is self.thread:
            return fn()
        box = {}
        done = threading.Event()

        def _run():
            try:
                box["r"] = fn()
            except Exception as e:
                box["e"] = e
            finally:
                done.set()
        self.call_soon(_run)
        if not done.wait(timeout):
            raise ActionError("Robot did not respond within %ds" % timeout)
        if "e" in box:
            raise box["e"]
        return box.get("r")

    def stop(self):
        with self._cv:
            self.running = False
            self._cv.notify()

    def run(self):
        self.thread = threading.current_thread()
        while self.running:
            with self._cv:
                while self.running and (not self._q or self._q[0][0] > time.time()):
                    wait = (self._q[0][0] - time.time()) if self._q else 0.5
                    self._cv.wait(max(0.001, min(wait, 0.5)))
                if not self.running:
                    break
                _, _, fn, args = heapq.heappop(self._q)
            try:
                fn(*args)
            except Exception:
                traceback.print_exc()


# ---------------------------------------------------------------------------
# Robot control (port of PepperGui without the widgets)
# ---------------------------------------------------------------------------
class ControlApp(object):
    def __init__(self, loop, autostart_tracker=True, voice=True):
        self.loop = loop
        self.session = qi.Session()
        self.connected = False
        self.connecting = False
        self.ip, self.port = "192.168.1.61", 9559
        self.robot_type = None

        self._log = deque(maxlen=600)
        self._log_id = itertools.count(1)
        self._log_lock = threading.Lock()

        # Queues shared with the legacy threads
        self.q_speech = Queue()
        self.q_record = Queue()
        self.q_button = Queue()
        self.q_stop = Queue()
        self.q_pepper = Queue()
        self.q_appr_teleop = Queue()
        self.q_gesture = Queue()

        self.st = None
        self.ok_pepper = None
        self.pac = None
        self.arm_mirror = None
        self.body_drive = None
        self.vr_drive = None
        self.keyboard_on = False
        self._drive_cmd = (0.0, 0.0, 0.0)
        self._drive_t = 0.0
        self._drive_sent_zero = True
        self.track_user_on = False
        self.tablet_on = False
        self.talking = False
        self.speech_text = ""
        self.feedback = ""
        self._ask_busy = False

        self._tracker_proc = None
        self._tracker_external = False
        self._tracker_last_exit = None
        self.autostart_tracker = autostart_tracker

        self._video = None
        self._cam_subs = []
        self._cam_tick_n = 0
        self._cam_err = 0

        self.mjpeg_server = legacy.MjpegServer(port=8080)
        self.mjpeg_server.gui = self          # Unity /control + /status use this
        self.mjpeg_server.start()
        self.mjpeg_ip = self.mjpeg_server.get_local_ip()

        self.feed_sub = None
        try:
            self.feed_sub = legacy.LiveFeedSubscriber()
            t = threading.Thread(target=self._feed_worker)
            t.daemon = True
            t.start()
        except Exception as e:
            self.log("Operator feed subscriber failed: %s" % e, "error")

        if voice:
            try:
                self.ok_pepper = legacy.OkPepperThread(self.q_button, self.q_stop)
                self.ok_pepper.start()
                self.q_stop.put("Rec")
            except Exception as e:
                self.log("Voice commands unavailable: %s" % e, "warn")

        self.study = StudyManager(self)

        loop.every(0.25, self._poll)
        loop.every(0.1, self._drive_tick)
        loop.every(0.05, self._camera_tick)
        if autostart_tracker and legacy.AUTO_START_MEDIAPIPE_TRACKER:
            loop.after(0.8, self._autostart_tracker)
        self.log("Control panel ready. Streams for Unity/tablet: http://%s:8080/" % self.mjpeg_ip, "accent")

    # ------------------------------------------------------------ logging
    def log(self, msg, level="info"):
        with self._log_lock:
            self._log.append({"id": next(self._log_id), "t": time.strftime("%H:%M:%S"),
                              "msg": msg, "level": level})
        print("[%s] %s" % (level, msg))

    def log_since(self, since):
        with self._log_lock:
            return [e for e in self._log if e["id"] > since]

    # ------------------------------------------------------------ capabilities
    @property
    def is_nao(self):
        return self.robot_type == "nao"

    def caps(self):
        c = self.connected
        return {
            "drive": c and not self.is_nao,         # NAO would walk
            "tablet": c and not self.is_nao,
            "ask": c and not self.is_nao,
            "arm_mirror": c,
            "track_user": c,
            "voice": c and self.st is not None,
        }

    def _require(self, cap, what):
        if not self.connected:
            raise ActionError("Connect to the robot first.")
        if not self.caps()[cap]:
            raise ActionError("%s is not available on %s." % (what, (self.robot_type or "this robot").upper()))

    # ------------------------------------------------------------ connection
    def connect(self, ip=None, port=None):
        if self.connected:
            return "Already connected to %s:%d" % (self.ip, self.port)
        ip = (ip or self.ip).strip()
        try:
            port = int(port or self.port)
        except ValueError:
            raise ActionError("Invalid port.")
        self.ip, self.port = ip, port
        self.connecting = True
        self.log("Connecting to %s:%d..." % (ip, port))
        try:
            self._connect_with_timeout("tcp://%s:%d" % (ip, port), 8.0)
        except RuntimeError as e:
            self.session = qi.Session()       # fresh session for the next attempt
            self.log("Connection to %s:%d failed: %s" % (ip, port, e), "error")
            raise ActionError("Cannot connect to %s:%d - check the IP and that the robot is on." % (ip, port))
        finally:
            self.connecting = False
        self.connected = True
        self.robot_type = detect_robot_type(self.session)
        self.log("Connected to %s:%d (%s)" % (ip, port, self.robot_type.upper()), "ok")
        if self.is_nao:
            self.log("NAO: driving, tablet and Pepper ask-demos are disabled (NAO would walk). "
                     "Arm Mirror and NAO Study are available.", "warn")
        self._wake()
        set_tts_language(self.session, ROBOT_LANGUAGE, lambda m: self.log(m.replace("[NAO] ", ""), "info"))
        try:
            self.st = legacy.SpeechThread(self.session, self.q_speech, self.q_record, self.q_button)
            self.st.start()
        except Exception as e:
            self.st = None
            self.log("Speech thread unavailable: %s" % e, "warn")
        if legacy.ENABLE_PEPPER_CAMERA_IN_GUI or legacy.ENABLE_PEPPER_STREAM_SERVER:
            self._start_camera()
        return "Connected"

    def _connect_with_timeout(self, url, timeout_s):
        """session.connect can block for a long time on a wrong IP; bound it."""
        try:
            fut = self.session.connect(url, _async=True)
        except TypeError:                       # very old qi: no async connect
            self.session.connect(url)
            return
        fut.wait(int(timeout_s * 1000))
        if not fut.isFinished():
            try:
                fut.cancel()
            except Exception:
                pass
            raise RuntimeError("no answer within %ds" % timeout_s)
        if fut.hasError():
            raise RuntimeError(fut.error())

    def _wake(self):
        try:
            self.session.service("ALMotion").wakeUp()
            self.log("Motors awake.", "ok")
        except Exception as e:
            self.log("wakeUp: %s" % e, "warn")
        try:
            life = self.session.service("ALAutonomousLife")
            if life.getState() != "solitary":
                life.setState("solitary")
        except Exception as e:
            self.log("AutonomousLife: %s" % e, "warn")

    # ------------------------------------------------------------ modes
    def toggle_arm_mirror(self):
        if self.arm_mirror and self.arm_mirror.is_alive():
            self.arm_mirror.stop()
            self.arm_mirror = None
            self.log("Arm Mirror off.", "warn")
            return
        self._require("arm_mirror", "Arm Mirror")
        if self.study.running:
            raise ActionError("A study take is running.")
        self.arm_mirror = legacy.ArmMirrorThread(self.session, self.q_appr_teleop, self.q_gesture,
                                                 one_to_one=legacy.ARM_ONE_TO_ONE_MAPPING)
        self.arm_mirror.start()
        self.log("Arm Mirror on - stand in front of the webcam.", "ok")

    def toggle_body_drive(self):
        if self.body_drive and self.body_drive.is_alive():
            self.body_drive.stop()
            self.body_drive = None
            self.log("Body Drive off.", "warn")
            return
        self._require("drive", "Body Drive")
        if self.vr_drive and self.vr_drive.is_alive():
            self.toggle_vr_drive()
        self.body_drive = legacy.BodyDriveThread(self.session, self.q_appr_teleop, self.q_gesture)
        self.body_drive.start()
        self.log("Body Drive on - lean to move, both hands up to stop.", "ok")

    def toggle_vr_drive(self):
        if self.vr_drive and self.vr_drive.is_alive():
            self.vr_drive.stop()
            self.mjpeg_server.vr_drive = None
            self.vr_drive = None
            self.log("VR Drive off.", "warn")
            return
        self._require("drive", "VR Drive")
        if self.body_drive and self.body_drive.is_alive():
            self.toggle_body_drive()
        self.vr_drive = legacy.VRDriveThread(self.session, self.q_appr_teleop)
        self.mjpeg_server.vr_drive = self.vr_drive
        self.vr_drive.start()
        self.log("VR Drive on - Unity should POST to http://%s:8080/vr_move" % self.mjpeg_ip, "ok")

    def toggle_keyboard(self):
        if self.keyboard_on:
            self.keyboard_on = False
            self.set_drive(0, 0, 0)
            if self.connected and not self.is_nao:
                try:
                    self.session.service("ALMotion").moveToward(0.0, 0.0, 0.0)
                except Exception:
                    pass
            self._drive_sent_zero = True
            self.log("Keyboard / pad driving off.", "warn")
            return
        self._require("drive", "Driving")
        self.keyboard_on = True
        self.log("Keyboard / pad driving on (WASD move, Q/E turn).", "ok")

    def set_drive(self, x, y, theta):
        """Called from HTTP threads at ~10 Hz while a key / pad button is held."""
        self._drive_cmd = (float(x), float(y), float(theta))
        self._drive_t = time.time()

    def _drive_tick(self):
        if not (self.connected and self.keyboard_on) or self.is_nao:
            return
        x, y, th = self._drive_cmd
        if time.time() - self._drive_t > 0.4:      # browser stopped sending -> stop
            x = y = th = 0.0
        moving = bool(x or y or th)
        if not moving and self._drive_sent_zero:
            return
        try:
            self.session.service("ALMotion").moveToward(
                max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y)), max(-1.0, min(1.0, th)))
            self._drive_sent_zero = not moving
        except Exception as e:
            self.log("Move error: %s" % e, "error")

    def toggle_track_user(self):
        self._require("track_user", "User tracking")
        life = self.session.service("ALAutonomousLife")
        self.track_user_on = not self.track_user_on
        life.setAutonomousAbilityEnabled("BasicAwareness", self.track_user_on)
        self.log("User tracking %s." % ("on" if self.track_user_on else "off"),
                 "ok" if self.track_user_on else "warn")

    def toggle_tablet(self):
        self._require("tablet", "Tablet feed")
        tablet = self.session.service("ALTabletService")
        if self.tablet_on:
            for fn in (tablet.hideWebview, tablet.resetTablet):
                try:
                    fn()
                except Exception:
                    pass
            self.tablet_on = False
            self.log("Tablet feed hidden.", "warn")
            return
        url = "http://%s:8080/" % self.mjpeg_ip
        try:
            tablet.resetTablet()
        except Exception:
            pass
        tablet.showWebview(url)
        self.tablet_on = True
        self.log("Tablet shows the operator feed (%s)." % url, "ok")

    def ask_demo(self, which):
        self._require("ask", "Ask-for-object demos")
        if self._ask_busy:
            raise ActionError("A demo is already running.")
        self._ask_busy = True
        tablet_url = "http://%s:8080/ask.html" % self.mjpeg_ip
        self.log("Ask demo '%s' started." % which, "accent")

        def _do():
            try:
                msg = legacy.play_ask_gesture(self.session, which,
                                              tablet_url=tablet_url if which == "ideal" else None)
                self.log(msg or "Ask demo done.", "ok")
            except Exception as e:
                self.log("Ask demo error: %s" % e, "error")
            finally:
                self._ask_busy = False
        t = threading.Thread(target=_do)
        t.daemon = True
        t.start()

    def start_approach(self):
        self._require("drive", "Search & approach")
        if self.pac and self.pac.is_alive():
            raise ActionError("Already running.")
        self.pac = legacy.PepperApproachControl(self.session, False, True, True,
                                                self.q_pepper, self.q_appr_teleop, None)
        self.pac.start()
        self.log("Search & approach started (needs the body tracker).", "ok")

    def stop_approach(self):
        if self.pac and self.pac.is_alive():
            self.q_pepper.put(True)
            self.log("Search & approach stopped.", "warn")
        self.pac = None

    def test_move(self):
        self._require("drive", "Test move")
        self.log("Test: moving forward for 2 s...")

        def _do():
            try:
                motion = self.session.service("ALMotion")
                motion.move(0.25, 0.0, 0.0)
                time.sleep(2.0)
                motion.move(0.0, 0.0, 0.0)
                self.log("Test move done.", "ok")
            except Exception as e:
                self.log("Test move error: %s" % e, "error")
        t = threading.Thread(target=_do)
        t.daemon = True
        t.start()

    def toggle_talk(self):
        self._require("voice", "Voice")
        if self.talking:
            self.q_record.put("StopRec")
            self.q_stop.put("Rec")
            self.talking = False
            self.log("Voice recording stopped.")
        else:
            self.q_stop.put("StopRec")
            self.q_record.put("Rec")
            self.talking = True
            self.log("Voice recording - speak now.", "accent")

    def stop_motion_modes(self):
        if self.arm_mirror and self.arm_mirror.is_alive():
            self.toggle_arm_mirror()
        if self.body_drive and self.body_drive.is_alive():
            self.toggle_body_drive()
        if self.vr_drive and self.vr_drive.is_alive():
            self.toggle_vr_drive()
        if self.keyboard_on:
            self.toggle_keyboard()
        self.stop_approach()

    def stop_all(self):
        self.stop_motion_modes()
        self.study.stop()
        if self.connected and not self.is_nao:
            try:
                self.session.service("ALMotion").moveToward(0.0, 0.0, 0.0)
            except Exception:
                pass
        self.log("STOP ALL - every mode stopped.", "error")

    # ------------------------------------------------------------ tracker
    def _tracker_running(self):
        return self._tracker_proc is not None and self._tracker_proc.poll() is None

    def _autostart_tracker(self):
        if self._tracker_ports_in_use():
            self._tracker_external = True
            self.log("Body tracker already running (started by the launcher).", "ok")
            return
        self.start_tracker()

    @staticmethod
    def _tracker_ports_in_use():
        """True if another process already publishes on the tracker ports 1234/1236."""
        ctx = legacy.zmq.Context()
        socks = []
        try:
            for port in (1234, 1236):
                s = ctx.socket(legacy.zmq.PUB)
                s.setsockopt(legacy.zmq.LINGER, 0)
                socks.append(s)
                s.bind("tcp://*:%d" % port)
            return False
        except Exception:
            return True
        finally:
            for s in socks:
                s.close()
            ctx.term()

    def start_tracker(self):
        if self._tracker_running():
            return "Tracker already running."
        if self._tracker_ports_in_use():
            self._tracker_external = True
            return "Tracker already running in another window."
        script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..",
                                              "openpose_wrap", "mediapipe_body_tracker.py"))
        if not os.path.exists(script):
            raise ActionError("Tracker script not found: %s" % script)
        import subprocess
        for py_cmd in legacy.TRACKER_PY_CANDIDATES:
            try:
                self._tracker_proc = subprocess.Popen(list(py_cmd) + [script],
                                                      cwd=os.path.dirname(script))
                self._tracker_last_exit = None
                self.log("Body tracker started (%s)." % " ".join(py_cmd), "ok")
                return "Started"
            except Exception as e:
                last = e
        raise ActionError("Could not start the tracker (%s). Is Python 3.10 installed?" % last)

    def stop_tracker(self):
        p, self._tracker_proc = self._tracker_proc, None
        if p is None:
            return
        try:
            p.terminate()
            for _ in range(20):
                if p.poll() is not None:
                    break
                time.sleep(0.05)
            if p.poll() is None:
                p.kill()
        except Exception:
            pass
        self.log("Body tracker stopped.", "warn")

    def restart_tracker(self):
        self.stop_tracker()
        return self.start_tracker()

    # ------------------------------------------------------------ feeds / camera
    def _feed_worker(self):
        while self.loop.running:
            jpg = self.feed_sub.get_latest_jpeg()
            if jpg:
                self.mjpeg_server.push(jpg)
                time.sleep(0.005)
            else:
                time.sleep(0.01)

    def _start_camera(self):
        self._stop_camera()
        if not legacy.PIL_AVAILABLE:
            self.log("Robot camera skipped (Pillow not installed).", "warn")
            return
        ts = int(time.time())
        specs = [{"key": "main", "camera": legacy.PEPPER_CAMERA_INDEX, "mode": "rgb"}]
        specs += [{"key": s["name"], "camera": int(s["camera"]), "mode": s["mode"]}
                  for s in legacy.PEPPER_VR_EXTRA_STREAMS]
        try:
            v = self.session.service("ALVideoDevice")
        except Exception as e:
            self.log("Camera service unavailable: %s" % e, "error")
            return
        self._video = v
        for sp in specs:
            try:
                link = v.subscribeCamera("webui_%s_%d" % (sp["key"], ts), sp["camera"], 1, 11, 10)
                self._cam_subs.append(dict(sp, link=link))
            except Exception as e:
                self.log("Camera '%s' not available on this robot (%s)." % (sp["key"], e), "warn")
        if self._cam_subs:
            self.log("Robot camera streaming: %s" % ", ".join(s["key"] for s in self._cam_subs), "ok")

    def _stop_camera(self):
        if self._video is not None:
            for sp in self._cam_subs:
                try:
                    self._video.unsubscribe(sp["link"])
                except Exception:
                    pass
        self._video = None
        self._cam_subs = []
        self.mjpeg_server.clear_pepper()

    def _camera_tick(self):
        """Grab robot camera frames (main every tick, extra cameras every 3rd)."""
        if self._video is None or not self._cam_subs:
            return
        self._cam_tick_n += 1
        push = {"main": self.mjpeg_server.push_pepper,
                "bottom": self.mjpeg_server.push_pepper_bottom,
                "depth": self.mjpeg_server.push_pepper_depth}
        for sp in self._cam_subs:
            if sp["key"] != "main" and self._cam_tick_n % 3:
                continue
            try:
                img = self._video.getImageRemote(sp["link"])
                if not img or len(img) < 7:
                    continue
                image = legacy._pepper_raw_to_pil(int(img[0]), int(img[1]), img[6], sp["mode"])
                if image is None:
                    continue
                buf = legacy.BytesIO()
                image.save(buf, format="JPEG", quality=65)
                if sp["key"] in push:
                    push[sp["key"]](buf.getvalue())
            except Exception as e:
                self._cam_err += 1
                if self._cam_err <= 5 or self._cam_err % 100 == 0:
                    self.log("Camera frame error: %s" % e, "warn")

    # ------------------------------------------------------------ periodic poll
    def _poll(self):
        p = self._tracker_proc
        if p is not None and p.poll() is not None:
            code = p.poll()
            self._tracker_proc = None
            if self._tracker_last_exit != code:
                self._tracker_last_exit = code
                self.log("Body tracker exited (code %s). Is the webcam used by another app?" % code, "error")

        while True:
            try:
                msg = self.q_appr_teleop.get_nowait()
            except Empty:
                break
            if msg:
                if msg != self.feedback and not msg.startswith("VR-DRIVE"):
                    self.log(msg)
                self.feedback = msg

        while True:
            try:
                cmd = self.q_gesture.get_nowait()
            except Empty:
                break
            if cmd == "switch_mode" and not self.is_nao:
                if self.arm_mirror and self.arm_mirror.is_alive():
                    self.log("Gesture: Arm Mirror -> Body Drive", "accent")
                    self.toggle_arm_mirror()
                    self.loop.after(0.3, self._safe_action, self.toggle_body_drive)
                elif self.body_drive and self.body_drive.is_alive():
                    self.log("Gesture: Body Drive -> Arm Mirror", "accent")
                    self.toggle_body_drive()
                    self.loop.after(0.3, self._safe_action, self.toggle_arm_mirror)

        while not self.q_speech.empty():
            text = self.q_speech.get_nowait()
            if text:
                self.speech_text = text
                self.log("Speech: %s" % text)

        while not self.q_button.empty():
            cmd = (self.q_button.get_nowait() or "").lower()
            self.speech_text = cmd or self.speech_text
            if cmd == "connect":
                self._safe_action(self.connect)
            elif cmd in ("start talking", "stop talking"):
                if (cmd == "start talking") != self.talking:
                    self._safe_action(self.toggle_talk)
            elif cmd == "stop pepper":
                self._safe_action(self.stop_all)

    def _safe_action(self, fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            self.log(str(e), "error")

    # ------------------------------------------------------------ HTTP-facing
    ACTIONS = ("connect", "toggle_arm_mirror", "toggle_body_drive", "toggle_vr_drive",
               "toggle_keyboard", "toggle_track_user", "toggle_tablet", "ask_demo",
               "start_approach", "stop_approach", "test_move", "toggle_talk", "stop_all",
               "start_tracker", "stop_tracker", "restart_tracker")

    def dispatch(self, action, args):
        args = args or {}
        if action.startswith("study_"):
            return self.study.dispatch(action[6:], args)
        if action not in self.ACTIONS:
            raise ActionError("Unknown action: %s" % action)
        fn = getattr(self, action)
        timeout = 40.0 if action == "connect" else 15.0
        return self.loop.call_sync(lambda: fn(**args), timeout=timeout)

    def request_remote_action(self, action):
        """Compatibility with Unity's GET :8080/control?action=..."""
        mapping = {"toggle_keyboard_teleop": "toggle_keyboard", "toggle_keyboard": "toggle_keyboard",
                   "toggle_vr_drive": "toggle_vr_drive", "toggle_arm_mirror": "toggle_arm_mirror",
                   "toggle_body_drive": "toggle_body_drive"}
        act = (action or "").strip().lower()
        if act == "stop_all_drive":
            def _stop():
                if self.vr_drive and self.vr_drive.is_alive():
                    self.toggle_vr_drive()
                if self.body_drive and self.body_drive.is_alive():
                    self.toggle_body_drive()
            self.loop.call_soon(self._safe_action, _stop)
            return True
        if act not in mapping:
            return False
        self.loop.call_soon(self._safe_action, getattr(self, mapping[act]))
        return True

    def _alive(self, t):
        return bool(t is not None and t.is_alive())

    def mode_label(self):
        if self.study.running:
            return "STUDY"
        if self._alive(self.vr_drive) or self._alive(self.body_drive) or self.keyboard_on:
            return "DRIVING"
        if self._alive(self.arm_mirror):
            return "MIRRORING"
        return "IDLE"

    def get_remote_status(self):
        return {"ok": True, "connected": self.connected, "mode": self.mode_label(),
                "arm_mirror": self._alive(self.arm_mirror), "body_drive": self._alive(self.body_drive),
                "vr_drive": self._alive(self.vr_drive), "keyboard_teleop": self.keyboard_on,
                "mjpeg_ip": self.mjpeg_ip}

    def snapshot(self, log_since=0, study_since=0):
        with self.mjpeg_server._lock:
            frames = {"operator": bool(self.mjpeg_server._frame),
                      "main": bool(self.mjpeg_server._frame_pepper),
                      "bottom": bool(self.mjpeg_server._frame_pepper_bottom),
                      "depth": bool(self.mjpeg_server._frame_pepper_depth)}
        return {
            "conn": {"connected": self.connected, "connecting": self.connecting,
                     "ip": self.ip, "port": self.port, "robot_type": self.robot_type},
            "caps": self.caps(),
            "mode": self.mode_label(),
            "modes": {"arm_mirror": self._alive(self.arm_mirror),
                      "body_drive": self._alive(self.body_drive),
                      "vr_drive": self._alive(self.vr_drive),
                      "keyboard": self.keyboard_on,
                      "track_user": self.track_user_on,
                      "tablet": self.tablet_on,
                      "approach": self._alive(self.pac),
                      "talking": self.talking,
                      "ask_busy": self._ask_busy},
            "tracker": {"running": self._tracker_running() or self._tracker_external},
            "frames": frames,
            "feedback": self.feedback,
            "speech_text": self.speech_text,
            "stream_base": "http://%s:8080" % self.mjpeg_ip,
            "log": self.log_since(log_since),
            "study": self.study.snapshot(study_since),
        }

    def meta(self):
        return {"scenarios": [{"key": k, "label": v} for k, v in SCENARIOS.items()],
                "round": ROUND, "moves": list(MOVES.keys()), "defaults": DEFAULT_CONFIG,
                "default_ip": self.ip, "default_port": self.port}

    def shutdown(self):
        self.study.stop()
        self.stop_motion_modes()
        self.q_record.put("StopRun")
        self.q_stop.put("StopRun")
        self._stop_camera()
        self.stop_tracker()
        if self.feed_sub is not None:
            try:
                self.feed_sub.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# NAO dance study (same behaviour as nao_study_gui.py)
# ---------------------------------------------------------------------------
class StudyManager(object):
    def __init__(self, app):
        self.app = app
        self.sim = True
        self.controller = None
        self.busy = False
        self._nao = None
        self._events = deque(maxlen=2000)
        self._ev_id = itertools.count(1)
        self._lock = threading.Lock()
        self._csv_file = None
        self._csv = None
        self.state = "IDLE"
        self.detail = "Choose a scenario and press Start take."
        self.position = None          # (round, move_index) of the current move
        self.take = None              # info about the current / last take

    @property
    def running(self):
        return self.controller is not None and self.controller.is_alive()

    def robot(self):
        app = self.app
        live = (not self.sim) and app.connected
        if not live:
            return SimRobot(log=lambda m: app.log(m, "info"))
        if app.robot_type == "pepper":
            raise ActionError("The dance is written for NAO's legs - use Simulation with Pepper.")
        if self._nao is None:
            self._nao = NaoRobot(app.session, log=lambda m: app.log(m, "warn"))
        return self._nao

    def dispatch(self, action, args):
        fn = {"set_sim": self.set_sim, "start": self.start, "stop": self.stop,
              "trigger": self.trigger, "resume": self.resume, "tool": self.tool,
              "preview": self.preview, "capture": self.capture}.get(action)
        if fn is None:
            raise ActionError("Unknown study action: %s" % action)
        return fn(**args)

    def set_sim(self, sim):
        if self.running:
            raise ActionError("Stop the take first.")
        if not sim and not self.app.connected:
            raise ActionError("Connect to NAO first (Teleoperation tab), or stay in Simulation.")
        self.sim = bool(sim)
        return self.sim

    def _config(self, cfg):
        c = dict(DEFAULT_CONFIG)
        for k, v in (cfg or {}).items():
            if k in c:
                c[k] = v
        c["rounds"] = max(1, int(c["rounds"]))
        c["beat_s"] = max(0.6, float(c["beat_s"]))
        c["slow_factor"] = max(1.0, float(c["slow_factor"]))
        c["trigger_round"] = int(c["trigger_round"])
        c["trigger_move"] = int(c["trigger_move"])
        for k in ("auto_trigger", "callouts", "restart_round_on_resume"):
            c[k] = bool(c[k])
        return c

    def start(self, scenario, take_id="take", config=None):
        if self.running:
            raise ActionError("A take is already running.")
        if self.busy:
            raise ActionError("Robot busy - wait for the current action.")
        if scenario not in SCENARIOS:
            raise ActionError("Unknown scenario.")
        robot = self.robot()
        cfg = self._config(config)
        if not robot.is_sim:
            self.app.loop.call_sync(self.app.stop_motion_modes)
        take_id = "".join(ch for ch in (take_id or "") if ch.isalnum() or ch in "-_") or "take"
        self._open_csv(take_id, scenario, cfg, robot.is_sim)
        self.take = {"id": take_id, "scenario": scenario, "sim": robot.is_sim, "config": cfg,
                     "started": time.time()}
        self.position = None
        self.controller = DanceController(robot, scenario, cfg, self._on_event)
        self.app.log("Study take %s - %s%s" % (take_id, SCENARIOS[scenario],
                                                " [SIMULATION]" if robot.is_sim else ""), "accent")
        self.controller.start()
        return "started"

    def stop(self):
        ctl = self.controller
        if ctl is not None and ctl.is_alive():
            ctl.stop()
            robot = ctl.robot
            t = threading.Thread(target=robot.stop_motion)
            t.daemon = True
            t.start()
            self.app.log("Study take stopped - NAO holds its pose (use Stand up / Sit down).", "error")

    def trigger(self):
        ctl = self.controller
        if ctl is None or not ctl.is_alive() or ctl.triggered:
            raise ActionError("No running take to trigger.")
        ctl.trigger_struggle("operator")

    def resume(self):
        ctl = self.controller
        if ctl is None or not ctl.is_alive() or not ctl.waiting:
            raise ActionError("NAO is not waiting.")
        ctl.resume()

    def _robot_job(self, label, fn):
        if self.running or self.busy:
            raise ActionError("Robot busy.")
        robot = self.robot()
        self.busy = True

        def _do():
            try:
                fn(robot)
                self.app.log("%s: done." % label, "ok")
            except Exception as e:
                self.app.log("%s failed: %s" % (label, e), "error")
            finally:
                self.busy = False
        t = threading.Thread(target=_do)
        t.daemon = True
        t.start()

    def tool(self, name):
        jobs = {"stand": ("Stand up", lambda r: r.stand()),
                "rest": ("Sit down + rest", lambda r: r.rest()),
                "relax": ("Relax arms", lambda r: r.set_arms_stiff(False)),
                "stiffen": ("Stiffen arms", lambda r: r.set_arms_stiff(True))}
        if name not in jobs:
            raise ActionError("Unknown tool.")
        self._robot_job(*jobs[name])

    def preview(self, move, beat_s=1.4):
        if move not in MOVES:
            raise ActionError("Unknown move.")
        self._robot_job("Preview '%s'" % move, lambda r: r.go(move, float(beat_s)))

    def capture(self):
        if self.running or self.busy:
            raise ActionError("Robot busy.")
        line = format_captured_pose(self.robot().read_angles(), "new_move")
        self.app.log("Captured pose: %s" % line, "accent")
        return line

    # -- events / CSV ------------------------------------------------------
    def _open_csv(self, take_id, scenario, cfg, sim):
        import csv
        self._close_csv()
        try:
            if not os.path.isdir(STUDY_LOG_DIR):
                os.makedirs(STUDY_LOG_DIR)
            name = "%s_%s_%s%s.csv" % (time.strftime("%Y%m%d_%H%M%S"), take_id, scenario,
                                       "_SIM" if sim else "")
            path = os.path.join(STUDY_LOG_DIR, name)
            if sys.version_info[0] < 3:
                self._csv_file = open(path, "wb")
            else:
                self._csv_file = open(path, "w", newline="")
            self._csv = csv.writer(self._csv_file)
            self._csv.writerow(["wall_time", "t_take_s", "event", "detail"])
            self._csv.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), "0.000", "config",
                                "; ".join("%s=%s" % kv for kv in sorted(cfg.items()))])
            self.app.log("Study log: %s" % path)
        except Exception as e:
            self._csv_file = self._csv = None
            self.app.log("Could not open CSV log: %s" % e, "error")

    def _close_csv(self):
        if self._csv_file is not None:
            try:
                self._csv_file.close()
            except Exception:
                pass
        self._csv_file = self._csv = None

    def _on_event(self, t_rel, event, detail):
        wall = time.time()
        with self._lock:
            if self._csv is not None:
                ms = int((wall - int(wall)) * 1000)
                self._csv.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(wall))
                                    + ".%03d" % ms, "%.3f" % t_rel, event, detail])
                self._csv_file.flush()
            self._events.append({"id": next(self._ev_id), "t": round(t_rel, 2),
                                 "event": event, "detail": detail})
        scen = self.controller.scenario if self.controller else ""
        if event == "take_start":
            self.state, self.detail = "PREPARING", "Waking NAO and standing up..."
        elif event == "said":
            self.detail = u'NAO: "%s"' % detail
        elif event == "move":
            r, m, name = detail.split()
            self.position = (int(r[1:]), int(m[1:]))
            slow = self.controller is not None and self.controller.tempo > 1.0
            self.state = "SLOW" if slow else "DANCING"
            self.detail = "Round %d - move %d - %s" % (self.position[0], self.position[1], name.upper())
        elif event == "struggle_trigger":
            self.state, self.detail = "STRUGGLE", "Trigger fired (%s)" % detail
        elif event == "waiting_for_resume":
            if scen == "checkin":
                self.state, self.detail = "CHECK-IN", "Press Resume (R) after the participant answers."
            else:
                self.state, self.detail = "WAITING", "Press Resume (R) when the participant restarts."
        elif event == "resumed":
            self.state = "DANCING"
        elif event == "take_end":
            self.state = "DONE" if detail == "completed" else "STOPPED"
            self.detail = "Take %s." % detail
            with self._lock:
                self._close_csv()
            self.app.log("Study take ended: %s" % detail, "ok" if detail == "completed" else "warn")

    def snapshot(self, since=0):
        ctl = self.controller
        running = self.running
        with self._lock:
            events = [e for e in self._events if e["id"] > since]
        live_possible = self.app.connected and self.app.robot_type != "pepper"
        return {"running": running, "busy": self.busy, "sim": self.sim or not self.app.connected,
                "live_possible": live_possible,
                "waiting": bool(running and ctl.waiting),
                "triggered": bool(ctl is not None and ctl.triggered),
                "tempo": ctl.tempo if ctl is not None else 1.0,
                "state": self.state, "detail": self.detail,
                "position": self.position,
                "take": {k: v for k, v in (self.take or {}).items() if k != "config"} or None,
                "elapsed": (time.time() - self.take["started"]) if (self.take and running) else None,
                "events": events}


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------
APP = None
CAM_NAMES = {"operator": "_frame", "main": "_frame_pepper",
             "bottom": "_frame_pepper_bottom", "depth": "_frame_pepper_depth"}
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
                 ".png": "image/png", ".ico": "image/x-icon"}


def _b(s):
    return s if isinstance(s, bytes) else s.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "RobotControl/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype, extra=None):
        body = _b(body)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        u = urlparse.urlparse(self.path)
        q = urlparse.parse_qs(u.query)
        path = u.path
        try:
            if path == "/api/state":
                return self._json(APP.snapshot(int(q.get("log", ["0"])[0]),
                                               int(q.get("study", ["0"])[0])))
            if path == "/api/meta":
                return self._json(APP.meta())
            if path.startswith("/cam/"):
                return self._camera(path[5:].replace(".jpg", ""), q.get("last", [""])[0])
            return self._static(path)
        except Exception as e:
            traceback.print_exc()
            return self._json({"ok": False, "error": str(e)}, 500)

    def do_POST(self):
        path = urlparse.urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or "{}") if n else {}
        except ValueError:
            return self._json({"ok": False, "error": "bad JSON"}, 400)
        if path == "/api/drive":
            APP.set_drive(data.get("x", 0), data.get("y", 0), data.get("theta", 0))
            return self._json({"ok": True})
        if path == "/api/action":
            try:
                result = APP.dispatch(str(data.get("action", "")), data.get("args") or {})
                return self._json({"ok": True, "result": result})
            except ActionError as e:
                return self._json({"ok": False, "error": str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)})
        if path == "/api/shutdown":
            self._json({"ok": True})
            threading.Thread(target=SHUTDOWN).start()
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def _camera(self, name, last):
        attr = CAM_NAMES.get(name)
        if attr is None:
            return self._json({"ok": False}, 404)
        ms = APP.mjpeg_server
        with ms._lock:
            frame = getattr(ms, attr)
        if not frame:
            return self._send(204, b"", "image/jpeg")
        token = str(id(frame))
        if token == last:          # unchanged since the browser's last fetch
            return self._send(204, b"", "image/jpeg", {"X-Frame": token})
        self._send(200, frame, "image/jpeg", {"X-Frame": token})

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.normpath(os.path.join(WEB_DIR, path.lstrip("/")))
        if not full.startswith(WEB_DIR + os.sep) or not os.path.isfile(full):
            return self._send(404, "Not found", "text/plain")
        with open(full, "rb") as f:
            body = f.read()
        ext = os.path.splitext(full)[1].lower()
        self._send(200, body, CONTENT_TYPES.get(ext, "application/octet-stream"))


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


SHUTDOWN = None


def main():
    global APP, SHUTDOWN
    ap = argparse.ArgumentParser(description="Browser control panel for Pepper / NAO")
    ap.add_argument("--port", type=int, default=8000, help="web UI port (default 8000)")
    ap.add_argument("--lan", action="store_true",
                    help="listen on all interfaces (control from another device on the network)")
    ap.add_argument("--ip", default=None, help="robot IP to pre-fill")
    ap.add_argument("--robot-port", type=int, default=None)
    ap.add_argument("--connect", action="store_true", help="connect to the robot on start")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-tracker", action="store_true", help="do not auto-start the body tracker")
    ap.add_argument("--no-voice", action="store_true", help="disable 'ok pepper' voice commands")
    ap.add_argument("--tab", choices=("control", "study"), default="control")
    args = ap.parse_args()

    loop = MainLoop()
    APP = ControlApp(loop, autostart_tracker=not args.no_tracker, voice=not args.no_voice)
    if args.ip:
        APP.ip = args.ip
    if args.robot_port:
        APP.port = args.robot_port

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    try:
        server = ThreadedServer((host, args.port), Handler)
    except Exception as e:
        print("[web_app] Cannot listen on port %d (%s). Is the panel already open?" % (args.port, e))
        sys.exit(1)
    st = threading.Thread(target=server.serve_forever)
    st.daemon = True
    st.start()

    url = "http://127.0.0.1:%d/#%s" % (args.port, args.tab)
    print("=" * 60)
    print("  Control panel:  %s" % url)
    if args.lan:
        print("  On the LAN:     http://%s:%d/" % (APP.mjpeg_ip, args.port))
    print("  Close this window or press Ctrl+C to quit.")
    print("=" * 60)

    def _shutdown():
        APP.log("Shutting down...", "warn")
        try:
            loop.call_sync(APP.shutdown, timeout=10)
        except Exception:
            pass
        loop.stop()
    SHUTDOWN = _shutdown

    if args.connect:
        loop.call_soon(APP._safe_action, APP.connect)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        loop.run()
    except KeyboardInterrupt:
        try:
            APP.shutdown()
        except Exception:
            pass
    server.shutdown() if hasattr(server, "shutdown") else None
    os._exit(0)


if __name__ == "__main__":
    main()
