# -*- coding: utf-8 -*-
"""
One-shot Pepper demos: three levels of "asking for an object".

1. Limited  - upright forward point (closed hand / finger tip); no blink / LEDs / tablet
2. OK       - clearly looks down at the table and reaches the open palm toward it
3. Ideal    - bends forward, reaches over, grab motion, eye blinks, head hint,
              tablet + spoken "Please place the object in my hand"
"""

from __future__ import print_function

import time


_STIFF_JOINTS = [
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
    "HeadYaw", "HeadPitch", "HipPitch",
]

# Shared name list for full upper-body poses (order matches angle lists below).
_POSE_NAMES = [
    "HeadYaw", "HeadPitch", "HipPitch",
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll",
]

TABLET_MSG = "Please place the object in my hand"


def _safe(svc_call, label=""):
    try:
        return svc_call()
    except Exception as e:
        if label:
            print("[AskGesture] %s: %s" % (label, e))
        return None


def _prepare(session):
    """Wake motors, solitary life, stiffness on, disable awareness fighting us."""
    motion = session.service("ALMotion")
    _safe(lambda: session.service("ALAutonomousLife").setState("solitary"),
          "AutonomousLife")
    try:
        life = session.service("ALAutonomousLife")
        _safe(lambda: life.setAutonomousAbilityEnabled("BasicAwareness", False),
              "BasicAwareness off")
        _safe(lambda: life.setAutonomousAbilityEnabled("SpeakingMovement", False),
              "SpeakingMovement off")
    except Exception:
        pass
    _safe(motion.wakeUp, "wakeUp")
    _safe(lambda: motion.setStiffnesses(_STIFF_JOINTS, 1.0), "stiffness")
    _safe(lambda: motion.setExternalCollisionProtectionEnabled("Arms", False),
          "arm collision")
    # Kill residual walk / idle so setAngles is visible.
    _safe(lambda: motion.moveToward(0.0, 0.0, 0.0), "stop walk")
    return motion


def _leds(session):
    try:
        return session.service("ALLeds")
    except Exception:
        return None


def _set_autonomous_blink(session, enabled):
    try:
        blink = session.service("ALAutonomousBlinking")
        blink.setEnabled(bool(enabled))
    except Exception as e:
        print("[AskGesture] ALAutonomousBlinking: %s" % e)


def _face_leds_off(leds):
    if leds is None:
        return
    if _safe(lambda: leds.off("FaceLeds")) is None:
        _safe(lambda: leds.off("AllLeds"))


def _face_leds_color(leds, color="white", duration=0.15):
    if leds is None:
        return
    ok = _safe(lambda: leds.fadeRGB("FaceLeds", color, float(duration)))
    if ok is None:
        _safe(lambda: leds.reset("FaceLeds"))


def _blink_eyes(leds, times=4, color="white"):
    """Explicit FaceLeds blinks (dark <-> color)."""
    if leds is None:
        return
    for _ in range(int(times)):
        _safe(lambda: leds.fadeRGB("FaceLeds", "black", 0.06))
        time.sleep(0.10)
        try:
            leds.fadeRGB("FaceLeds", color, 0.06)
        except Exception:
            _safe(lambda: leds.fadeRGB("FaceLeds", 0x00FFFF, 0.06))
        time.sleep(0.16)


def _go(motion, angles, speed=0.25):
    """
    Blocking pose move. Prefer angleInterpolationWithSpeed (waits until done);
    fall back to setAngles + sleep.
    """
    angles = [float(a) for a in angles]
    try:
        motion.angleInterpolationWithSpeed(_POSE_NAMES, angles, float(speed))
        return
    except Exception as e:
        print("[AskGesture] angleInterpolationWithSpeed fallback: %s" % e)
    try:
        motion.setAngles(_POSE_NAMES, angles, float(speed))
        time.sleep(1.6)
    except Exception as e:
        print("[AskGesture] setAngles failed: %s" % e)


def _right_rest():
    """Right arm down at side."""
    return [1.15, -0.18, 0.1, 0.6]


