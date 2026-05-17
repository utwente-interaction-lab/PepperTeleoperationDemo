# Unity VR — scripts and feature reference

> **Start here:** [`docs/UNITY_VR_SETUP.md`](../docs/UNITY_VR_SETUP.md) — download **`PepperVR.unitypackage`** from [Releases](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases) and import it into your Unity XR project.  
> Use **this file** for depth HUD, locomotion, and troubleshooting after import.

This folder is **source code** for maintainers. End users only need the **`.unitypackage`** (pre-built scene inside the package).

| Contents | Purpose |
|----------|---------|
| `Assets/Scripts/` | Camera streams, VR locomotion, depth assist, wrist UI |
| `Assets/Editor/` | **Tools → Pepper VR** setup menus |

---

## HTTP blocked (white quads, Console: "Insecure connection not allowed")
Unity **2022.2+** blocks `http://` camera URLs unless you allow it:

1. In the editor menu, run **Tools -> Pepper VR -> Allow HTTP for LAN camera streams** (sets Player Settings for you), **or**
2. **Edit -> Project Settings -> Player -> Other Settings** -> **Allow downloads over HTTP** -> **Always allowed**.

Then press Play again. Builds use the same Player setting.

## Two different addresses (important)

**This repo is pre-filled for your lab Wi-Fi:**

| What | Pre-filled value | Role |
|------|------------------|------|
| **Pepper (robot)** | `192.168.1.61:9559` | NAOqi - already the default in **`pepper_gui.py`** connection field. |
| **Video stream (teleop PC)** | `http://192.168.1.123:8080/pepper.jpg` | Default in **`PepperCameraStream.cs`** - the PC that runs `pepper_gui.py`. |

You do **not** need the public internet. A dedicated LAN (router + PC + Pepper) is enough.

- If your teleop PC's IP changes, update **Server Url** on the Unity component (or edit the default in `PepperCameraStream.cs`).
- **Same PC as Unity:** you can still use `http://127.0.0.1:8080/pepper.jpg` instead of `.123` if you prefer.
- **Unity on another machine:** set **Server Url** to `http://192.168.1.123:8080/pepper.jpg` (the teleop PC's address - **not** Pepper's `.61`).

To check the teleop PC IP: `ipconfig` -> IPv4.

---

## What you need running

1. `Start_Pepper_Azure.bat` (tracker + GUI)
2. **Connect** to Pepper (`192.168.1.61:9559` or whatever yours is) so the GUI can pull Pepper's camera and push JPEGs to port **8080** on **your PC**.

---

## Manual setup (maintainers only)

Use this only when developing from `unity_pepper_vr/Assets/` in the repo — **not** for normal users (they import `PepperVR.unitypackage`).

### 1. Add the scripts

- Copy `Assets/Scripts/` and `Assets/Editor/` into your Unity project.
- Unity compiles automatically; use **Tools → Pepper VR** for helpers.

### 2. Add a Quad

- **GameObject -> 3D Object -> Quad**
- Name it e.g. `PepperViewQuad`

### 3. Attach the stream component

- Select the Quad -> **Add Component -> Pepper Camera Stream**
- Leave **Server Url** as `http://127.0.0.1:8080/pepper.jpg` if Unity runs on the **same PC** as the teleop GUI.
- If Unity runs on another machine on the LAN, set it to `http://<teleop-pc-ip>:8080/pepper.jpg` and open Windows Firewall for TCP **8080** on the teleop PC.

### 4. Position in VR

**Target Renderer:** leave **None** if `PepperCameraStream` is on the **same GameObject as the Quad** - it auto-uses that Quad's renderer. Only assign a field if the stream component sits on a parent and the mesh is on a child.

**Default (XR Interaction Toolkit, etc.):** leave **Attach In Front Of Main Camera** **unchecked** - you parent the Quad yourself under **XR Origin -> Camera Offset -> Main Camera**, set **local position** (e.g. `0, 0, 2`) and **scale** yourself.

**Quick test in an empty scene:** enable **Attach In Front Of Main Camera** so the script parents to `Camera.main` and sets distance + scale from the Inspector.

### 5. Material (URP)

- Default quad uses **Lit**; the video can look dark. Create a material with **Shader: Universal Render Pipeline / Unlit** (or **Unlit/Texture**) and assign it to the Quad. The script sets `mainTexture` each frame - Unlit works well.

