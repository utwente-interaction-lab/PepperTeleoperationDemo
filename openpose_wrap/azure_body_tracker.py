"""
azure_body_tracker.py - Azure Kinect DK body tracker for Pepper teleoperation
==============================================================================
Replaces op_depth_keypoints.py (Kinect v2 + OpenPose).

Reads 3D skeleton joints from the Azure Kinect Body Tracking SDK via
pykinect_azure, maps the 9 relevant joints to the BODY_25 dict format
expected by keypoints_to_angles.py, and publishes the result over a
ZeroMQ PUB socket (tcp://*:1234) - identical wire protocol to the
original script so the pepper_teleoperation side needs no changes.

Requirements
------------
  pip install pykinect_azure pyzmq numpy opencv-python
  Azure Kinect Sensor SDK 1.4.x installed
  Azure Kinect Body Tracking SDK 1.1.x installed

Usage
-----
  python azure_body_tracker.py
  python azure_body_tracker.py --no-display
  python azure_body_tracker.py --no-display --depth-mode WFOV_2X2BINNED
"""

import sys
import os
import time
import json
import argparse
from datetime import datetime

import numpy as np
import cv2
import zmq

# ---------------------------------------------------------------------------
# pykinect_azure import - graceful error if SDK not found
# ---------------------------------------------------------------------------
try:
    import pykinect_azure as pykinect
    from pykinect_azure import K4ABT_JOINT_CONFIDENCE_MEDIUM
except ImportError as e:
    print("[AZ] ERROR: pykinect_azure not found. Install with:")
    print("       pip install pykinect_azure")
    print("     AND ensure the Azure Kinect Sensor SDK + Body Tracking SDK")
    print("     are installed on your system.")
    print("     Original error:", e)
    sys.exit(1)

# Local imports
from pyazure_lib.joint_map import AZURE_TO_BODY25, MIN_CONFIDENCE

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ZMQ_PORT        = 1234          # publisher port (matches socket_receive.py)
FRAME_PORT      = 1236          # JPEG preview stream for GUI
DEPTH_MODES = {
    "NFOV_2X2BINNED": pykinect.K4A_DEPTH_MODE_NFOV_2X2BINNED,
    "NFOV_UNBINNED":  pykinect.K4A_DEPTH_MODE_NFOV_UNBINNED,
    "WFOV_2X2BINNED": pykinect.K4A_DEPTH_MODE_WFOV_2X2BINNED,
    "WFOV_UNBINNED":  pykinect.K4A_DEPTH_MODE_WFOV_UNBINNED,
}

# BODY_25 skeleton bone pairs (subset for display)
SKELETON_BONES = [
    ('0','1'),  # Nose - Neck
    ('1','2'),  # Neck - RShoulder
    ('1','5'),  # Neck - LShoulder
    ('2','3'),  # RShoulder - RElbow
    ('3','4'),  # RElbow - RWrist
    ('5','6'),  # LShoulder - LElbow
    ('6','7'),  # LElbow - LWrist
    ('1','8'),  # Neck - MidHip
]

# ---------------------------------------------------------------------------
# ZMQ publisher
# ---------------------------------------------------------------------------
class KeypointPublisher:
    def __init__(self, port=ZMQ_PORT):
        self.ctx  = zmq.Context()
        self.sock = self.ctx.socket(zmq.PUB)
        try:
            self.sock.bind("tcp://*:%d" % port)
            print("[AZ] ZMQ PUB socket bound on tcp://*:%d" % port)
        except zmq.ZMQError as e:
            print("[AZ] ZMQ bind error:", e)
            sys.exit(1)

    def send(self, wp_dict):
        """Serialize dict to JSON and publish."""
        self.sock.send_string(json.dumps(wp_dict))

    def close(self):
        self.sock.close()
        self.ctx.term()

class FramePublisher:
    """Publish JPEG preview frames for GUI rendering."""
    def __init__(self, port=FRAME_PORT):
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.PUB)
        try:
            self.sock.bind("tcp://*:%d" % port)
            print("[AZ] Frame PUB socket bound on tcp://*:%d" % port)
        except zmq.ZMQError as e:
            print("[AZ] Frame ZMQ bind error:", e)
            self.sock = None

    def send(self, jpg_bytes):
        if self.sock is not None:
            self.sock.send(jpg_bytes)

    def close(self):
        if self.sock is not None:
            self.sock.close()
        self.ctx.term()