def _pose(head_yaw, head_pitch, hip_pitch, l_arm, r_arm=None):
    """Build a full pose list matching _POSE_NAMES.

    l_arm = [LShoulderPitch, LShoulderRoll, LElbowYaw, LElbowRoll, LWristYaw, LHand]
    """
    if r_arm is None:
        r_arm = _right_rest()
    return [
        float(head_yaw), float(head_pitch), float(hip_pitch),
        float(l_arm[0]), float(l_arm[1]), float(l_arm[2]),
        float(l_arm[3]), float(l_arm[4]), float(l_arm[5]),
        float(r_arm[0]), float(r_arm[1]), float(r_arm[2]), float(r_arm[3]),
    ]


# Palm-up "put it in my hand" left arm (ElbowYaw + WristYaw rotate palm skyward).
# ShoulderPitch ~0.25-0.55 = forward / slightly down; Hand 1.0 = open.
def _arm_palm_up(pitch, roll=0.32, hand=1.0):
    return [pitch, roll, -1.45, -0.95, -1.15, hand]


def _arm_palm_up_low(pitch=0.65, roll=0.28, hand=1.0):
    """Lower reach toward a table surface."""
    return [pitch, roll, -1.35, -1.05, -1.20, hand]


def _arm_point(pitch=0.15, roll=0.28):
    """
    Forward point. Pepper's hand is one DOF (no true index finger), so we close
    the fingers firmly and align wrist/elbow so it reads as a single-finger point.
    Hand ~0.0 = closed tip; ElbowYaw near 0 keeps knuckles pointing ahead.
    """
    return [pitch, roll, -0.15, -0.35, -1.55, 0.0]


def _arm_grab_close(pitch=0.55, roll=0.30):
    """Same reach but hand closing (grab)."""
    return [pitch, roll, -1.40, -1.00, -1.10, 0.12]


# How long each demo holds its final "asking" pose (seconds).
_HOLD_LIMITED = 5.5
_HOLD_OK = 5.5
_HOLD_IDEAL = 5.5


def _rest_pose():
    """Visible start: arms down, head/hip neutral — so each demo motion is obvious."""
    return _pose(
        0.0, 0.0, 0.0,
        [1.2, 0.15, -0.2, -0.5, -0.3, 0.4],
    )


def _show_tablet(session, tablet_url):
    if not tablet_url:
        print("[AskGesture] No tablet_url — skip tablet message.")
        return False
    try:
        tablet = session.service("ALTabletService")
    except Exception as e:
        print("[AskGesture] ALTabletService unavailable: %s" % e)
        return False
    try:
        try:
            tablet.hideWebview()
        except Exception:
            pass
        try:
            tablet.resetTablet()
        except Exception:
            pass
        time.sleep(0.2)
        # showWebview(url) loads + displays in one call on modern NAOqi.
        try:
            tablet.showWebview(str(tablet_url))
        except TypeError:
            tablet.loadUrl(str(tablet_url))
            tablet.showWebview()
        print("[AskGesture] Tablet showing: %s" % tablet_url)
        return True
    except Exception as e:
        print("[AskGesture] Tablet show failed: %s" % e)
        return False


def _hide_tablet(session):
    try:
        tablet = session.service("ALTabletService")
        tablet.hideWebview()
    except Exception:
        pass


def _say(session, text):
    try:
        tts = session.service("ALTextToSpeech")
        tts.setVolume(0.85)
        tts.say(str(text))
    except Exception as e:
        print("[AskGesture] TTS: %s" % e)


def play_limited(session, tablet_url=None):
    """
    Limited: upright, left arm forward in a pointing pose (closed / finger tip).
    No blinking, no emotion LEDs, no tablet.
    """
    motion = _prepare(session)
    leds = _leds(session)
    _set_autonomous_blink(session, False)
    _face_leds_off(leds)
    _hide_tablet(session)

    _go(motion, _rest_pose(), 0.35)
    # Point straight ahead — closed hand reads as a single-finger point on Pepper.
    _go(motion, _pose(
        0.0, 0.0, 0.0,
        _arm_point(pitch=0.12, roll=0.30),
    ), 0.22)
    # Extra nudge to fully close fingers after the arm settles.
    try:
        motion.closeHand("LHand")
    except Exception:
        _safe(lambda: motion.setAngles(["LHand"], [0.0], 0.35))
    time.sleep(_HOLD_LIMITED)
    return "Limited: forward point (closed finger), held."


