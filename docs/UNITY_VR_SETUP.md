# Unity VR setup (Pepper teleoperation)

VR is delivered as **`PepperVrDemoPackage.unitypackage`** (GitHub Releases). Import it into **your own** Unity project after installing the XR dependencies below.

The **Python teleop stack must be running first** — Unity only talks to the HTTP server on your operator PC.

> **Use the package scripts, not the repo folder.** The GitHub repo includes [`unity_pepper_vr/`](../unity_pepper_vr/) for reference only. After importing **`PepperVrDemoPackage`**, all Pepper VR behaviour comes from the package assets. If you previously copied `unity_pepper_vr/Assets` into your project, **remove those copies** to avoid duplicate types and outdated scripts.

---

## What you need

| Item | Notes |
|------|--------|
| **Unity** | **2022.2 LTS** or newer (LAN `http://` camera streams) |
| **`PepperVrDemoPackage.unitypackage`** | [Releases](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases) |
| **Python teleop** | `Start_Pepper_Azure.bat` → **Connect** to Pepper |
| **XR headset** | e.g. Meta Quest via Link / Air Link |
| **Same LAN** | VR PC and teleop PC |

---

## 1. Install Unity XR dependencies (before importing the package)

Install these **in order** via **Window → Package Manager** (Unity Registry unless noted).

### Required packages

| Package | Why |
|---------|-----|
| **XR Plugin Management** | Enables XR in the project |
| **OpenXR Plugin** | PC VR / Quest Link (recommended) |
| **XR Interaction Toolkit** | Wrist UI, ray interactors, locomotion coexistence with the demo scene |
| **XR Interaction Toolkit Starter Assets** | Sample **XR Origin** rig, input actions, and prefabs the demo scene expects |

**OpenXR setup**

1. **Edit → Project Settings → XR Plug-in Management**
2. Under **PC Standalone** (and **Android** if you build to Quest standalone), enable **OpenXR**
3. Use **XR Plug-in Management → OpenXR** to pick your runtime / controller profile if prompted

**XR Interaction Manager**

The demo scene expects an **XR Interaction Manager** in the hierarchy (usually on or under the **XR Origin** from Starter Assets).

- If you use the **VR template** or import **Starter Assets**, this is often created automatically.
- Otherwise: **GameObject → XR → XR Interaction Manager** (or add the component to your XR Origin root).

Without it, wrist UI and XRI interactors will not work correctly.

### Recommended project template

**Unity Hub → New project → 3D (URP)** or the **VR** template, then add any missing packages from the table above.

Confirm a blank XR scene runs in Play mode with your headset before importing the Pepper package.

---

## 2. Import `PepperVrDemoPackage`

1. Download **`PepperVrDemoPackage.unitypackage`** from **[Releases](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases)**.
2. **Assets → Import Package → Custom Package…** → select the file → **Import all**.
3. Open the **demo scene** from the Project window (path is inside the package, e.g. under `Assets/PepperVrDemo/` or similar — use the scene named in the Release notes).
4. **Do not** merge in scripts from `unity_pepper_vr/` in the cloned Git repo; the package is the supported source.

### If you already copied repo scripts into `Assets/`

1. Delete the old folder (e.g. duplicated `Assets/Scripts/` from `unity_pepper_vr`).
2. Re-import **`PepperVrDemoPackage`** if needed.
3. Use only components and scenes from the package.

Unity resolves script references by **class name**. Duplicate copies cause “script missing”, wrong behaviour, or compile errors — always prefer the **package** version.

---

## 3. Configure network addresses

| Role | Example | Where |
|------|---------|--------|
| **Pepper** | `192.168.1.61:9559` | Python GUI **Connect** only |
| **Teleop PC** | `http://192.168.1.123:8080` | Package scene: **Stream Base** / **Server Base** |

- Teleop PC IP: `ipconfig` → IPv4.
- Unity on the **same PC** as the GUI: `http://127.0.0.1:8080`.

On package components (`PepperCameraStream`, `VRLocomotionSender`, `VRGuiBridge`, etc.):

- **Stream Base** = `http://<teleop-pc-ip>:8080`
- **Server Base** = same URL (no path)

---

## 4. Allow HTTP on LAN (required)

Unity 2022.2+ blocks `http://` unless allowed:

1. **Tools → Pepper VR → Allow HTTP for LAN camera streams** (included in the package), **or**
2. **Edit → Project Settings → Player → Other Settings → Allow downloads over HTTP → Always allowed**

---

## 5. Run

1. **`Start_Pepper_Azure.bat`** → **Connect** to Pepper.
2. Browser: `http://127.0.0.1:8080/pepper.html` (live video on teleop PC).
3. Unity: open the **Pepper VR demo scene** from the package → set **Stream Base** → **Play**.
4. Python GUI: **VR Drive (Unity Headset)** for thumbstick locomotion.

The package scene is built for **XR Interaction Toolkit** + **OpenXR**: use the provided **XR Origin** / wrist UI setup rather than rebuilding from scratch.

Feature reference (depth HUD, locomotion tuning): [`unity_pepper_vr/README.md`](../unity_pepper_vr/README.md) — behaviour matches the package scripts when versions are in sync.

---

## Dependency checklist

Before reporting issues, confirm:

- [ ] **OpenXR** enabled for your build target (PC Standalone at minimum)
- [ ] **XR Interaction Toolkit** installed
- [ ] **XR Interaction Toolkit Starter Assets** installed (sample rig / input)
- [ ] Scene contains **XR Interaction Manager**
- [ ] **`PepperVrDemoPackage`** imported; no duplicate Pepper scripts from `unity_pepper_vr/` in `Assets/`
- [ ] **Allow HTTP** for LAN streams
- [ ] **Stream Base** points at the teleop PC, not Pepper’s NAOqi IP

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Missing scripts / pink materials | Install URP + packages above; re-import package; remove duplicate repo scripts |
| Wrist UI / pointers dead | Add or enable **XR Interaction Manager**; check Starter Assets / XR Origin in scene |
| Controllers move player instead of Pepper | In scene, enable **Disable XR rig move** on `VRLocomotionSender` (or wrist toggle); see package README |
| White quad / insecure HTTP | **Allow HTTP for LAN** (step 4) |
| No video | Browser test; **Stream Base** IP; firewall **TCP 8080** on teleop PC |
| Pepper won’t walk | **VR Drive** in Python GUI; **Server Base** = teleop PC |

```powershell
netsh advfirewall firewall add rule name="Pepper teleop stream" dir=in action=allow protocol=TCP localport=8080
```

---

## Maintainers

Export **`PepperVrDemoPackage.unitypackage`** from the lab Unity project (with XRI + OpenXR + Starter Assets already present). See [`releases/README.md`](../releases/README.md). Keep [`unity_pepper_vr/`](../unity_pepper_vr/) in git aligned with the package export, but tell users to **only** install the Release `.unitypackage`.