# ---------------------------------------------------------------------------
# Helper: project 3D world point to 2D color image pixel
# ---------------------------------------------------------------------------
def project_to_color(device, world_mm):
    """
    Project a 3D point (mm, camera frame) onto the color image.
    Returns (u, v) in pixels or None on failure.
    device: pykinect_azure device handle (not used directly;
            we use the calibration attached to the body_frame)
    world_mm: list/array [x, y, z] in mm
    """
    # pykinect_azure does not expose projection directly - we project
    # using the Azure Kinect SDK's coordinate_transform via the
    # body_frame.body_index_map calibration or via the device calibration.
    # For simplicity we draw on the depth-encoded colour image
    # without pixel-perfect projection (screen overlay only).
    return None

# ---------------------------------------------------------------------------
# Draw skeleton on a colour image using 2D joint pixel positions
# ---------------------------------------------------------------------------
def draw_skeleton_2d(image, joint_pixels, body25_dict, colour=(0, 200, 80)):
    """
    joint_pixels: dict  BODY_25_key -> (u, v) pixels
    body25_dict:  dict  BODY_25_key -> [x, y, z] metres (for labels)
    """
    radius = 8
    thickness = 3
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.4

    # Draw joints
    for key, pt in joint_pixels.items():
        cv2.circle(image, pt, radius, colour, -1)
        cv2.putText(image, key, (pt[0]+6, pt[1]-6),
                    font, font_scale, (255,255,255), 1, cv2.LINE_AA)

    # Draw bones
    for a, b in SKELETON_BONES:
        if a in joint_pixels and b in joint_pixels:
            cv2.line(image, joint_pixels[a], joint_pixels[b], colour, thickness, cv2.LINE_AA)

    return image

