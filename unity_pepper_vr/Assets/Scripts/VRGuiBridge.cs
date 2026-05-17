using System.Collections;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;

/// <summary>
/// Bridge Unity VR UI buttons to the desktop Pepper GUI via HTTP.
/// Attach to any scene object, then wire button OnClick() to:
///   ToggleVRDrive, ToggleArmMirror, ToggleBodyDrive, ToggleKeyboardTeleop, StopAllDrive
/// </summary>
public class VRGuiBridge : MonoBehaviour
{
    [Header("Server")]
    [Tooltip("Teleop PC server base URL (same host as /vr_move).")]
    public string serverBase = "http://192.168.1.123:8080";

    [Header("Status Polling")]
    public bool pollStatus = true;
    [Range(0.2f, 3f)] public float pollEverySeconds = 0.8f;
    public Text statusLabel;
    [TextArea(1, 3)] public string lastStatus = "";

    bool _busy;
    float _pollTimer;

    [System.Serializable]
    class BridgeStatus
    {
        public bool ok;
        public bool connected;
        public string mode;
        public bool arm_mirror;
        public bool body_drive;
        public bool vr_drive;
        public bool keyboard_teleop;
        public string mjpeg_ip;
    }

    void Update()
    {
        if (!pollStatus || _busy)
            return;
        _pollTimer += Time.unscaledDeltaTime;
        if (_pollTimer >= Mathf.Max(0.2f, pollEverySeconds))
        {
            _pollTimer = 0f;
            StartCoroutine(PollStatus());
        }
    }

    public void ToggleVRDrive()         { StartAction("toggle_vr_drive"); }
    public void ToggleArmMirror()       { StartAction("toggle_arm_mirror"); }
    public void ToggleBodyDrive()       { StartAction("toggle_body_drive"); }
    public void ToggleKeyboardTeleop()  { StartAction("toggle_keyboard_teleop"); }
    public void StopAllDrive()          { StartAction("stop_all_drive"); }

    void StartAction(string action)
    {
        if (_busy) return;
        StartCoroutine(SendAction(action));
    }

    IEnumerator SendAction(string action)
    {
        _busy = true;
        string url = string.Format("{0}/control?action={1}", serverBase.TrimEnd('/'), action);
        using (UnityWebRequest req = UnityWebRequest.Get(url))
        {
            req.timeout = 2;
            yield return req.SendWebRequest();
#if UNITY_2020_2_OR_NEWER
            bool ok = req.result == UnityWebRequest.Result.Success;
#else
            bool ok = !req.isNetworkError && !req.isHttpError;
#endif
            lastStatus = ok ? ("action ok: " + action) : ("action fail: " + (req.error ?? "unknown"));
            PushStatusText(lastStatus);
        }
        _busy = false;
    }

    IEnumerator PollStatus()
    {
        _busy = true;
        string url = string.Format("{0}/status", serverBase.TrimEnd('/'));
        using (UnityWebRequest req = UnityWebRequest.Get(url))
        {
            req.timeout = 2;
            yield return req.SendWebRequest();
#if UNITY_2020_2_OR_NEWER
            bool ok = req.result == UnityWebRequest.Result.Success;
#else
            bool ok = !req.isNetworkError && !req.isHttpError;
#endif
            if (!ok)
            {
                lastStatus = "status fail: " + (req.error ?? "unknown");
                PushStatusText(lastStatus);
            }
            else
            {
                BridgeStatus st = null;
                try
                {
                    st = JsonUtility.FromJson<BridgeStatus>(req.downloadHandler.text);
                }
                catch { }
                if (st != null)
                {
                    lastStatus = string.Format(
                        "GUI conn={0} mode={1} vr={2} arm={3} body={4} kb={5}",
                        st.connected, st.mode, st.vr_drive, st.arm_mirror, st.body_drive, st.keyboard_teleop);
                    PushStatusText(lastStatus);
                }
                else
                {
                    lastStatus = "status parse fail";
                    PushStatusText(lastStatus);
                }
            }
        }
        _busy = false;
    }

    void PushStatusText(string s)
    {
        if (statusLabel != null)
            statusLabel.text = s;
    }
}

