# -*- coding: utf-8 -*-
"""
nao_study_gui.py - NAO Dance Study operator panel (Wizard-of-Oz)
================================================================
Behind-the-scenes control for the Group 10 study: pick one of the four
struggle-response scenarios, start the take, fire the "participant struggles"
trigger (automatically at a fixed point, or by hand) and resume NAO when the
participant restarts / has answered.

Opens either
  * from pepper_gui.py ("Open NAO Study Panel", shares the connected session), or
  * standalone:  python nao_study_gui.py [--ip 192.168.1.61] [--port 9559] [--sim]

Hotkeys (when no text field has focus):
  Space = participant struggles (trigger)   R = resume   Esc = stop take

Every take is logged to study_logs/<date>_<take>_<scenario>.csv with
timestamps relative to take start, for syncing with the video recordings.
"""

from __future__ import print_function

try:
    import Tkinter as tk
except ImportError:
    import tkinter as tk
try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty
import argparse
import csv
import os
import sys
import threading
import time

try:
    import qi
except ImportError:
    qi = None

from utils.nao_dance import (
    DEFAULT_CONFIG, MOVES, ROUND, SCENARIOS,
    DanceController, NaoRobot, SimRobot, detect_robot_type, format_captured_pose,
)

# Same palette as pepper_gui.py
BG          = "#0d1117"
SURFACE     = "#161b22"
SURFACE_2   = "#21262d"
BORDER      = "#30363d"
ACCENT      = "#388bfd"
ACCENT_DARK = "#1f6feb"
SUCCESS     = "#3fb950"
WARNING     = "#d29922"
DANGER      = "#f85149"
TEXT_PRI    = "#e6edf3"
TEXT_SEC    = "#8b949e"

FONT_LABEL  = ("Segoe UI", 10)
FONT_SMALL  = ("Segoe UI", 9)
FONT_BOLD   = ("Segoe UI", 11, "bold")
FONT_H1     = ("Segoe UI", 14, "bold")
FONT_BIG    = ("Segoe UI", 20, "bold")
FONT_MONO   = ("Consolas", 9)
PAD         = 10

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "study_logs"))


