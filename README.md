# Pepper Teleoperation — MediaPipe

**Repository:** [github.com/utwente-interaction-lab/PepperTeleoperationDemo](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo)  
**VR package:** [Releases](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases) (`PepperVrDemoPackage.unitypackage` — requires OpenXR + XR Interaction Toolkit)

Control a SoftBank **Pepper** robot in real time using your body movements captured via a standard webcam and [MediaPipe Pose](https://google.github.io/mediapipe/solutions/pose).

This repository extends an inherited Pepper teleoperation stack (Python 2.7 GUI + pose-driven mirroring) with MediaPipe tracking and optional Unity VR viewing.

```bash
git clone https://github.com/utwente-interaction-lab/PepperTeleoperationDemo.git
cd PepperTeleoperationDemo
```

---

## Hardware requirements

| Item | Required? | Notes |
|------|-----------|--------|
| **SoftBank Pepper** robot | Yes | On the same LAN as the operator PC; NAOqi reachable (default port `9559`) |
| **Windows PC** | Yes | Tested on Windows 10/11; runs the GUI, tracker, and HTTP video server |
| **Webcam** | Yes (MediaPipe path) | USB camera for body pose; good lighting helps tracking |
| **Wi‑Fi / Ethernet LAN** | Yes | PC and Pepper on the same network; no public internet required |
| **Meta Quest (or similar) + Unity** | Optional | `PepperVrDemoPackage` + OpenXR + XR Interaction Toolkit — [`docs/UNITY_VR_SETUP.md`](docs/UNITY_VR_SETUP.md) |
| **Azure Kinect DK** | Optional | Alternative tracker; see `requirements_azure.txt` and set `TRACKER_BACKEND=azure` in `Start_Pepper_Azure.bat` |

**Example IPs in this repo** (`192.168.1.61` for Pepper, `192.168.1.123` for the teleop PC) are lab defaults. Set your real addresses in the GUI and in Unity **Server Url** / **Stream Base** fields.

---

## Features
| Feature | Description |
|---|---|
| **Arm Mirror** | Pepper's arms copy your arm movements in real time |
| **Body Drive** | Lean forward/back/side to drive Pepper; hands up to stop |
| **Mode switching** | Hold a T-pose for 2.5 s to swap between Arm Mirror and Body Drive hands-free |
| **Manual Locomotion** | Click buttons to nudge Pepper in any direction |
| **Pepper Camera** | Live feed from Pepper's forehead camera in the GUI |
| **Tablet Feed** | Streams your MediaPipe camera to Pepper's chest tablet so people near the robot can see the operator |
| **VR / Unity** | Pepper's onboard camera at `http://<PC>:8080/pepper.jpg`; VR scene via Unity package — [docs/UNITY_VR_SETUP.md](docs/UNITY_VR_SETUP.md) |
| **Keyboard Teleop** | WASD + Q/E to move Pepper from the keyboard |

---

## Software requirements

| Component | Version | Purpose |
|-----------|---------|---------|
| **Choregraphe Suite** | 2.5.x | NAOqi Python bindings (`qi`, `naoqi`) — not on PyPI |
| **Miniconda / Anaconda** | Latest | Creates `pepper27_32` (Python 2.7 **32-bit**) for the GUI |
| **Python** | 3.10 | MediaPipe body tracker (`openpose_wrap/`) |
| **Unity** | 2022.2+ (optional) | OpenXR, XR Interaction Toolkit (+ Starter Assets), then `PepperVrDemoPackage` — [`docs/UNITY_VR_SETUP.md`](docs/UNITY_VR_SETUP.md) |

**Python dependencies (installed by `setup.bat`):**

- GUI: [`requirements_gui.txt`](requirements_gui.txt) → `numpy`, `scipy`, `matplotlib`, `pyzmq`, `Pillow`
- Tracker: [`requirements_tracker.txt`](requirements_tracker.txt) → `mediapipe`, `opencv-python`, `pyzmq`, `numpy`
- Optional Azure Kinect: [`requirements_azure.txt`](requirements_azure.txt)

---

## Prerequisites (install before setup)

You need **three** things installed before running setup:
### 1 - Choregraphe Suite 2.5 (provides NAOqi Python bindings)

> These are **not on PyPI**. The `qi` and `naoqi` Python modules ship inside Choregraphe.

1. Create a free account at [SoftBank Robotics Community](https://community.softbankrobotics.com/)
2. Download **Choregraphe Suite 2.5.10** for Windows (or the latest 2.5.x)
3. Install to the default path:
   ```
   C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\
   ```
   If you install elsewhere, edit the top two lines of `Start_Pepper_Azure.bat`:
   ```bat
   set "CHORE_LIB=C:\your\custom\path\lib"
   set "CHORE_BIN=C:\your\custom\path\bin"
   ```

### 2 - Miniconda (to create the Python 2.7 32-bit GUI environment)

Download from <https://docs.conda.io/en/latest/miniconda.html>  
Install the **64-bit** Miniconda3 for Windows (the Python version of Miniconda itself doesn't matter; we create a 32-bit env inside it).

### 3 - Python 3.10 (for the MediaPipe tracker)

Download from <https://www.python.org/downloads/>  
Make sure **"Add Python to PATH"** is checked during install, or use `py -3.10` launcher.

---

## Setup (automated)

Run the provided script **once** after installing the prerequisites above:

```bat
setup.bat
```

This will:
- Create the `pepper27_32` conda environment (Python 2.7 32-bit)
- Install all GUI dependencies into it (`numpy`, `pillow`, `pyzmq`, `scipy`, `matplotlib`)
- Install all tracker dependencies for Python 3.10 (`mediapipe`, `opencv-python`, `pyzmq`, `numpy`)

---

## Setup (manual - if setup.bat fails)

### GUI environment (Python 2.7 32-bit)

```bat
set CONDA_FORCE_32BIT=1
conda create -n pepper27_32 python=2.7 -y
conda activate pepper27_32
pip install -r requirements_gui.txt
```

### Tracker environment (Python 3.10)

```bat
py -3.10 -m pip install -r requirements_tracker.txt
```

---

## Running

```bat
Start_Pepper_Azure.bat
```

This opens two windows:
1. **Body Tracker** - MediaPipe webcam feed (keep it open, don't close it)
2. **Pepper GUI** - control panel

**First steps in the GUI:**
1. Enter Pepper's IP address (default `192.168.1.61`) and click **Connect**
2. Click **Start Arm Mirror (MediaPipe)** and stand in front of the webcam
3. Optionally click **Show Operator on Pepper Tablet** - people near Pepper will see you

Logs are saved to the `logs/` folder if anything goes wrong.

After the first Pepper camera frame, the session log shows the **VR stream URL** (`http://...:8080/pepper.jpg`).

---

## VR headset (Unity)

1. Run the Python stack and **Connect** to Pepper (same as desktop use).
2. Install **OpenXR**, **XR Interaction Toolkit**, and **Starter Assets** (see guide).
3. **Import** `PepperVrDemoPackage.unitypackage` from [Releases](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases) — use package scripts only, not `unity_pepper_vr/` from git.
4. Open the demo scene (must include **XR Interaction Manager**).
5. Set teleop PC IP on **Stream Base** / **Server Base** → Play → **VR Drive** in Python GUI.

| Doc | Content |
|-----|---------|
| **[docs/UNITY_VR_SETUP.md](docs/UNITY_VR_SETUP.md)** | Import package into your project, IPs, first run |
| **[unity_pepper_vr/README.md](unity_pepper_vr/README.md)** | Depth HUD, locomotion, wrist UI, manual scene build |
| **[docs/Unity_VR_Pepper_View.md](docs/Unity_VR_Pepper_View.md)** | HTTP endpoints, firewall, sample code |

Streams: **`/pepper.jpg`** (main), **`/pepper_bottom.jpg`**, **`/pepper_depth.jpg`** — browser test: `http://127.0.0.1:8080/pepper.html`.

---

## Gesture controls (no buttons needed)

| Gesture | Action |
|---|---|
| **T-pose** (arms spread wide, held 2.5 s) | Switch between Arm Mirror <-> Body Drive |
| **Both hands above shoulders** | Emergency stop (Body Drive only) |
| **Right hand up** (Body Drive) | Move forward |
| **Left hand up** (Body Drive) | Move backward |

---

## Folder structure

```
pepper_openpose_teleoperation/
├── README.md
├── LICENSE / NOTICE
├── setup.bat
├── Start_Pepper_Azure.bat
├── requirements_gui.txt
├── requirements_tracker.txt
├── requirements_azure.txt          (optional Kinect tracker)
├── docs/
│   ├── GITHUB_PUBLISH.md
│   ├── UNITY_VR_SETUP.md           (Unity package / project install)
│   └── Unity_VR_Pepper_View.md
├── openpose_wrap/
│   ├── mediapipe_body_tracker.py
│   └── azure_body_tracker.py       (optional)
├── pepper_teleoperation/
│   └── pepper_gui.py
└── unity_pepper_vr/                (reference scripts; use PepperVrDemoPackage from Releases)
```

---

## Documentation

| Document | Audience |
|----------|----------|
| This README | Install, run, troubleshoot |
| [`docs/GITHUB_PUBLISH.md`](docs/GITHUB_PUBLISH.md) | Publishing and updating on GitHub |
| [`docs/UNITY_VR_SETUP.md`](docs/UNITY_VR_SETUP.md) | XRI + OpenXR deps, import `PepperVrDemoPackage`, configure, run |
| [`unity_pepper_vr/README.md`](unity_pepper_vr/README.md) | VR features (depth, locomotion, manual build) |
| [`docs/Unity_VR_Pepper_View.md`](docs/Unity_VR_Pepper_View.md) | HTTP streams and technical reference |

---

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). **Choregraphe**, **Pepper**, **MediaPipe**, and **Unity** remain under their respective vendor licenses; you must install and accept those separately.
---

## Troubleshooting

| Error | Fix |
|---|---|
| `Could not find qi Python bindings` | Choregraphe not installed, or installed to a non-default path. Edit `CHORE_LIB` / `CHORE_BIN` in the bat file. |
| `Could not find pepper27_32 Python environment` | Run `setup.bat` first, or follow the manual setup steps above. |
| `Missing MediaPipe tracker deps` | Run `py -3.10 -m pip install -r requirements_tracker.txt` |
| Arm Mirror does nothing | Make sure the Body Tracker window is open and detecting you |
| Pepper camera shows "No feed" | Check that Pepper is reachable (`ping 192.168.1.61`) and on the same network |
| Tablet feed not updating | Ensure your PC and Pepper are on the same network; check the IP shown in the GUI log |

---

## Network requirements (for Tablet Feed)

The operator PC and Pepper must be on the **same local network** (same WiFi or LAN).  
The MJPEG server runs on **port 8080** of the operator's PC - make sure no firewall blocks it.  
The URL shown in the GUI log (e.g. `http://192.168.1.x:8080/`) can also be opened in any browser to preview the feed.