### 6. Play

- Enter **Play** with the teleop GUI connected and Pepper camera running.
- You should see the live feed; if not, check the **Console** for HTTP errors and confirm `http://127.0.0.1:8080/pepper.html` works in a browser on that PC.

---

## Three Pepper streams (optional)

After connecting in the GUI, the same PC also serves three JPEG paths (same **Stream Base**, different path).

**In Unity:** add **one Quad + `PepperCameraStream` per feed**. On each component:

1. Set **Stream Base** to `http://192.168.1.123:8080` (your teleop PC - same on all three).
2. Set **Which Camera**:
   - **Top Forehead** -> main view  
   - **Bottom Mouth** -> chest camera  
   - **Depth Grayscale** -> depth panel  

Or choose **Custom** and paste a full URL in **Custom Server Url**.

| Inspector `Which Camera` | HTTP path |
|--------------------------|-----------|
| Top Forehead | `/pepper.jpg` |
| Bottom Mouth | `/pepper_bottom.jpg` |
| Depth Grayscale | `/pepper_depth.jpg` |

Arrange the three quads in VR (sizes/positions) - see **Multiple cameras in VR** in the doc below.

---

## Depth Assist HUD (recommended for teleoperation)

`DepthAssistHUD.cs` reads the **depth quad texture** and gives a simple driving cue:
- **CLEAR** (green)
- **CAUTION** (amber)
- **STOP** (red)

It also shows left/right bias (`OBSTACLE LEFT` or `OBSTACLE RIGHT`) plus normalized center/side risk values.

### 1) Add depth stream quad

If you do not already have one:
1. Create a quad named `PepperDepthQuad`.
2. Add `PepperCameraStream`.
3. Set:
   - **Stream Base** = `http://<teleop-pc-ip>:8080`
   - **Which Camera** = `DepthGrayscale`
4. Use an Unlit material for visibility.

### 2) Create a world-space HUD canvas

1. **GameObject -> UI -> Canvas**
2. Set **Render Mode** = `World Space`.
3. Parent it under your XR camera rig so it stays in view (e.g. near lower center).
4. Add:
   - A **Panel/Image** (background color block),
   - A **Text** (legacy UI Text is fine) for status.

Suggested text style:
- Font size: 28-40 (depends on world scale)
- Alignment: middle-left
- Color: white

### 3) Add and wire `DepthAssistHUD`

1. Add `DepthAssistHUD` to the Canvas (or an empty HUD object).
2. Drag references:
   - **Depth Stream** -> your depth quad's `PepperCameraStream`
   - **Status Text** -> the Text component
   - **Status Panel** -> the panel Image component
3. Keep defaults first:
   - `sampleRateHz = 8`
   - `sampleStride = 8`
   - `cautionCenterNear = 0.45`
   - `stopCenterNear = 0.65`

### 4) Tune for your environment

- If warnings trigger too often: increase `cautionCenterNear` / `stopCenterNear`.
- If warnings are too late: decrease those thresholds.
- If CPU is high: lower `sampleRateHz` (e.g. 6) or increase `sampleStride` (e.g. 10-12).
- If response feels slow: raise `sampleRateHz` to 10-12.

### 5) Best VR layout

- Keep **RGB top feed** as primary.
- Put **depth panel + Depth Assist HUD** as a smaller helper panel (lower-right or lower-center).
- Do not replace the main RGB feed with depth permanently; use depth as a safety cue.

---

## RGB + Depth Overlay + Left/Right indicator

If grayscale depth alone is not useful, use `DepthOverlayAssist.cs` to build one combined view:
- RGB stays visible
- near-depth regions are tinted (amber/red)
- simple left/right/center indicators show obstacle bias

### One-click helper (recommended)

Use menu:
**Tools -> Pepper VR -> Create Depth Overlay Assist Rig**

This creates a world-space Canvas rig, adds the composite `RawImage`, left/right/center indicators,
TMP status text, and auto-wires `DepthOverlayAssist` to the first scene streams found with:
- `WhichCamera = TopForehead`
- `WhichCamera = DepthGrayscale`

If the menu says streams were not found, create the two stream quads first, then run again.

### 1) Scene objects required

