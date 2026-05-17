using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

/// <summary>
/// One instance per Quad. Pick the feed in the Inspector: <see cref="WhichCamera"/> + <see cref="StreamBase"/>,
/// or set <see cref="WhichCamera"/> to Custom and paste a full URL in <see cref="CustomServerUrl"/>.
/// </summary>
public class PepperCameraStream : MonoBehaviour
{
    static int s_FailLogFrame = -99999;
    Texture2D _streamTexture;
    int _consecutiveFailures;
    float _nextAllowedRequestAt;
    public enum WhichCamera
    {
        TopForehead = 0,      // /pepper.jpg
        BottomMouth = 1,      // /pepper_bottom.jpg
        DepthGrayscale = 2,   // /pepper_depth.jpg
        Custom = 3            // use Custom Server Url
    }

    [Tooltip("Which Pepper stream this quad displays. Use one component per quad, each with a different choice.")]
    public WhichCamera whichCamera = WhichCamera.TopForehead;

    [Tooltip("Teleop PC + port only, no path. Example: http://192.168.1.123:8080 - ignored when Which Camera = Custom.")]
    public string streamBase = "http://192.168.1.123:8080";

    [Tooltip("Full URL when Which Camera = Custom (e.g. another server or path).")]
    public string customServerUrl = "http://192.168.1.123:8080/pepper.jpg";

    /// <summary>Resolved at runtime from whichCamera + streamBase, or customServerUrl.</summary>
    [HideInInspector]
    public string serverUrl = "";

    [Tooltip("Seconds between HTTP requests (~0.06 = ~16 fps).")]
    public float pollInterval = 0.06f;

    [Header("Display (usually leave Target Renderer empty)")]
    [Tooltip("Leave empty when this component is on the Quad itself - the Quad's Renderer is used automatically. Only drag a reference here if the mesh is on a different object.")]
    public Renderer targetRenderer;

    [Header("Placement (optional)")]
    [Tooltip("OFF = you already parented the quad and set position/scale under the XR camera (recommended for XRI templates). ON = script parents this object to Camera.main and sets distance/scale for you.")]
    public bool attachInFrontOfMainCamera = false;

    [Tooltip("Used only when Attach In Front Of Main Camera is enabled.")]
    public float distanceInFrontOfCamera = 2f;

    [Tooltip("Used only when Attach In Front Of Main Camera is enabled (local scale X,Y).")]
    public Vector2 quadWorldSize = new Vector2(3.2f, 2.4f);

    void Awake()
    {
        if (targetRenderer == null)
            targetRenderer = GetComponent<Renderer>();
    }

    void ResolveServerUrl()
    {
        if (whichCamera == WhichCamera.Custom)
        {
            serverUrl = string.IsNullOrWhiteSpace(customServerUrl)
                ? "http://192.168.1.123:8080/pepper.jpg"
                : customServerUrl.Trim();
            return;
        }

        string b = string.IsNullOrWhiteSpace(streamBase) ? "http://127.0.0.1:8080" : streamBase.Trim().TrimEnd('/');
        switch (whichCamera)
        {
            case WhichCamera.BottomMouth:
                serverUrl = b + "/pepper_bottom.jpg";
                break;
            case WhichCamera.DepthGrayscale:
                serverUrl = b + "/pepper_depth.jpg";
                break;
            default:
                serverUrl = b + "/pepper.jpg";
                break;
        }
    }

    void Start()
    {
        ResolveServerUrl();
        if (string.IsNullOrEmpty(serverUrl))
            Debug.LogError("[PepperCameraStream] serverUrl is empty on " + gameObject.name);

        if (attachInFrontOfMainCamera && Camera.main != null)
        {
            transform.SetParent(Camera.main.transform, false);
            transform.localPosition = new Vector3(0f, 0f, distanceInFrontOfCamera);
            transform.localRotation = Quaternion.identity;
            transform.localScale = new Vector3(quadWorldSize.x, quadWorldSize.y, 1f);
        }

        if (targetRenderer != null && targetRenderer.material != null)
        {
            // Unlit avoids lighting issues on the stream
            if (targetRenderer.material.shader.name.Contains("Standard"))
                Debug.LogWarning("[PepperCameraStream] Consider a URP/HDRP Unlit material for the quad.");
            if (_streamTexture == null)
                _streamTexture = new Texture2D(2, 2, TextureFormat.RGB24, false);
            targetRenderer.material.mainTexture = _streamTexture;
        }

        StartCoroutine(PollLoop());
    }

    IEnumerator PollLoop()
    {
        var wait = new WaitForSeconds(pollInterval);
        while (true)
        {
            if (targetRenderer == null)
            {
                yield return wait;
                continue;
            }

            if (Time.realtimeSinceStartup < _nextAllowedRequestAt)
            {
                yield return wait;
                continue;
            }

            string url = serverUrl + "?t=" + (Time.realtimeSinceStartup * 1000f).ToString("F0");
            using (UnityWebRequest req = UnityWebRequest.Get(url))
            {
                req.downloadHandler = new DownloadHandlerBuffer();
                req.timeout = 3;
                yield return req.SendWebRequest();

#if UNITY_2020_2_OR_NEWER
                bool ok = (req.result == UnityWebRequest.Result.Success);
#else
                bool ok = !req.isNetworkError && !req.isHttpError;
#endif
                if (!ok)
                {
                    _consecutiveFailures++;
                    float backoff = Mathf.Min(1.0f, 0.08f * _consecutiveFailures);
                    _nextAllowedRequestAt = Time.realtimeSinceStartup + backoff;
                    if (Time.frameCount - s_FailLogFrame > 180)
                    {
                        s_FailLogFrame = Time.frameCount;
                        string err = req.error;
#if UNITY_2020_2_OR_NEWER
                        if (string.IsNullOrEmpty(err))
                            err = req.result.ToString();
#else
                        if (string.IsNullOrEmpty(err))
                            err = "network or HTTP error";
#endif
                        Debug.LogWarning("[PepperCameraStream] " + err + "\n  URL: " + url +
                            "\n  If you see 'Insecure' or 'Non-secure', run menu: " +
                            "Tools -> Pepper VR -> Allow HTTP for LAN camera streams (Unity 2022.2+).");
                    }
                    yield return wait;
                    continue;
                }
                _consecutiveFailures = 0;
                _nextAllowedRequestAt = 0f;

                byte[] jpg = req.downloadHandler.data;
                if (jpg != null && jpg.Length > 0)
                {
                    if (_streamTexture == null)
                        _streamTexture = new Texture2D(2, 2, TextureFormat.RGB24, false);
                    if (_streamTexture.LoadImage(jpg, false))
                    {
                        if (targetRenderer.material.mainTexture != _streamTexture)
                            targetRenderer.material.mainTexture = _streamTexture;
                    }
                }
            }

            yield return wait;
        }
    }

    void OnDestroy()
    {
        if (_streamTexture != null)
        {
            Destroy(_streamTexture);
            _streamTexture = null;
        }
    }
}
