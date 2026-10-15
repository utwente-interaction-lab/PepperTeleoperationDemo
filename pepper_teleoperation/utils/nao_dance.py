# -*- coding: utf-8 -*-
"""
nao_dance.py - NAO dance-study engine (Group 10, Human-Robot Collaboration)
===========================================================================
A simple "head / shoulders / knees / toes" follow-me exercise for NAO, plus
the four scripted responses to a participant who visibly struggles:

    A  continue   - NAO keeps going exactly as before
    B  slow       - NAO keeps going but at a slower tempo
    C  wait       - NAO stops, faces the participant and waits until the
                    participant restarts (operator presses Resume)
    D  checkin    - NAO stops, faces the participant and asks how they are
                    doing, then waits for the operator to press Resume

Every take is identical up to the struggle trigger, so the intervention is the
only thing that differs between the four videos. With "auto trigger" on, the
trigger fires at a fixed round/move for perfectly repeatable takes; the operator
can also fire it by hand (Wizard-of-Oz).

Works with a real NAO (NAOqi via `qi`) or a SimRobot that only logs, so the
scenarios can be rehearsed without a robot.

Python 2.7 compatible (runs inside the pepper27_32 env alongside pepper_gui.py).
"""

from __future__ import print_function

import threading
import time
from collections import OrderedDict


# ---------------------------------------------------------------------------
# Robot detection
# ---------------------------------------------------------------------------
def detect_robot_type(session):
    """Return "nao", "pepper" or "unknown" for a connected qi session.

    Pepper has a HipPitch joint and wheels; NAO has legs (KneePitch).
    """
    try:
        names = session.service("ALMotion").getBodyNames("Body")
    except Exception:
        return "unknown"
    if "LKneePitch" in names:
        return "nao"
    if "HipPitch" in names or "WheelFL" in names:
        return "pepper"
    return "unknown"


# ---------------------------------------------------------------------------
# Choreography
# ---------------------------------------------------------------------------
# A pose = head pitch + LEFT arm + legs. The right arm is mirrored and both
# legs get the same values, so every pose is symmetric (important for NAO's
# balance when squatting).
#
#   arm  = [ShoulderPitch, ShoulderRoll, ElbowYaw, ElbowRoll, WristYaw, Hand]
#   legs = [HipPitch, KneePitch, AnklePitch]
#
# HeadPitch: negative = look up, positive = look down.
# Legs keep HipPitch + KneePitch + AnklePitch ~= -0.1 so the torso stays at the
# same slight forward tilt as StandInit while squatting.
#
# NAO's arms are too short to really touch its head or toes - these poses
# *indicate* each body part. They are first-draft values: check them in
# Choregraphe's virtual robot / on the real NAO and refine them with the
# "Relax arms" + "Capture pose" tools in the study panel.
ARM_KEYS = ("ShoulderPitch", "ShoulderRoll", "ElbowYaw", "ElbowRoll", "WristYaw", "Hand")
LEG_KEYS = ("HipPitch", "KneePitch", "AnklePitch")

STAND_LEGS = [-0.45, 0.70, -0.35]                 # NAO StandInit
NEUTRAL_ARM = [1.40, 0.30, -1.39, -1.00, 0.0, 0.25]

MOVES = OrderedDict([
    ("neutral",   dict(head=0.0,   arm=NEUTRAL_ARM,                          legs=STAND_LEGS)),
    # Looking at the participant (who is taller than NAO). Used by Stop & Wait
    # and Stop & Check-in so they differ only in what NAO says.
    ("attend",    dict(head=-0.18, arm=NEUTRAL_ARM,                          legs=STAND_LEGS)),
    ("head",      dict(head=-0.15, arm=[-0.95, 0.70,  0.00, -1.45, 0.0, 0.8], legs=STAND_LEGS,
                       say="Head")),
    ("shoulders", dict(head=0.0,   arm=[0.20,  1.10, -1.20, -1.45, 0.0, 0.8], legs=STAND_LEGS,
                       say="Shoulders")),
    ("knees",     dict(head=0.30,  arm=[1.05,  0.15, -1.00, -0.35, 0.0, 1.0], legs=[-0.75, 1.30, -0.65],
                       say="Knees")),
    ("toes",      dict(head=0.45,  arm=[1.25,  0.10, -0.50, -0.10, 0.0, 1.0], legs=[-0.95, 1.70, -0.85],
                       say="Toes")),
])