def play_ok(session, tablet_url=None):
    """
    OK: clearly stares at the table and reaches the open palm toward it.
    Stronger / lower than limited — head down, arm lower, slight lean.
    """
    motion = _prepare(session)
    leds = _leds(session)
    _set_autonomous_blink(session, False)
    _face_leds_color(leds, "white", 0.2)

    _go(motion, _rest_pose(), 0.35)

    # Phase 1: look down hard at the table (HeadPitch > 0 = down).
    _go(motion, _pose(
        0.0, 0.35, -0.12,
        _arm_palm_up(pitch=0.40, roll=0.30, hand=1.0),
    ), 0.20)
    time.sleep(0.6)

    # Phase 2: stretch open palm lower toward the table and hold the stare.
    _go(motion, _pose(
        0.0, 0.42, -0.18,
        _arm_palm_up_low(pitch=0.72, roll=0.26, hand=1.0),
    ), 0.18)
    time.sleep(_HOLD_OK)
    return "OK: head on table + lower palm-up reach, held."


def play_ideal(session, tablet_url=None):
    """
    Ideal: bend forward, reach over the table, grab gesture, eye blinks,
    head turns toward the object, tablet + spoken request.
    """
    motion = _prepare(session)
    leds = _leds(session)
    _set_autonomous_blink(session, False)

    _go(motion, _rest_pose(), 0.35)

    # Attention eyes + tablet message first so the ask is obvious.
    _face_leds_color(leds, "cyan", 0.25)
    tablet_ok = _show_tablet(session, tablet_url)

    # Spoken ask (non-blocking would be nicer, but say() is fine for a demo).
    # Run TTS in parallel with the bend so motion doesn't wait on speech alone.
    tts_thread_started = False
    try:
        import threading
        t = threading.Thread(target=lambda: _say(session, TABLET_MSG))
        t.daemon = True
        t.start()
        tts_thread_started = True
    except Exception:
        _say(session, TABLET_MSG)

    # Phase 1: lean forward (HipPitch < 0), look at table, start reach.
    _go(motion, _pose(
        0.15, 0.38, -0.45,
        _arm_palm_up_low(pitch=0.55, roll=0.30, hand=1.0),
    ), 0.18)
    _blink_eyes(leds, times=2, color="cyan")

    # Phase 2: reach further over the table, glance toward object (yaw).
    _go(motion, _pose(
        0.35, 0.40, -0.55,
        _arm_palm_up_low(pitch=0.78, roll=0.22, hand=1.0),
    ), 0.16)
    time.sleep(0.4)
    _blink_eyes(leds, times=2, color="white")

    # Phase 3: grab close, then reopen — "I want to take it".
    _go(motion, _pose(
        0.40, 0.42, -0.55,
        _arm_grab_close(pitch=0.75, roll=0.22),
    ), 0.28)
    time.sleep(0.45)
    try:
        motion.openHand("LHand")
    except Exception:
        _safe(lambda: motion.setAngles(["LHand"], [1.0], 0.3))

    # Phase 4: look up briefly at the person (social cue), then back to hand/object.
    _go(motion, _pose(
        0.10, 0.05, -0.40,
        _arm_palm_up_low(pitch=0.70, roll=0.25, hand=1.0),
    ), 0.20)
    time.sleep(0.5)
    _go(motion, _pose(
        0.30, 0.38, -0.50,
        _arm_palm_up_low(pitch=0.72, roll=0.24, hand=1.0),
    ), 0.18)
    _blink_eyes(leds, times=3, color="cyan")
    time.sleep(_HOLD_IDEAL)

    if leds is not None:
        _face_leds_color(leds, "white", 0.2)

    # Keep tablet up a moment for the audience, then clear.
    time.sleep(1.0)
    if tablet_ok:
        pass

    if tts_thread_started:
        pass
    return "Ideal: bend + reach + grab + blinks + head cue + tablet/TTS, held."


DEMOS = {
    "limited": play_limited,
    "ok": play_ok,
    "ideal": play_ideal,
}


def play(session, which, tablet_url=None):
    key = str(which).strip().lower()
    if key not in DEMOS:
        raise ValueError("Unknown ask demo: %s (use limited|ok|ideal)" % which)
    return DEMOS[key](session, tablet_url=tablet_url)
