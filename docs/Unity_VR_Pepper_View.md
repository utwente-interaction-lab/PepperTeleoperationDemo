# Pepper VR — HTTP streams and technical reference

> **Installation:** **`PepperVrDemoPackage`** (OpenXR + XR Interaction Toolkit required) — **[UNITY_VR_SETUP.md](UNITY_VR_SETUP.md)**.

The teleop GUI runs a small HTTP server on **port 8080** on the operator PC. While Pepper's cameras are subscribed, JPEG frames are published at:

| Path | Camera |
|------|--------|
| `/pepper.jpg` | Top (forehead) - main "Pepper's view" |
| `/pepper_bottom.jpg` | Bottom (mouth / chin) |
| `/pepper_depth.jpg` | Depth sensor, as **grayscale** (see below) |

Example:

```
http://<OPERATOR_PC_IP>:8080/pepper.jpg
```

Your **VR machine** (often the same PC as the GUI) must be able to reach that URL. If the headset is wireless (Quest, etc.), the PC running Unity must be on the same LAN and Windows Firewall must allow inbound TCP **8080**.

**Not Pepper's NAOqi IP:** Pepper is reached at something like `192.168.1.61:9559` for robot control. The JPEG stream is **not** on that address - it is always on the **operator PC** that runs `pepper_gui.py`, port **8080**. No public internet is required; a private LAN is enough. If Unity runs on that same PC, use `http://127.0.0.1:8080/pepper.jpg`.

---

## Quick test (no Unity)

Open in a desktop browser on the operator PC:

- `http://127.0.0.1:8080/pepper.html` - live Pepper camera (JS polling, like the tablet)

If that works, Unity can use the same feed.

---

## Multiple cameras in VR (layout idea)

Use **three copies** of the same `PepperCameraStream` pattern (or one script with three URLs):

- **Large central quad** -> `.../pepper.jpg` (forehead - primary navigation view).
- **Smaller panel bottom-left** -> `.../pepper_bottom.jpg` (close-up / people in front of chest).
- **Smaller panel bottom-right** -> `.../pepper_depth.jpg` (distance cue).

Parent all quads to the **XR camera** with small local offsets so they move with head rotation, or use a **world-locked** panel if you prefer a fixed "control room" feel.

---

## What "depth" is (and what it is not)

- Pepper's **depth sensor** returns range information; the GUI turns it into a **grayscale JPEG**: brighter ~ farther (after normalization), darker ~ closer, using the raw 16-bit buffer when NAOqi provides it that way.
- This is **not** a 3D mesh, **not** automatic collision, and **not** perfect metric depth in Unity without extra calibration.
- **Relating depth to RGB:** true fusion (overlay, point cloud, reprojection) needs **camera intrinsics + extrinsics** and more math in Unity or a separate library - a reasonable next step for a research project, but out of scope for this HTTP-only bridge.
- If `/pepper_depth.jpg` looks wrong (noise or flat), your firmware may pack depth differently; check the session log for decode warnings.

---

## Unity setup (high level)

1. Create a **Unity 2021.3 LTS** (or newer) **3D** project.
2. Install **XR** support:
   - **Edit -> Project Settings -> XR Plug-in Management**
   - Enable your device (e.g. **OpenXR** for Quest Link / Rift / many PCVR headsets, or **Oculus** legacy package if you prefer).
3. Add a **quad or UI RawImage** in front of the camera (world-space canvas works well).

---

## Download `pepper.jpg` into a texture (recommended pattern)

Poll with **cache busting** so every request gets a fresh JPEG (same idea as the Pepper tablet).

Attach this to the quad / RawImage GameObject (set `serverUrl` to your PC's LAN IP, e.g. `http://192.168.1.50:8080/pepper.jpg`):

```csharp
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

public class PepperCameraStream : MonoBehaviour
{
    [Tooltip("Full URL, no query string - script adds ?t= for cache bust")]
    public string serverUrl = "http://192.168.1.50:8080/pepper.jpg";

    [Tooltip("Interval between frames in seconds (~0.08 = ~12 fps)")]
    public float pollInterval = 0.08f;

    public Renderer targetRenderer;   // assign a quad's MeshRenderer
    // Or use UnityEngine.UI.RawImage + texture assignment instead

    void Start()
    {
        StartCoroutine(PollLoop());
    }

    IEnumerator PollLoop()
    {
        while (true)
        {
            string url = serverUrl + "?t=" + (Time.realtimeSinceStartup * 1000f);
            using (UnityWebRequest req = UnityWebRequestTexture.GetTexture(url))
            {
                yield return req.SendWebRequest();
#if UNITY_2020_2_OR_NEWER
                if (req.result == UnityWebRequest.Result.Success)
#else
                if (!req.isNetworkError && !req.isHttpError)
#endif
                {
                    var tex = DownloadHandlerTexture.GetContent(req);
                    if (tex != null && targetRenderer != null)
                    {
                        var old = targetRenderer.material.mainTexture;
                        targetRenderer.material.mainTexture = tex;
                        if (old != null) Destroy(old);
                    }
                }
            }
            yield return new WaitForSeconds(pollInterval);
        }
    }
}
```

**Note:** This replaces the texture each frame (simple and robust for QVGA). For higher resolutions, switch to a single `Texture2D` and `LoadImage(byte[])` to avoid per-frame allocations.

---

## Stereo VR (one image per eye)

Pepper sends a **single** camera image. For presence you usually:

- Show the **same** texture on a large quad in front of the HMD (both eyes see the same "window into Pepper"), or  
- Put the quad on a **world-space canvas** parented so it stays in view.

True stereoscopic 3D would need two camera images or depth - not available from one RGB stream.

---

## Latency tips

- Lower `pollInterval` (e.g. `0.05f`) for smoother motion; more CPU/network load.
- Run Unity on the **same machine** as `pepper_gui.py` and use `http://127.0.0.1:8080/pepper.jpg` to avoid WiFi hop.
- Quest over **Air Link / cable**: PC runs Unity; still use the PC's IP for the stream if the server binds to all interfaces (`0.0.0.0` - already the case).

---

## Firewall (Windows)

Allow inbound **TCP 8080** for the app or for Python when testing from another device:

```powershell
netsh advfirewall firewall add rule name="Pepper teleop stream" dir=in action=allow protocol=TCP localport=8080
```

---

## Related URLs (same server)

| URL | Purpose |
|-----|---------|
| `http://<ip>:8080/` | Operator (MediaPipe) - tablet |
| `http://<ip>:8080/frame.jpg` | Operator JPEG |
| `http://<ip>:8080/pepper.html` | Pepper **top** camera in browser |
| `http://<ip>:8080/pepper.jpg` | Pepper **top** (forehead) - main VR view |
| `http://<ip>:8080/pepper_bottom.jpg` | Pepper **bottom** (mouth) |
| `http://<ip>:8080/pepper_depth.jpg` | Depth as grayscale |