# One round of the exercise. Edit freely - any key of MOVES works.
ROUND = ["head", "shoulders", "knees", "toes", "knees", "toes"]

# NAO's speech language. Lab robots are often set to Dutch, which mangles the
# English lines, so every connection / take switches TTS to this language.
ROBOT_LANGUAGE = "English"


def set_tts_language(session, language=ROBOT_LANGUAGE, log=print):
    """Switch ALTextToSpeech to `language` if installed. Returns True on success."""
    try:
        tts = session.service("ALTextToSpeech")
        if tts.getLanguage() == language:
            return True
        available = tts.getAvailableLanguages()
        if language not in available:
            log("[NAO] TTS language '%s' not installed (have: %s)" % (language, ", ".join(available)))
            return False
        tts.setLanguage(language)
        log("[NAO] Speech language set to %s." % language)
        return True
    except Exception as e:
        log("[NAO] Could not set speech language: %s" % e)
        return False


def pose_targets(move):
    """Expand a MOVES entry to (joint_names, angles) for both sides."""
    m = MOVES[move]
    names = ["HeadYaw", "HeadPitch"]
    angles = [0.0, m["head"]]
    for side, sign in (("L", 1.0), ("R", -1.0)):
        sp, sr, ey, er, wy, hand = m["arm"]
        names += [side + k for k in ARM_KEYS]
        angles += [sp, sign * sr, sign * ey, sign * er, sign * wy, hand]
        names += [side + k for k in LEG_KEYS]
        angles += list(m["legs"])
    return names, [float(a) for a in angles]


def all_pose_joint_names():
    return pose_targets("neutral")[0]


def format_captured_pose(name_to_angle, move_name="new_move"):
    """Turn measured joint angles into a MOVES line (left arm + averaged legs)."""
    a = name_to_angle
    arm = [a["L" + k] for k in ARM_KEYS]
    legs = [(a["L" + k] + a["R" + k]) / 2.0 for k in LEG_KEYS]

    def fmt(vals):
        return "[" + ", ".join("%.2f" % v for v in vals) + "]"
    return '("%s", dict(head=%.2f, arm=%s, legs=%s)),' % (
        move_name, a["HeadPitch"], fmt(arm), fmt(legs))


# ---------------------------------------------------------------------------
# Scenarios + settings
# ---------------------------------------------------------------------------
SCENARIOS = OrderedDict([
    ("continue", "A - Continue unchanged"),
    ("slow",     "B - Continue, but slower"),
    ("wait",     "C - Stop & wait for human restart"),
    ("checkin",  "D - Stop & ask how they are doing"),
])

DEFAULT_CONFIG = dict(
    rounds=4,
    beat_s=1.4,           # seconds per move at normal tempo
    move_fraction=0.75,   # share of each beat spent moving (rest = hold)
    slow_factor=1.6,      # scenario B: beats become this many times longer
    auto_trigger=True,    # fire the struggle trigger at a fixed point
    trigger_round=3,      # 1-based
    trigger_move=3,       # 1-based index into ROUND (3 = first "knees")
    callouts=True,        # NAO says each body part as it moves
    intro_text="Let's do an exercise together. Follow my moves!",
    outro_text="Well done, that's the end of the exercise.",
    checkin_text="Are you okay? How are you doing?",
    resume_text_checkin="Okay, let's continue together!",
    resume_text_wait="",
    restart_round_on_resume=True,
)


# ---------------------------------------------------------------------------
# Robot back-ends
# ---------------------------------------------------------------------------
def _safe(fn, label="", log=None):
    try:
        return fn()
    except Exception as e:
        if label:
            msg = "[NAO] %s: %s" % (label, e)
            (log or print)(msg)
        return None


