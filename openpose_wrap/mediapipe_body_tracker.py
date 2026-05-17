"""
mediapipe_body_tracker.py
-------------------------
Plain-camera body tracker that publishes BODY_25-compatible keypoints for
pepper teleoperation on tcp://*:1234.

Also publishes JPEG preview frames for the GUI on tcp://*:1236.
"""

import argparse
import json
import sys

import cv2
import mediapipe as mp
import numpy as np
import zmq

ZMQ_PORT = 1234
FRAME_PORT = 1236

# BODY_25 keys consumed by keypoints_to_angles.py
# 0 Nose, 1 Neck, 2 RShoulder, 3 RElbow, 4 RWrist, 5 LShoulder, 6 LElbow, 7 LWrist, 8 MidHip
MP_TO_BODY25 = {
    "nose": 0,
    "left_shoulder": 5,
    "right_shoulder": 2,
    "left_elbow": 6,
    "right_elbow": 3,
    "left_wrist": 7,
    "right_wrist": 4,
    "left_hip": 8,   # used to derive mid-hip
    "right_hip": 8,  # used to derive mid-hip
}

LM = mp.solutions.pose.PoseLandmark
LANDMARKS = {
    "nose": LM.NOSE,
    "left_shoulder": LM.LEFT_SHOULDER,
    "right_shoulder": LM.RIGHT_SHOULDER,
    "left_elbow": LM.LEFT_ELBOW,
    "right_elbow": LM.RIGHT_ELBOW,
    "left_wrist": LM.LEFT_WRIST,
    "right_wrist": LM.RIGHT_WRIST,
    "left_hip": LM.LEFT_HIP,
    "right_hip": LM.RIGHT_HIP,
}


class KeypointPublisher(object):
    def __init__(self, port=ZMQ_PORT):
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.PUB)
        self.sock.bind("tcp://*:%d" % port)
        print("[MP] Keypoint PUB bound tcp://*:%d" % port)

    def send(self, data):
        self.sock.send_string(json.dumps(data))

    def close(self):
        self.sock.close()
        self.ctx.term()


class FramePublisher(object):
    def __init__(self, port=FRAME_PORT):
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.PUB)
        self.sock.bind("tcp://*:%d" % port)
        print("[MP] Frame PUB bound tcp://*:%d" % port)

    def send(self, jpg_bytes):
        self.sock.send(jpg_bytes)

    def close(self):
        self.sock.close()
        self.ctx.term()


def _landmark_xyz(landmark, w, h, scale):
    # Camera-centered coordinates in meters-ish scale.
    x = (landmark.x - 0.5) * scale
    y = (0.5 - landmark.y) * scale
    z = (-landmark.z) * scale
    return np.array([x, y, z], dtype=np.float32)


def _open_camera(index):
    """
    Open a camera with Windows-friendly backend fallbacks.
    CAP_DSHOW is usually more stable than MSMF for long-running reads.
    """
    backends = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append(("DSHOW", cv2.CAP_DSHOW))
    if hasattr(cv2, "CAP_MSMF"):
        backends.append(("MSMF", cv2.CAP_MSMF))
    backends.append(("DEFAULT", None))

    for name, backend in backends:
        try:
            cap = cv2.VideoCapture(index, backend) if backend is not None else cv2.VideoCapture(index)
        except Exception:
            continue
        if cap is not None and cap.isOpened():
            # Conservative defaults to reduce driver stress.
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
            print("[MP] Camera opened: index=%d backend=%s" % (index, name))
            return cap
        try:
            cap.release()
        except Exception:
            pass
    return None


