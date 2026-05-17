# Publishing to GitHub (UTwente Interaction Lab)

Public repository: **[utwente-interaction-lab/PepperTeleoperationDemo](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo)**

```text
https://github.com/utwente-interaction-lab/PepperTeleoperationDemo.git
```

Run commands from the project root (folder containing `README.md`).

---

## Before you upload

1. **No secrets** — passwords, API keys, or personal data must not be committed.
2. **Lab IPs** — defaults like `192.168.1.61` / `192.168.1.123` are examples only.
3. **Ignored data** (do not force-add): `logs/`, `pepper_teleoperation/angles_data/`, `openpose_wrap/keypoints_data/`, `openpose_wrap/video_data/`, Unity `Library/`.

---

## First push

```powershell
cd "C:\path\to\PepperTeleoperationDemo"

git init
git add .
git status
git commit -m "Initial release: Pepper MediaPipe teleoperation with optional VR"

git branch -M main
git remote add origin https://github.com/utwente-interaction-lab/PepperTeleoperationDemo.git
git push -u origin main
```

If the org repo already exists on GitHub (empty), use the remote above. If you created it with a README on the website, pull first:

```powershell
git pull origin main --rebase
git push -u origin main
```

Use a **Personal Access Token** when Git asks for a password (not your GitHub account password).

---

## Unity VR package (Releases)

After the code is on GitHub:

1. Export **`PepperVrDemoPackage.unitypackage`** from Unity (see [`releases/README.md`](../releases/README.md)).
2. Open https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases → **Draft a new release**.
3. Tag e.g. `v1.0.0`, attach the package; note Unity + URP + **XRI + OpenXR + Starter Assets** + demo scene path.
4. Publish the release so [`UNITY_VR_SETUP.md`](UNITY_VR_SETUP.md) download links work.

---

## Later updates

```powershell
git add .
git status
git commit -m "Describe what you changed"
git push
```

---

## Suggested repo settings (org admins)

| Setting | Suggestion |
|---------|------------|
| **Description** | Real-time Pepper teleoperation with MediaPipe pose tracking and optional Unity VR |
| **Topics** | `pepper`, `robotics`, `teleoperation`, `mediapipe`, `naoqi`, `unity`, `vr` |
| **Visibility** | Public (for sharing with students / collaborators) |

---

## What clone users need

- **Clone:** `git clone https://github.com/utwente-interaction-lab/PepperTeleoperationDemo.git`
- **Setup:** `setup.bat` → `Start_Pepper_Azure.bat`
- **VR:** `PepperVrDemoPackage` from [Releases](https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases) — see [UNITY_VR_SETUP.md](UNITY_VR_SETUP.md) (XRI + OpenXR required)