class SimRobot(object):
    """No robot: logs what NAO would do, with real timing, for rehearsals."""
    is_sim = True

    def __init__(self, log=print):
        self.log = log

    def prepare(self):
        self.log("[SIM] wakeUp + StandInit")

    def go(self, move, duration):
        time.sleep(duration)

    def say(self, text, block=False):
        if not text:
            return
        self.log('[SIM] NAO says: "%s"' % text)
        if block:
            time.sleep(0.25 + 0.07 * len(text))

    def stop_motion(self):
        self.log("[SIM] motion tasks killed")

    def stand(self):
        self.log("[SIM] StandInit")

    def rest(self):
        self.log("[SIM] Crouch + rest")

    def set_arms_stiff(self, stiff):
        self.log("[SIM] arms %s" % ("stiff" if stiff else "relaxed"))

    def read_angles(self):
        names, angles = pose_targets("neutral")
        return dict(zip(names, angles))


class NaoRobot(object):
    """Thin wrapper around the NAOqi services the dance needs."""
    is_sim = False

    def __init__(self, session, log=print):
        self.log = log
        self.session = session
        self.motion = session.service("ALMotion")
        self.posture = session.service("ALRobotPosture")
        self.tts = _safe(lambda: session.service("ALTextToSpeech"), "ALTextToSpeech", log)

    def prepare(self):
        """Quiet autonomous behaviours that would fight the choreography, then stand."""
        life = _safe(lambda: self.session.service("ALAutonomousLife"))
        if life is not None:
            if _safe(life.getState) == "disabled":
                _safe(lambda: life.setState("solitary"), "AutonomousLife solitary", self.log)
            for ability in ("BasicAwareness", "BackgroundMovement",
                            "ListeningMovement", "SpeakingMovement"):
                _safe(lambda: life.setAutonomousAbilityEnabled(ability, False))
        _safe(lambda: self.motion.setBreathEnabled("Body", False))
        set_tts_language(self.session, ROBOT_LANGUAGE, self.log)
        self.motion.wakeUp()
        self.posture.goToPosture("StandInit", 0.5)

    def go(self, move, duration):
        """Blocking timed move to a MOVES pose."""
        names, angles = pose_targets(move)
        times = [max(0.2, float(duration))] * len(names)
        self.motion.angleInterpolation(names, angles, times, True)

    def say(self, text, block=False):
        if not text or self.tts is None:
            return
        if block:
            _safe(lambda: self.tts.say(str(text)), "say", self.log)
            return
        try:
            self.tts.say(str(text), _async=True)
        except Exception:
            t = threading.Thread(target=lambda: _safe(lambda: self.tts.say(str(text))))
            t.daemon = True
            t.start()

    def stop_motion(self):
        _safe(self.motion.killAll, "killAll", self.log)
        if self.tts is not None:
            _safe(self.tts.stopAll)

    def stand(self):
        self.motion.wakeUp()
        self.posture.goToPosture("StandInit", 0.5)

    def rest(self):
        """Sit down safely (Crouch) and switch motors off."""
        _safe(lambda: self.posture.goToPosture("Crouch", 0.5), "Crouch", self.log)
        self.motion.rest()

    def set_arms_stiff(self, stiff):
        self.motion.setStiffnesses(["LArm", "RArm", "Head"], 1.0 if stiff else 0.0)

    def read_angles(self):
        names = all_pose_joint_names()
        return dict(zip(names, self.motion.getAngles(names, True)))


# ---------------------------------------------------------------------------
# Dance controller
# ---------------------------------------------------------------------------
class DanceStopped(Exception):
    pass