def run(args):
    # Bind PUB sockets first, so duplicate tracker instances fail early without
    # grabbing the camera (prevents webcam LED blink / black-start confusion).
    try:
        kpub = KeypointPublisher()
        fpub = FramePublisher()
    except Exception as e:
        print("[MP] ERROR: tracker ports busy (1234/1236). Another tracker is likely running.")
        print("[MP] Details: %s" % e)
        sys.exit(1)

    cap = _open_camera(args.camera_index)
    if cap is None:
        print("[MP] ERROR: camera %d not available." % args.camera_index)
        print("[MP] Tip: close Zoom/Teams/OBS and retry with --camera-index 1")
        try:
            kpub.close()
            fpub.close()
        except Exception:
            pass
        sys.exit(1)
    ema = {}
    last_pts = {}

    pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=args.min_det_conf,
        min_tracking_confidence=args.min_track_conf,
    )

    print("[MP] Running. Press q to quit.")
    frame_failures = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                frame_failures += 1
                if frame_failures == 1 or frame_failures % 30 == 0:
                    print("[MP] WARN: camera read failed (%d)." % frame_failures)

                # Camera may have been stolen/reset by driver; attempt reopen.
                if frame_failures >= 45:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = _open_camera(args.camera_index)
                    if cap is None:
                        # Fallback: probe a few common camera indices.
                        for i in (0, 1, 2):
                            cap = _open_camera(i)
                            if cap is not None:
                                print("[MP] Switched to camera index %d." % i)
                                args.camera_index = i
                                break
                    frame_failures = 0
                if not args.no_display:
                    # Keep UI responsive even when frame reads fail.
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        break
                continue
            frame_failures = 0

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = pose.process(rgb)

            wp = {}
            if res.pose_landmarks:
                lms = res.pose_landmarks.landmark
                world_lms = res.pose_world_landmarks.landmark if res.pose_world_landmarks else None

                # Dynamic metric-ish scale: shoulder width ~= 0.35 m
                ls = lms[LANDMARKS["left_shoulder"]]
                rs = lms[LANDMARKS["right_shoulder"]]
                shoulder_px = max(np.hypot((ls.x - rs.x) * w, (ls.y - rs.y) * h), 30.0)
                scale = 0.35 / (shoulder_px / float(w))

                # build raw points
                pts = {}
                for name, lm_id in LANDMARKS.items():
                    lm = lms[lm_id]
                    if world_lms is not None:
                        wm = world_lms[lm_id]
                        # pose_world is in meters; invert y to keep "up" positive.
                        p = np.array([float(wm.x), float(-wm.y), float(wm.z)], dtype=np.float32)
                        if lm.visibility >= args.min_visibility:
                            pts[name] = p
                        elif name in last_pts:
                            pts[name] = last_pts[name]
                    else:
                        if lm.visibility >= args.min_visibility:
                            pts[name] = _landmark_xyz(lm, w, h, scale)
                        elif name in last_pts:
                            pts[name] = last_pts[name]

                # derive neck and mid-hip
                if "left_shoulder" in pts and "right_shoulder" in pts:
                    pts["neck"] = 0.5 * (pts["left_shoulder"] + pts["right_shoulder"])
                if "left_hip" in pts and "right_hip" in pts:
                    pts["mid_hip"] = 0.5 * (pts["left_hip"] + pts["right_hip"])

                # y-offset calibration (e.g. -0.04 m to compensate high bias)
                for k in list(pts.keys()):
                    pts[k][1] += args.y_offset_m

                # publish BODY_25 format
                map_pairs = [
                    ("nose", "0"),
                    ("neck", "1"),
                    ("right_shoulder", "2"),
                    ("right_elbow", "3"),
                    ("right_wrist", "4"),
                    ("left_shoulder", "5"),
                    ("left_elbow", "6"),
                    ("left_wrist", "7"),
                    ("mid_hip", "8"),
                ]
                for src, dst in map_pairs:
                    if src not in pts:
                        continue
                    p = pts[src]
                    # EMA smoothing
                    if dst in ema:
                        p = args.ema_alpha * p + (1.0 - args.ema_alpha) * ema[dst]
                    ema[dst] = p
                    last_pts[src] = p
                    wp[dst] = [float(p[0]), float(p[1]), float(p[2])]

                # draw landmarks for debug preview
                mp.solutions.drawing_utils.draw_landmarks(
                    frame, res.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS
                )

            kpub.send(wp)

            preview = cv2.resize(frame, (640, 360))
            ok_enc, enc = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok_enc:
                fpub.send(enc.tobytes())

            if not args.no_display:
                cv2.imshow("MediaPipe Tracker", frame)
                if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                    break
    finally:
        pose.close()
        cap.release()
        cv2.destroyAllWindows()
        kpub.close()
        fpub.close()
        print("[MP] Shutdown complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MediaPipe-based body tracker for Pepper teleoperation")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--min-det-conf", type=float, default=0.6)
    parser.add_argument("--min-track-conf", type=float, default=0.6)
    parser.add_argument("--min-visibility", type=float, default=0.35)
    parser.add_argument("--ema-alpha", type=float, default=0.35)
    parser.add_argument("--y-offset-m", type=float, default=-0.04)
    run(parser.parse_args())