# ---------------------------------------------------------------------------
# Main tracker loop
# ---------------------------------------------------------------------------
def run(args):
    # -- Initialise SDK --
    # Body tracking needs k4abt DLL initialization as well.
    # Some pykinect_azure builds require track_body=True explicitly.
    try:
        pykinect.initialize_libraries(track_body=True)
    except TypeError:
        # Fallback for older wrappers with different signature support.
        pykinect.initialize_libraries()

    dev_config = pykinect.default_configuration
    dev_config.color_resolution = pykinect.K4A_COLOR_RESOLUTION_720P
    try:
        depth_mode = DEPTH_MODES[args.depth_mode]
    except KeyError:
        print("[AZ] Unknown depth mode '%s'. Valid options: %s"
              % (args.depth_mode, list(DEPTH_MODES.keys())))
        sys.exit(1)
    dev_config.depth_mode     = depth_mode
    dev_config.synchronized_images_only = True

    print("[AZ] Opening Azure Kinect device ...")
    device = pykinect.start_device(config=dev_config)
    print("[AZ] Device opened.")

    # Compatibility across pykinect_azure variants.
    bt_config = getattr(pykinect, "default_body_tracker_configuration", None)
    if bt_config is None:
        bt_config = getattr(pykinect, "k4abt_tracker_default_configuration", None)
    if bt_config is None:
        print("[AZ] ERROR: unsupported pykinect_azure version (no tracker default config).")
        sys.exit(1)
    # Different pykinect_azure builds expose different call signatures.
    try:
        try:
            body_tracker = pykinect.start_body_tracker(body_tracker_config=bt_config)
        except TypeError:
            try:
                body_tracker = pykinect.start_body_tracker(tracker_configuration=bt_config)
            except TypeError:
                body_tracker = pykinect.start_body_tracker()
    except Exception as e:
        print("[AZ] ERROR: could not start body tracker.")
        print("     Ensure Azure Kinect Body Tracking SDK is installed and on PATH.")
        print("     Typical path:")
        print("     C:\\Program Files\\Azure Kinect Body Tracking SDK\\tools")
        print("     Original error:", e)
        sys.exit(1)
    print("[AZ] Body tracker started.")

    publisher = KeypointPublisher()
    frame_publisher = FramePublisher()

    # FPS counter
    t_prev = time.perf_counter()
    frame_count = 0
    fps = 0.0

    print("[AZ] Entering main loop. Press Q (display window) or Ctrl-C to quit.\n")

    try:
        while True:
            # ---- Capture ----
            capture = device.update()
            body_frame = body_tracker.update()

            frame_count += 1
            t_now = time.perf_counter()
            elapsed = t_now - t_prev
            if elapsed >= 1.0:
                fps = frame_count / elapsed
                frame_count = 0
                t_prev = t_now

            # ---- Colour image (for display + GUI stream) ----
            ret_color, color_image = capture.get_color_image()
            if not ret_color or color_image is None:
                continue

            if not args.no_display:
                # Resize for local display speed
                display_img = cv2.resize(color_image, (0,0), fx=0.5, fy=0.5)
            else:
                display_img = None

            # ---- Extract body 0 joints ----
            wp_dict = {}        # BODY_25 key -> [x, y, z] in METRES
            joint_pixels = {}   # BODY_25 key -> (u, v) pixels (display only)

            num_bodies = body_frame.get_num_bodies()
            if num_bodies > 0:
                # Pick the most relevant body: closest valid pelvis depth.
                chosen_idx = 0
                best_depth = None
                for body_idx in range(num_bodies):
                    try:
                        sk = body_frame.get_body(body_idx).numpy()
                        pelvis = sk[0]  # K4ABT_JOINT_PELVIS
                        z_mm = float(pelvis[2])
                        conf = int(pelvis[7])
                        if conf < MIN_CONFIDENCE or z_mm <= 0:
                            continue
                        if best_depth is None or z_mm < best_depth:
                            best_depth = z_mm
                            chosen_idx = body_idx
                    except Exception:
                        continue

                skeleton = body_frame.get_body(chosen_idx).numpy()
                # skeleton shape: (32, 8)
                #   columns: x_mm, y_mm, z_mm, qw, qx, qy, qz, confidence
                for azure_id, body25_key in AZURE_TO_BODY25.items():
                    try:
                        joint = skeleton[azure_id]
                        confidence = int(joint[7])
                        if confidence < MIN_CONFIDENCE:
                            continue

                        x_mm, y_mm, z_mm = float(joint[0]), float(joint[1]), float(joint[2])

                        # Skip invalid readings
                        if z_mm <= 0 or z_mm > 4000:
                            continue

                        # Convert mm -> metres (same as original KinectV2 pipeline)
                        x_m = x_mm / 1000.0
                        y_m = y_mm / 1000.0
                        z_m = z_mm / 1000.0

                        wp_dict[body25_key] = [x_m, y_m, z_m]

                        # Compute rough 2D projection for overlay
                        if display_img is not None:
                            h, w = display_img.shape[:2]
                            # Pinhole projection using approximate FOV
                            # Azure Kinect color camera ~90 deg hFOV @ 720p
                            fx = w / (2.0 * np.tan(np.radians(45)))
                            fy = fx
                            cx = w / 2.0
                            cy = h / 2.0
                            if z_mm > 0:
                                u = int(fx * (x_mm / z_mm) + cx)
                                v = int(fy * (y_mm / z_mm) + cy)
                                if 0 <= u < w and 0 <= v < h:
                                    joint_pixels[body25_key] = (u, v)
                    except (IndexError, TypeError):
                        continue

            # ---- Publish ----
            publisher.send(wp_dict)
            preview = cv2.resize(color_image, (640, 360))
            ok, enc = cv2.imencode('.jpg', preview, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok:
                frame_publisher.send(enc.tobytes())
            if wp_dict:
                keys_str = sorted(wp_dict.keys())
                print("[AZ] %.1f FPS | bodies=%d | joints sent: %s" %
                      (fps, num_bodies, keys_str), end='\r')
            else:
                print("[AZ] %.1f FPS | no body detected       " % fps, end='\r')

            # ---- Display ----
            if display_img is not None:
                if joint_pixels:
                    display_img = draw_skeleton_2d(display_img, joint_pixels, wp_dict)

                cv2.putText(display_img, "%.1f FPS" % fps,
                            (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,220,80), 2)
                cv2.putText(display_img, "Bodies: %d" % num_bodies,
                            (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,220,80), 2)
                cv2.imshow("Azure Kinect - Body Tracker", display_img)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    break

    except KeyboardInterrupt:
        print("\n[AZ] Interrupted by user.")
    finally:
        publisher.close()
        frame_publisher.close()
        cv2.destroyAllWindows()
        print("[AZ] Shutdown complete.")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Azure Kinect body tracker for Pepper teleoperation")
    parser.add_argument(
        "--no-display", action="store_true",
        help="Disable the OpenCV preview window (headless mode).")
    parser.add_argument(
        "--depth-mode", default="WFOV_2X2BINNED",
        choices=list(DEPTH_MODES.keys()),
        help="Azure Kinect depth mode (default: WFOV_2X2BINNED).")
    args = parser.parse_args()
    run(args)
