# Releases — `PepperVrDemoPackage`

VR is distributed as a Unity package only (not a full Unity project).

## Publish this file

| File | Description |
|------|-------------|
| **`PepperVrDemoPackage.unitypackage`** | Demo scene + Pepper VR scripts (requires XRI + OpenXR — see below) |

## User prerequisites (state in every Release note)

Users must install **before** importing the package:

1. **XR Plugin Management**
2. **OpenXR Plugin**
3. **XR Interaction Toolkit**
4. **XR Interaction Toolkit Starter Assets** (sample XR Origin / input)

The demo scene expects an **XR Interaction Manager** (usually from Starter Assets / XR Origin).

Full steps: [`docs/UNITY_VR_SETUP.md`](../docs/UNITY_VR_SETUP.md)

## Export from Unity

1. Open the lab project with XRI, OpenXR, and Starter Assets already configured.
2. Select the Pepper demo folder (scene, prefabs, scripts under e.g. `Assets/PepperVrDemo/`).
3. **Assets → Export Package…** → include dependencies → save as **`PepperVrDemoPackage.unitypackage`**.
4. **GitHub → Releases** → tag e.g. `v1.0.0` → attach the file.
5. In release notes include: **Unity version**, **URP version**, **XRI version**, **scene path**, and the dependency list above.

Release URL: https://github.com/utwente-interaction-lab/PepperTeleoperationDemo/releases

Keep [`unity_pepper_vr/`](../unity_pepper_vr/) in the git repo in sync with the exported package; users should import the **Release package**, not copy `unity_pepper_vr/` into their project.