1. `PepperViewTop` quad with `PepperCameraStream` -> `WhichCamera = TopForehead`
2. `PepperViewDepth` quad with `PepperCameraStream` -> `WhichCamera = DepthGrayscale`
3. A world-space UI Canvas with:
   - `RawImage` (composite display)
   - `Image` for left indicator
   - `Image` for right indicator
   - optional `Image` for center indicator
   - `Text (TMP)` for status

### 2) Add and wire `DepthOverlayAssist`

1. Add `DepthOverlayAssist` on the Canvas (or an empty object under it).
2. Assign:
   - **Rgb Stream** -> `PepperViewTop`'s `PepperCameraStream`
   - **Depth Stream** -> `PepperViewDepth`'s `PepperCameraStream`
   - **Composite Raw Image** -> your output `RawImage`
   - **Left Indicator** / **Right Indicator** (and optional **Center Indicator**)
   - **Status Text TMP** (or legacy `Status Text`)

You can leave fallback renderer fields empty when stream refs are assigned.

### 3) Good starting values

- `updateRateHz = 10`
- `sampleStride = 6`
- `cautionNear = 0.42`
- `stopNear = 0.62`
- `sideNear = 0.52`

### 4) How to read it

- **CLEAR**: mostly safe path
- **CAUTION**: something is close in center or one side
- **STOP**: near obstacle in center
- Brighter left/right indicators = obstacle bias on that side

### 5) Tuning tips

- Overlay too aggressive -> raise `cautionNear` and `stopNear`
- Overlay too weak -> lower thresholds slightly
- CPU too high -> lower `updateRateHz` or increase `sampleStride`

---

## VR Locomotion (walk Pepper with VR headset + controllers)

`VRLocomotionSender.cs` captures controller thumbstick input and headset orientation,
then sends HTTP POST commands to the Python teleop server so Pepper walks in the real world.

| Control | Action |
|---------|--------|
| **Left stick forward/back** | Pepper walks forward/backward |
| **Left stick left/right** | Pepper strafes |
| **Right stick left/right** | Pepper rotates |
| **Head orientation** | Optional: movement direction follows where you look |

### Quick setup

1. In Unity: **Tools -> Pepper VR -> Add VR Locomotion Sender** (auto-detects server URL from existing stream components).
2. Or manually: create an empty GameObject, add `VRLocomotionSender`, set **Server Base** to your teleop PC (e.g. `http://192.168.1.123:8080`).
3. In the Python GUI: click **VR Drive (Unity Headset)** to activate the receiver.
4. Press Play in Unity. Thumbstick input now drives Pepper.

### How it works

```
Unity (VRLocomotionSender)
  └─ HTTP POST /vr_move  {"x":0.3, "y":0, "theta":-0.1, "head_yaw":15, "head_pitch":-5}
       │
       ▼
Python MjpegServer :8080
  └─ VRDriveThread
       └─ ALMotion.moveToward(x, y, theta)  →  Pepper walks
```

### Safety

- If Unity stops sending (disconnect, pause, exit), the Python side auto-stops Pepper after 0.6 s.
- Speed is clamped to `maxTranslateSpeed` / `maxStrafeSpeed` / `maxRotateSpeed` in the Inspector.
- Combine with **Depth Assist HUD** or **Depth Overlay Assist** for obstacle awareness.

### Keyboard fallback (no VR headset)

When no XR controllers are detected, `VRLocomotionSender` accepts keyboard input for flat-screen testing:

| Key | Action |
|-----|--------|
| I / K | Forward / Back |
| J / L | Strafe left / right |
| U / O | Rotate left / right |

Disable via `keyboardFallback = false` in the Inspector.

### Inspector settings

| Field | Default | Notes |
|-------|---------|-------|
| Server Base | `http://192.168.1.123:8080` | Same as stream base |
| Max Translate Speed | 0.55 | 0-1 range for moveToward |
| Max Strafe Speed | 0.40 | |
| Max Rotate Speed | 0.50 | |
| Deadzone | 0.12 | Thumbstick dead zone |
| Send Rate Hz | 12 | HTTP POSTs per second |
| Head Relative Movement | true | Stick-forward follows head direction |

---

## More detail

- [../docs/Unity_VR_Pepper_View.md](../docs/Unity_VR_Pepper_View.md) - multi-camera layout, depth limitations, firewall, latency

---

## Git

`Library/`, `Temp/`, `Logs/` under `unity_pepper_vr/` are ignored. Commit `Assets/`, `Packages/`, `ProjectSettings/` as usual.
