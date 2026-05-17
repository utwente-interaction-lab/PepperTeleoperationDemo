# Unity VR setup (Pepper teleoperation)

VR is delivered as a **Unity package** (`PepperVR.unitypackage`) that you import into **your own** Unity XR project. There is no standalone Unity project to download.

The **Python teleop stack must be running first** — Unity only talks to the HTTP server on your operator PC.

---

## What you need

| Item | Notes |
|------|--------|
| **Your Unity project** | **2022.2 LTS** or newer, with **XR Plug-in Management** + **OpenXR** (or your headset’s plug-in) |
| **`PepperVR.unitypackage`** | From **[Releases](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases)** |
| **Python teleop running** | `Start_Pepper_Azure.bat` → **Connect** to Pepper in the GUI |
| **XR headset** | e.g. Meta Quest via Link / Air Link |
| **Same LAN** | VR PC and teleop PC on the same Wi‑Fi/Ethernet |

---

## 1. Prepare your Unity project

If you do not already have an XR project:

1. **Unity Hub → New project** → **3D (URP)** template (or your lab’s URP template).
2. **Edit → Project Settings → XR Plug-in Management** → install/enable **OpenXR** (PC) and your headset if prompted.
3. Confirm you can enter Play mode with the headset (empty scene is fine).

---

## 2. Import `PepperVR.unitypackage`

1. Download **`PepperVR.unitypackage`** from **[Releases](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases)**.
2. In your project: **Assets → Import Package → Custom Package…** → select the file.
3. Leave all items checked → **Import**.
4. Open the Pepper VR scene from the Project window (e.g. **`Assets/PepperVR/Scenes/PepperVR_Teleop.unity`** — path matches how the package was exported).

The package includes:

- Pre-built **VR scene** (camera views, wrist UI, locomotion wired)
- **Scripts** and **Tools → Pepper VR** editor menus

---

## 3. Configure network addresses

| Role | Example | Where to set it |
|------|---------|-----------------|
| **Pepper (robot)** | `192.168.1.61:9559` | Python GUI **Connect** only |
| **Teleop PC (streams)** | `http://192.168.1.123:8080` | Unity **Stream Base** / **Server Base** |

- Teleop PC IP: `ipconfig` → IPv4 (Windows).
- Unity on the **same PC** as the GUI: use `http://127.0.0.1:8080`.

In the imported scene, set:

- `PepperCameraStream` → **Stream Base** = `http://<teleop-pc-ip>:8080`
- `VRLocomotionSender` / `VRGuiBridge` → **Server Base** = same base URL (no path)

---

## 4. Allow HTTP on LAN (required)

Unity 2022.2+ blocks `http://` unless allowed:

1. **Tools → Pepper VR → Allow HTTP for LAN camera streams**, **or**
2. **Edit → Project Settings → Player → Other Settings → Allow downloads over HTTP → Always allowed**

---

## 5. Run

1. Run **`Start_Pepper_Azure.bat`** and **Connect** to Pepper.
2. Browser test on the teleop PC: `http://127.0.0.1:8080/pepper.html` (live video).
3. Unity: open the Pepper VR scene → fix **Stream Base** if needed → **Play**.
4. Optional: in the Python GUI, **VR Drive (Unity Headset)** for thumbstick locomotion.

Feature details (depth HUD, locomotion, wrist UI): [`unity_pepper_vr/README.md`](../unity_pepper_vr/README.md).

---

## HTTP streams

| Path | Camera |
|------|--------|
| `/pepper.jpg` | Forehead RGB (main view) |
| `/pepper_bottom.jpg` | Chest camera |
| `/pepper_depth.jpg` | Depth (grayscale) |

See [`Unity_VR_Pepper_View.md`](Unity_VR_Pepper_View.md) for API and firewall notes.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| White quad / insecure HTTP | **Allow HTTP for LAN** (step 4) |
| No video | Browser test first; correct **Stream Base**; firewall **TCP 8080** on teleop PC |
| Pepper won’t walk from VR | **VR Drive** in Python GUI; **Server Base** = teleop PC |
| Import errors / pink materials | Match **URP** and Unity **2022.2+** to the version noted on the Release |

```powershell
netsh advfirewall firewall add rule name="Pepper teleop stream" dir=in action=allow protocol=TCP localport=8080
```

---

## Source scripts in this repo (maintainers)

The folder [`unity_pepper_vr/`](../unity_pepper_vr/) holds the same C# sources used to build the package. End users should **not** need it — only import the `.unitypackage`. Re-export the package from Unity when scripts change; see [`releases/README.md`](../releases/README.md).