class DanceController(threading.Thread):
    """Runs one take: intro -> rounds -> (struggle -> intervention) -> outro.

    on_event(t_rel, event, detail) is called from this thread for every
    meaningful moment; the GUI logs these to screen + CSV.
    """

    def __init__(self, robot, scenario, cfg, on_event):
        threading.Thread.__init__(self)
        self.daemon = True
        if scenario not in SCENARIOS:
            raise ValueError("Unknown scenario %r" % scenario)
        self.robot = robot
        self.scenario = scenario
        self.cfg = dict(DEFAULT_CONFIG)
        self.cfg.update(cfg or {})
        self.on_event = on_event

        self._stop_evt = threading.Event()
        self._resume = threading.Event()
        self._trigger_requested = threading.Event()
        self.triggered = False
        self.waiting = False
        self.tempo = 1.0
        self._t0 = None

    # -- operator commands (any thread) ---------------------------------
    def trigger_struggle(self, source="operator"):
        if not self.triggered:
            self._trigger_source = source
            self._trigger_requested.set()

    def resume(self):
        self._resume.set()

    def stop(self):
        self._stop_evt.set()
        self._resume.set()

    # -- helpers ----------------------------------------------------------
    def _emit(self, event, detail=""):
        t = time.time() - self._t0 if self._t0 else 0.0
        try:
            self.on_event(t, event, detail)
        except Exception as e:
            print("[NAO] on_event error: %s" % e)

    def _check(self):
        if self._stop_evt.is_set():
            raise DanceStopped()

    def _beat(self, move):
        beat = float(self.cfg["beat_s"]) * self.tempo
        move_t = beat * float(self.cfg["move_fraction"])
        t_start = time.time()
        self.robot.go(move, move_t)
        rest = beat - (time.time() - t_start)
        if rest > 0:
            self._stop_evt.wait(rest)
        self._check()

    def _wait_for_resume(self):
        self.waiting = True
        self._resume.clear()
        self._emit("waiting_for_resume")
        while not self._resume.wait(0.1):
            pass
        self.waiting = False
        self._check()
        self._emit("resumed", "operator")

    def _intervene(self):
        """Run the scenario's response. Returns True to restart the current round."""
        self.triggered = True
        self._emit("struggle_trigger", getattr(self, "_trigger_source", "operator"))
        cfg = self.cfg
        if self.scenario == "continue":
            self._emit("intervention", "none - continuing unchanged")
            return False
        if self.scenario == "slow":
            self.tempo = float(cfg["slow_factor"])
            self._emit("intervention", "slow down (beat %.2fs)" % (cfg["beat_s"] * self.tempo))
            return False

        self._emit("intervention", "stop" if self.scenario == "wait" else "stop + check-in")
        self.robot.go("attend", 1.0)
        self._check()
        if self.scenario == "checkin":
            self.robot.say(cfg["checkin_text"], block=True)
            self._emit("said", cfg["checkin_text"])
            self._check()
        self._wait_for_resume()
        resume_text = cfg["resume_text_checkin"] if self.scenario == "checkin" else cfg["resume_text_wait"]
        if resume_text:
            self.robot.say(resume_text, block=True)
            self._emit("said", resume_text)
            self._check()
        return bool(cfg["restart_round_on_resume"])

    # -- main -------------------------------------------------------------
    def run(self):
        cfg = self.cfg
        self._t0 = time.time()
        self._emit("take_start", SCENARIOS[self.scenario])
        try:
            self.robot.prepare()
            self._check()
            self.robot.go("neutral", 1.0)
            self._check()
            if cfg["intro_text"]:
                self.robot.say(cfg["intro_text"], block=True)
                self._emit("said", cfg["intro_text"])
            self._check()

            rounds = int(cfg["rounds"])
            r = 1
            while r <= rounds:
                self._emit("round_start", "%d/%d" % (r, rounds))
                i = 0
                restart = False
                while i < len(ROUND):
                    self._check()
                    if (cfg["auto_trigger"] and not self.triggered
                            and r == int(cfg["trigger_round"])
                            and i + 1 == int(cfg["trigger_move"])):
                        self.trigger_struggle("auto")
                    if self._trigger_requested.is_set() and not self.triggered:
                        if self._intervene():
                            restart = True
                            break
                    move = ROUND[i]
                    self._emit("move", "r%d m%d %s" % (r, i + 1, move))
                    if cfg["callouts"]:
                        self.robot.say(MOVES[move].get("say", ""))
                    self._beat(move)
                    i += 1
                if restart:
                    self._emit("round_restart", "%d/%d" % (r, rounds))
                    continue
                r += 1

            self.robot.go("neutral", 1.2)
            if cfg["outro_text"]:
                self.robot.say(cfg["outro_text"], block=True)
                self._emit("said", cfg["outro_text"])
            self._emit("take_end", "completed")
        except DanceStopped:
            self._emit("take_end", "stopped by operator")
        except Exception as e:
            if self._stop_evt.is_set():   # killAll interrupted a move
                self._emit("take_end", "stopped by operator")
                return
            self._emit("error", str(e))
            self._emit("take_end", "error")
