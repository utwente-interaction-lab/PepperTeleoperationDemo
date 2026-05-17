# Releases — Unity VR package

VR is distributed only as a Unity package — **not** as a full Unity project.

## Publish this file

| File | Description |
|------|-------------|
| **`PepperVR.unitypackage`** | Import into any Unity **2022.2+** XR project (URP recommended) |

## Export from Unity

1. Open your development Unity project (with the finished Pepper VR scene).
2. Select the folder to ship (e.g. `Assets/PepperVR/` including `Scenes/`, scripts, prefabs, materials).
3. **Assets → Export Package…** → include dependencies → save as `PepperVR.unitypackage`.
4. **GitHub → Releases → New release** → tag e.g. `v1.0.0` → attach `PepperVR.unitypackage`.
5. In the release notes, state: **Unity version**, **URP version**, **OpenXR** (or required XR plug-in).
6. Release URL: https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases

Keep `unity_pepper_vr/` in this repo in sync with the exported package (tag the same commit when possible).