def _card(parent, title):
    card = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
    tk.Label(card, text=title, font=FONT_BOLD, bg=SURFACE, fg=TEXT_PRI).pack(
        anchor="w", padx=PAD, pady=(PAD // 2, 2))
    tk.Frame(card, bg=BORDER, height=1).pack(fill=tk.X, padx=PAD)
    return card


def _button(parent, text, command, colour=SURFACE_2, active=BORDER, **kw):
    return tk.Button(parent, text=text, command=command, bg=colour, fg="white",
                     activebackground=active, activeforeground="white",
                     disabledforeground=TEXT_SEC, font=("Segoe UI", 11), relief=tk.FLAT,
                     cursor="hand2", padx=10, pady=5, **kw)


def _entry(parent, value, width=8):
    e = tk.Entry(parent, bg=SURFACE_2, fg=TEXT_PRI, insertbackground=TEXT_PRI,
                 relief=tk.FLAT, font=FONT_LABEL, width=width)
    e.insert(0, str(value))
    return e


def _check(parent, text, var):
    return tk.Checkbutton(parent, text=text, variable=var, font=FONT_LABEL,
                          bg=SURFACE, fg=TEXT_PRI, activebackground=SURFACE,
                          activeforeground=TEXT_PRI, selectcolor=SURFACE_2,
                          highlightthickness=0)


class NaoStudyPanel(object):
    def __init__(self, master, session=None, standalone=False, before_start=None,
                 default_ip="192.168.1.61", default_port=9559, force_sim=False):
        self.master = master
        self.session = session
        self.standalone = standalone
        self.before_start = before_start   # e.g. stop arm mirror in pepper_gui
        self._gui_thread = threading.current_thread()
        self.robot = None
        self._nao = None
        self.robot_type = None
        self.controller = None
        self._robot_busy = False
        self._q_events = Queue()
        self._csv_file = None
        self._csv = None
        self.closed = False

        self.sim_var = tk.IntVar(value=1 if (force_sim or qi is None) else 0)
        self.scenario_var = tk.StringVar(value=list(SCENARIOS.keys())[0])
        self.auto_var = tk.IntVar(value=1 if DEFAULT_CONFIG["auto_trigger"] else 0)
        self.callout_var = tk.IntVar(value=1 if DEFAULT_CONFIG["callouts"] else 0)
        self.restart_var = tk.IntVar(value=1 if DEFAULT_CONFIG["restart_round_on_resume"] else 0)
        self.preview_var = tk.StringVar(value="head")

        self._build(default_ip, default_port)
        if session is not None and not standalone:
            self._attach_session(session)
        self._refresh_robot()

        for seq in ("<space>", "<KeyPress-r>", "<KeyPress-R>", "<Escape>"):
            master.bind(seq, self._on_hotkey)
        master.protocol("WM_DELETE_WINDOW", self.close)
        master.after(100, self._poll)

    # ------------------------------------------------------------------ UI
    def _build(self, default_ip, default_port):
        m = self.master
        m.title("NAO Dance Study - Operator Panel")
        m.configure(bg=BG)
        m.geometry("1060x760")
        m.minsize(860, 600)

        header = tk.Frame(m, bg=SURFACE, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="NAO Dance Study - Operator Panel", font=FONT_H1,
                 bg=SURFACE, fg=TEXT_PRI).pack(side=tk.LEFT, padx=PAD * 2)
        self.lbl_robot = tk.Label(header, text="", font=FONT_BOLD, bg=SURFACE, fg=TEXT_SEC)
        self.lbl_robot.pack(side=tk.RIGHT, padx=PAD * 2)

        body = tk.Frame(m, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=PAD, pady=PAD)
        body.columnconfigure(0, weight=0, minsize=330)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, PAD))
        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")

        # -- Connection ----------------------------------------------------
        conn = _card(left, "Robot")
        conn.pack(fill=tk.X, pady=(0, PAD // 2))
        if self.standalone:
            row = tk.Frame(conn, bg=SURFACE)
            row.pack(fill=tk.X, padx=PAD, pady=(PAD // 2, 2))
            tk.Label(row, text="IP", font=FONT_LABEL, bg=SURFACE, fg=TEXT_SEC).pack(side=tk.LEFT)
            self.ent_ip = _entry(row, default_ip, 14)
            self.ent_ip.pack(side=tk.LEFT, padx=(4, 8), fill=tk.X, expand=True)
            tk.Label(row, text="Port", font=FONT_LABEL, bg=SURFACE, fg=TEXT_SEC).pack(side=tk.LEFT)
            self.ent_port = _entry(row, default_port, 6)
            self.ent_port.pack(side=tk.LEFT, padx=(4, 0))
            self.btn_connect = _button(conn, "Connect", self.connect, ACCENT, ACCENT_DARK)
            self.btn_connect.pack(fill=tk.X, padx=PAD, pady=2)
            if qi is None:
                self.btn_connect.configure(state=tk.DISABLED)
        sim = _check(conn, "Simulation - rehearse without the robot", self.sim_var)
        sim.configure(command=self._refresh_robot)
        sim.pack(anchor="w", padx=PAD - 2, pady=(2, PAD // 2))
        if qi is None:
            sim.configure(state=tk.DISABLED)

        # -- Take -------------------------------------------------------------
        take = _card(left, "Take")
        take.pack(fill=tk.X, pady=(0, PAD // 2))
        row = tk.Frame(take, bg=SURFACE)
        row.pack(fill=tk.X, padx=PAD, pady=(PAD // 2, 2))
        tk.Label(row, text="Participant / take ID", font=FONT_LABEL,
                 bg=SURFACE, fg=TEXT_SEC).pack(side=tk.LEFT)
        self.ent_take = _entry(row, "P01", 10)
        self.ent_take.pack(side=tk.RIGHT)

        for key, label in SCENARIOS.items():
            tk.Radiobutton(take, text=label, value=key, variable=self.scenario_var,
                           font=("Segoe UI", 11), bg=SURFACE, fg=TEXT_PRI,
                           activebackground=SURFACE, activeforeground=TEXT_PRI,
                           selectcolor=SURFACE_2, highlightthickness=0,
                           anchor="w").pack(fill=tk.X, padx=PAD - 2)

        row = tk.Frame(take, bg=SURFACE)
        row.pack(fill=tk.X, padx=PAD, pady=(PAD // 2, PAD // 2))
        row.columnconfigure((0, 1), weight=1)
        self.btn_start = _button(row, "Start take", self.start_take, ACCENT, ACCENT_DARK)
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self.btn_stop = _button(row, "Stop  [Esc]", self.stop_take, DANGER, "#b91c1c")
        self.btn_stop.grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # -- Live controls ------------------------------------------------------
        live = _card(left, "Live controls")
        live.pack(fill=tk.X, pady=(0, PAD // 2))
        self.btn_trigger = _button(live, "Participant struggles NOW  [Space]",
                                   self.trigger, WARNING, "#9e6a03")
        self.btn_trigger.pack(fill=tk.X, padx=PAD, pady=(PAD // 2, 2))
        self.btn_resume = _button(live, "Resume - participant restarted  [R]",
                                  self.resume, SUCCESS, "#238636")
        self.btn_resume.pack(fill=tk.X, padx=PAD, pady=(0, PAD // 2))

        # -- Robot tools ---------------------------------------------------------
        tools = _card(left, "Robot tools (between takes)")
        tools.pack(fill=tk.X, pady=(0, PAD // 2))
        grid = tk.Frame(tools, bg=SURFACE)
        grid.pack(fill=tk.X, padx=PAD, pady=PAD // 2)
        grid.columnconfigure((0, 1), weight=1)
        self.tool_buttons = []
        for i, (text, fn) in enumerate((
                ("Stand up", lambda r: r.stand()),
                ("Sit down + rest", lambda r: r.rest()),
                ("Relax arms (pose by hand)", lambda r: r.set_arms_stiff(False)),
                ("Stiffen arms", lambda r: r.set_arms_stiff(True)),
        )):
            b = _button(grid, text, lambda f=fn, t=text: self._robot_action(t, f))
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=1, pady=1)
            self.tool_buttons.append(b)
        b = _button(grid, "Capture pose", self.capture_pose)
        b.grid(row=2, column=0, sticky="ew", padx=1, pady=1)
        self.tool_buttons.append(b)
        prev = tk.Frame(grid, bg=SURFACE)
        prev.grid(row=2, column=1, sticky="ew", padx=1, pady=1)
        om = tk.OptionMenu(prev, self.preview_var, *MOVES.keys())
        om.configure(bg=SURFACE_2, fg=TEXT_PRI, activebackground=BORDER, relief=tk.FLAT,
                     highlightthickness=0, font=FONT_LABEL, width=8)
        om.pack(side=tk.LEFT, fill=tk.X, expand=True)
        b = _button(prev, "Go", self.preview_move)
        b.pack(side=tk.LEFT)
        self.tool_buttons.append(b)

        # -- Status (right) ----------------------------------------------------
        status = _card(right, "Status")
        status.pack(fill=tk.X, pady=(0, PAD // 2))
        self.lbl_state = tk.Label(status, text="IDLE", font=FONT_BIG, bg=SURFACE, fg=TEXT_SEC,
                                  anchor="w")
        self.lbl_state.pack(fill=tk.X, padx=PAD, pady=(PAD // 2, 0))
        self.lbl_detail = tk.Label(status, text="Choose a scenario and press Start take.",
                                   font=("Segoe UI", 12), bg=SURFACE, fg=TEXT_PRI, anchor="w",
                                   justify=tk.LEFT, wraplength=620)
        self.lbl_detail.pack(fill=tk.X, padx=PAD, pady=(0, PAD // 2))

        # -- Settings ------------------------------------------------------------
        st = _card(right, "Take settings (applied when a take starts)")
        st.pack(fill=tk.X, pady=(0, PAD // 2))
        g = tk.Frame(st, bg=SURFACE)
        g.pack(fill=tk.X, padx=PAD, pady=PAD // 2)
        c = DEFAULT_CONFIG

        def lbl(text, r, col):
            tk.Label(g, text=text, font=FONT_LABEL, bg=SURFACE, fg=TEXT_SEC, anchor="w").grid(
                row=r, column=col, sticky="w", padx=(0 if col == 0 else 12, 4), pady=2)

        lbl("Rounds", 0, 0)
        self.ent_rounds = _entry(g, c["rounds"], 5)
        self.ent_rounds.grid(row=0, column=1, sticky="w")
        lbl("Seconds per move", 0, 2)
        self.ent_beat = _entry(g, c["beat_s"], 5)
        self.ent_beat.grid(row=0, column=3, sticky="w")
        lbl("Slow-down factor (B)", 0, 4)
        self.ent_slow = _entry(g, c["slow_factor"], 5)
        self.ent_slow.grid(row=0, column=5, sticky="w")

        _check(g, "Auto trigger at round", self.auto_var).grid(row=1, column=0, columnspan=2,
                                                                sticky="w", pady=2)
        self.ent_trig_round = _entry(g, c["trigger_round"], 5)
        self.ent_trig_round.grid(row=1, column=2, sticky="w", padx=(12, 0))
        lbl("move #", 1, 3)
        self.ent_trig_move = _entry(g, c["trigger_move"], 5)
        self.ent_trig_move.grid(row=1, column=4, sticky="w", padx=(12, 0))
        tk.Label(g, text="Round: " + ", ".join("%d %s" % (i + 1, mv) for i, mv in enumerate(ROUND)),
                 font=FONT_SMALL, bg=SURFACE, fg=TEXT_SEC, anchor="w").grid(
            row=2, column=0, columnspan=6, sticky="w")

        _check(g, "NAO calls out each move", self.callout_var).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=2)
        _check(g, "Restart the round after resume (C, D)", self.restart_var).grid(
            row=3, column=3, columnspan=3, sticky="w", pady=2)

        self.text_entries = {}
        for r, (key, label) in enumerate((
                ("intro_text", "Intro (all)"),
                ("checkin_text", "Check-in question (D)"),
                ("resume_text_checkin", "Said on resume (D)"),
                ("resume_text_wait", "Said on resume (C)"),
                ("outro_text", "Outro (all)"),
        ), start=4):
            lbl(label, r, 0)
            e = _entry(g, c[key], 50)
            e.grid(row=r, column=1, columnspan=5, sticky="ew", pady=1)
            self.text_entries[key] = e
        g.columnconfigure(5, weight=1)

        # -- Log ---------------------------------------------------------------
        logc = _card(right, "Event log")
        logc.pack(fill=tk.BOTH, expand=True)
        frame = tk.Frame(logc, bg=SURFACE)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.txt_log = tk.Text(frame, bg=SURFACE, fg=TEXT_SEC, font=FONT_MONO, relief=tk.FLAT,
                               state=tk.DISABLED, wrap=tk.WORD, bd=0, height=10)
        sb = tk.Scrollbar(frame, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------- logging
    def log(self, msg, colour=None):
        """Thread-safe: worker threads queue messages, the GUI thread prints them."""
        if threading.current_thread() is not self._gui_thread:
            self._q_events.put(("log", msg, colour))
            return
        self._log_now(msg, colour)

    def _log_now(self, msg, colour=None):
        line = "[%s] %s\n" % (time.strftime("%H:%M:%S"), msg)
        self.txt_log.configure(state=tk.NORMAL)
        if colour:
            tag = "c" + colour.replace("#", "")
            self.txt_log.tag_configure(tag, foreground=colour)
            self.txt_log.insert(tk.END, line, tag)
        else:
            self.txt_log.insert(tk.END, line)
        self.txt_log.configure(state=tk.DISABLED)
        self.txt_log.see(tk.END)

    # ------------------------------------------------------------- robot
    def connect(self):
        try:
            ip = self.ent_ip.get().strip()
            port = int(self.ent_port.get().strip())
        except ValueError:
            self._log_now("Invalid port.", DANGER)
            return
        self.session = qi.Session()
        try:
            self.session.connect("tcp://%s:%d" % (ip, port))
        except RuntimeError as e:
            self.session = None
            self._log_now("Connection to %s:%d failed: %s" % (ip, port, e), DANGER)
            return
        self.btn_connect.configure(text="Connected", state=tk.DISABLED, bg=SUCCESS)
        self._log_now("Connected to %s:%d" % (ip, port), SUCCESS)
        self._attach_session(self.session)
        self.sim_var.set(0)
        self._refresh_robot()

    def _attach_session(self, session):
        self.robot_type = detect_robot_type(session)
        if self.robot_type == "pepper":
            self._log_now("Connected robot looks like Pepper - this panel's choreography "
                          "is written for NAO (legs). Use Simulation instead.", WARNING)
        elif self.robot_type == "nao":
            self._log_now("NAO detected.", SUCCESS)
        try:
            self._nao = NaoRobot(session, log=self.log)
        except Exception as e:
            self._nao = None
            self._log_now("NAOqi services unavailable: %s" % e, DANGER)

    def _refresh_robot(self):
        if self.controller is not None and self.controller.is_alive():
            return
        nao = self._nao
        if self.sim_var.get() or nao is None:
            self.robot = SimRobot(log=self.log)
            self.lbl_robot.configure(text="* SIMULATION", fg=WARNING)
        else:
            self.robot = nao
            self.lbl_robot.configure(text="* %s CONNECTED" % (self.robot_type or "robot").upper(),
                                     fg=SUCCESS)

    def _robot_action(self, label, fn):
        if self._robot_busy or (self.controller is not None and self.controller.is_alive()):
            self._log_now("Robot busy - wait for the current action / take to finish.", WARNING)
            return
        robot = self.robot
        self._robot_busy = True
        self._log_now("%s..." % label)

        def _do():
            try:
                fn(robot)
                self.log("%s: done." % label, SUCCESS)
            except Exception as e:
                self.log("%s ERROR: %s" % (label, e), DANGER)
            finally:
                self._robot_busy = False
        t = threading.Thread(target=_do)
        t.daemon = True
        t.start()

    def preview_move(self):
        move = self.preview_var.get()
        beat = self._float(self.ent_beat, DEFAULT_CONFIG["beat_s"])
        self._robot_action("Preview '%s'" % move, lambda r: r.go(move, beat))

    def capture_pose(self):
        if self._robot_busy:
            return
        try:
            line = format_captured_pose(self.robot.read_angles(), "new_move")
        except Exception as e:
            self._log_now("Capture failed: %s" % e, DANGER)
            return
        self._log_now("Captured pose (copied to clipboard - paste into MOVES in utils/nao_dance.py):",
                      ACCENT)
        self._log_now("    " + line, TEXT_PRI)
        self.master.clipboard_clear()
        self.master.clipboard_append(line)

    # ------------------------------------------------------------- take
    @staticmethod
    def _float(entry, default):
        try:
            return float(entry.get().strip())
        except ValueError:
            return default

    @staticmethod
    def _int(entry, default):
        try:
            return int(entry.get().strip())
        except ValueError:
            return default

    def _collect_config(self):
        c = DEFAULT_CONFIG
        cfg = dict(
            rounds=max(1, self._int(self.ent_rounds, c["rounds"])),
            beat_s=max(0.6, self._float(self.ent_beat, c["beat_s"])),
            slow_factor=max(1.0, self._float(self.ent_slow, c["slow_factor"])),
            auto_trigger=bool(self.auto_var.get()),
            trigger_round=self._int(self.ent_trig_round, c["trigger_round"]),
            trigger_move=self._int(self.ent_trig_move, c["trigger_move"]),
            callouts=bool(self.callout_var.get()),
            restart_round_on_resume=bool(self.restart_var.get()),
        )
        for key, e in self.text_entries.items():
            cfg[key] = e.get().strip()
        return cfg

    def start_take(self):
        if self.controller is not None and self.controller.is_alive():
            self._log_now("A take is already running.", WARNING)
            return
        if self._robot_busy:
            self._log_now("Robot busy - wait for the current action to finish.", WARNING)
            return
        self._refresh_robot()
        if not self.robot.is_sim and self.robot_type == "pepper":
            self._log_now("Refusing to run the NAO choreography on Pepper.", DANGER)
            return
        if self.before_start is not None:
            try:
                self.before_start()
            except Exception as e:
                self._log_now("before_start hook: %s" % e, WARNING)

        scenario = self.scenario_var.get()
        cfg = self._collect_config()
        take_id = "".join(ch for ch in self.ent_take.get().strip() if ch.isalnum() or ch in "-_") or "take"
        self._open_csv(take_id, scenario, cfg)

        self.controller = DanceController(self.robot, scenario, cfg, self._on_event)
        self._log_now("=" * 60)
        self._log_now("Take %s - %s%s" % (take_id, SCENARIOS[scenario],
                                          "  [SIMULATION]" if self.robot.is_sim else ""), ACCENT)
        if cfg["auto_trigger"]:
            self._log_now("Auto trigger: round %d, move %d" % (cfg["trigger_round"], cfg["trigger_move"]))
        self.controller.start()

    def stop_take(self):
        ctl = self.controller
        if ctl is not None and ctl.is_alive():
            ctl.stop()
            robot = self.robot
            threading.Thread(target=robot.stop_motion).start()
            self._log_now("STOP pressed - NAO holds its pose. Use Stand up / Sit down if needed.", DANGER)

    def trigger(self):
        ctl = self.controller
        if ctl is not None and ctl.is_alive() and not ctl.triggered:
            ctl.trigger_struggle("operator")
            self._log_now("Struggle trigger queued - NAO reacts at the next move boundary.", WARNING)

    def resume(self):
        ctl = self.controller
        if ctl is not None and ctl.is_alive() and ctl.waiting:
            ctl.resume()

    def _on_hotkey(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Spinbox)):
            return
        k = event.keysym.lower()
        if k == "space":
            self.trigger()
        elif k == "r":
            self.resume()
        elif k == "escape":
            self.stop_take()
        return "break"

    # ------------------------------------------------------------- events
    def _on_event(self, t_rel, event, detail):
        """Called from the DanceController thread."""
        self._q_events.put(("event", t_rel, event, detail, time.time()))

    def _open_csv(self, take_id, scenario, cfg):
        self._close_csv()
        try:
            if not os.path.isdir(LOG_DIR):
                os.makedirs(LOG_DIR)
            name = "%s_%s_%s%s.csv" % (time.strftime("%Y%m%d_%H%M%S"), take_id, scenario,
                                       "_SIM" if self.robot.is_sim else "")
            path = os.path.join(LOG_DIR, name)
            if sys.version_info[0] < 3:
                self._csv_file = open(path, "wb")
            else:
                self._csv_file = open(path, "w", newline="")
            self._csv = csv.writer(self._csv_file)
            self._csv.writerow(["wall_time", "t_take_s", "event", "detail"])
            self._csv.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), "0.000", "config",
                                "; ".join("%s=%s" % kv for kv in sorted(cfg.items()))])
            self._log_now("Logging to %s" % path)
        except Exception as e:
            self._csv_file = self._csv = None
            self._log_now("Could not open CSV log: %s" % e, DANGER)

    def _close_csv(self):
        if self._csv_file is not None:
            try:
                self._csv_file.close()
            except Exception:
                pass
        self._csv_file = self._csv = None

    def _handle_event(self, t_rel, event, detail, wall):
        if self._csv is not None:
            ms = int((wall - int(wall)) * 1000)
            self._csv.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(wall)) + ".%03d" % ms,
                                "%.3f" % t_rel, event, detail])
            self._csv_file.flush()

        colour = {"struggle_trigger": WARNING, "intervention": WARNING, "waiting_for_resume": ACCENT,
                  "resumed": SUCCESS, "take_end": SUCCESS, "error": DANGER}.get(event)
        self._log_now("t=%6.2fs  %-18s %s" % (t_rel, event, detail), colour)

        scen = self.controller.scenario if self.controller else ""
        if event == "take_start":
            self._set_state("PREPARING", TEXT_PRI, "Waking NAO and standing up...")
        elif event == "said":
            self.lbl_detail.configure(text='NAO: "%s"' % detail)
        elif event == "move":
            parts = detail.split()
            mode = "SLOW" if (self.controller and self.controller.tempo > 1.0) else "DANCING"
            self._set_state(mode, SUCCESS if mode == "DANCING" else WARNING,
                            "Round %s  -  move %s  -  %s" % (parts[0][1:], parts[1][1:], parts[2].upper()))
        elif event == "struggle_trigger":
            self._set_state("STRUGGLE", WARNING, "Trigger fired (%s)" % detail)
        elif event == "waiting_for_resume":
            if scen == "checkin":
                self._set_state("CHECK-IN", ACCENT,
                                "NAO asked how they are doing. Press RESUME [R] after the participant answers.")
            else:
                self._set_state("WAITING", ACCENT,
                                "NAO is waiting. Press RESUME [R] when the participant restarts.")
        elif event == "take_end":
            self._set_state("DONE" if detail == "completed" else "STOPPED",
                            SUCCESS if detail == "completed" else DANGER, "Take %s." % detail)
            self._close_csv()

    def _set_state(self, state, colour, detail):
        self.lbl_state.configure(text=state, fg=colour)
        self.lbl_detail.configure(text=detail)

    def _poll(self):
        if self.closed:
            return
        while True:
            try:
                item = self._q_events.get_nowait()
            except Empty:
                break
            if item[0] == "log":
                self._log_now(item[1], item[2])
            else:
                self._handle_event(*item[1:])

        running = self.controller is not None and self.controller.is_alive()
        waiting = running and self.controller.waiting
        self.btn_start.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.btn_stop.configure(state=tk.NORMAL if running else tk.DISABLED)
        self.btn_trigger.configure(
            state=tk.NORMAL if (running and not self.controller.triggered) else tk.DISABLED)
        self.btn_resume.configure(state=tk.NORMAL if waiting else tk.DISABLED)
        tool_state = tk.DISABLED if running else tk.NORMAL
        for b in self.tool_buttons:
            b.configure(state=tool_state)
        self.master.after(100, self._poll)

    def close(self):
        if self.controller is not None and self.controller.is_alive():
            self.stop_take()
        self.closed = True
        self._close_csv()
        self.master.destroy()


def main():
    ap = argparse.ArgumentParser(description="NAO dance study operator panel")
    ap.add_argument("--ip", default="192.168.1.61")
    ap.add_argument("--port", type=int, default=9559)
    ap.add_argument("--sim", action="store_true", help="start in simulation mode")
    args = ap.parse_args()

    root = tk.Tk()
    NaoStudyPanel(root, standalone=True, default_ip=args.ip, default_port=args.port,
                  force_sim=args.sim)
    root.mainloop()


if __name__ == "__main__":
    main()
