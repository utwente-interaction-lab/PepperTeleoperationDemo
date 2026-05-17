using UnityEngine;
using UnityEngine.UI;
using TMPro;

/// <summary>
/// Composites Pepper RGB + depth into a single assist view and exposes simple
/// left/right obstacle indicators for teleoperation.
/// </summary>
public class DepthOverlayAssist : MonoBehaviour
{
    [Header("Input streams")]
    [Tooltip("Top camera stream (RGB).")]
    public PepperCameraStream rgbStream;
    [Tooltip("Depth stream (DepthGrayscale).")]
    public PepperCameraStream depthStream;

    [Tooltip("Optional fallback renderers if stream refs are empty.")]
    public Renderer rgbRendererFallback;
    public Renderer depthRendererFallback;

    [Header("Composite output (choose one)")]
    [Tooltip("Preferred: world-space UI RawImage that shows the composite.")]
    public RawImage compositeRawImage;
    [Tooltip("Alternative: mesh renderer target (quad) if not using UI.")]
    public Renderer compositeRenderer;

    [Header("Left/Right indicators")]
    public Image leftIndicator;
    public Image rightIndicator;
    public Image centerIndicator;
    public TMP_Text statusTextTMP;
    public Text statusText;

    [Header("Timing and quality")]
    [Range(2f, 20f)] public float updateRateHz = 10f;
    [Range(2, 12)] public int sampleStride = 6;

    [Header("Overlay thresholds (0=far, 1=near)")]
    [Range(0f, 1f)] public float cautionNear = 0.42f;
    [Range(0f, 1f)] public float stopNear = 0.62f;
    [Range(0f, 1f)] public float sideNear = 0.52f;

    [Header("Overlay colors")]
    public Color cautionOverlay = new Color(1f, 0.75f, 0.0f, 0.25f);
    public Color stopOverlay = new Color(1f, 0.15f, 0.1f, 0.45f);
    public Color indicatorIdle = new Color(1f, 1f, 1f, 0.18f);
    public Color indicatorWarn = new Color(1f, 0.25f, 0.15f, 0.90f);

    Texture2D _compositeTex;
    Color32[] _rgbPx;
    Color32[] _depthPx;
    Color32[] _outPx;
    float _timer;

    void Start()
    {
        SetStatus("Depth overlay waiting...");
        SetIndicator(leftIndicator, 0f);
        SetIndicator(rightIndicator, 0f);
        SetIndicator(centerIndicator, 0f);
    }

    void Update()
    {
        _timer += Time.unscaledDeltaTime;
        float period = 1f / Mathf.Max(0.01f, updateRateHz);
        if (_timer < period)
            return;
        _timer = 0f;

        Texture2D rgb = ResolveTexture(rgbStream, rgbRendererFallback);
        Texture2D depth = ResolveTexture(depthStream, depthRendererFallback);
        if (rgb == null || depth == null)
        {
            SetStatus("Depth overlay: missing stream");
            return;
        }

        if (!TryReadPixels(rgb, depth))
        {
            SetStatus("Depth overlay: unreadable texture");
            return;
        }

        Compose(rgb.width, rgb.height, depth.width, depth.height);
        PushOutput();
    }

    Texture2D ResolveTexture(PepperCameraStream stream, Renderer fallback)
    {
        if (stream != null && stream.targetRenderer != null && stream.targetRenderer.material != null)
            return stream.targetRenderer.material.mainTexture as Texture2D;
        if (fallback != null && fallback.material != null)
            return fallback.material.mainTexture as Texture2D;
        return null;
    }

    bool TryReadPixels(Texture2D rgb, Texture2D depth)
    {
        try
        {
            _rgbPx = rgb.GetPixels32();
            _depthPx = depth.GetPixels32();
            if (_rgbPx == null || _depthPx == null || _rgbPx.Length == 0 || _depthPx.Length == 0)
                return false;
            return true;
        }
        catch
        {
            return false;
        }
    }

    void Compose(int rw, int rh, int dw, int dh)
    {
        int n = rw * rh;
        if (_outPx == null || _outPx.Length != n)
            _outPx = new Color32[n];

        float centerSum = 0f, leftSum = 0f, rightSum = 0f;
        int centerN = 0, leftN = 0, rightN = 0;
        int s = Mathf.Max(1, sampleStride);

        for (int y = 0; y < rh; y++)
        {
            int rRow = y * rw;
            int dy = Mathf.Clamp((int)((y / (float)rh) * dh), 0, dh - 1);
            int dRow = dy * dw;

            for (int x = 0; x < rw; x++)
            {
                int ridx = rRow + x;
                int dx = Mathf.Clamp((int)((x / (float)rw) * dw), 0, dw - 1);
                int didx = dRow + dx;

                Color32 rc = _rgbPx[ridx];
                Color32 dc = _depthPx[didx];
                float lum = (dc.r + dc.g + dc.b) / (3f * 255f);
                float near = 1f - lum;

                Color outC = rc;
                if (near >= stopNear)
                    outC = Color.Lerp(outC, stopOverlay, stopOverlay.a);
                else if (near >= cautionNear)
                    outC = Color.Lerp(outC, cautionOverlay, cautionOverlay.a);
                _outPx[ridx] = outC;

                if ((x % s) == 0 && (y % s) == 0)
                {
                    bool inMidY = y >= (int)(rh * 0.35f) && y < (int)(rh * 0.90f);
                    if (!inMidY) continue;

                    if (x >= (int)(rw * 0.35f) && x < (int)(rw * 0.65f))
                    {
                        centerSum += near; centerN++;
                    }
                    else if (x < rw / 2)
                    {
                        leftSum += near; leftN++;
                    }
                    else
                    {
                        rightSum += near; rightN++;
                    }
                }
            }
        }

        float c = centerN > 0 ? centerSum / centerN : 0f;
        float l = leftN > 0 ? leftSum / leftN : 0f;
        float r = rightN > 0 ? rightSum / rightN : 0f;

        float lWarn = Mathf.InverseLerp(sideNear, 1f, l);
        float rWarn = Mathf.InverseLerp(sideNear, 1f, r);
        float cWarn = Mathf.InverseLerp(cautionNear, 1f, c);

        SetIndicator(leftIndicator, lWarn);
        SetIndicator(rightIndicator, rWarn);
        SetIndicator(centerIndicator, cWarn);

        string dir = "CENTER";
        if (l > r + 0.08f) dir = "LEFT";
        else if (r > l + 0.08f) dir = "RIGHT";

        if (c >= stopNear) SetStatus("STOP  " + dir + "  C:" + c.ToString("0.00"));
        else if (c >= cautionNear || l >= sideNear || r >= sideNear)
            SetStatus("CAUTION  " + dir + "  C:" + c.ToString("0.00"));
        else
            SetStatus("CLEAR  " + dir + "  C:" + c.ToString("0.00"));

        if (_compositeTex == null || _compositeTex.width != rw || _compositeTex.height != rh)
        {
            _compositeTex = new Texture2D(rw, rh, TextureFormat.RGBA32, false);
            _compositeTex.wrapMode = TextureWrapMode.Clamp;
            _compositeTex.filterMode = FilterMode.Bilinear;
        }
        _compositeTex.SetPixels32(_outPx);
        _compositeTex.Apply(false, false);
    }

    void PushOutput()
    {
        if (_compositeTex == null) return;
        if (compositeRawImage != null)
            compositeRawImage.texture = _compositeTex;
        if (compositeRenderer != null && compositeRenderer.material != null)
            compositeRenderer.material.mainTexture = _compositeTex;
    }

    void SetIndicator(Image img, float t)
    {
        if (img == null) return;
        t = Mathf.Clamp01(t);
        img.color = Color.Lerp(indicatorIdle, indicatorWarn, t);
    }

    void SetStatus(string msg)
    {
        if (statusTextTMP != null) statusTextTMP.text = msg;
        if (statusText != null) statusText.text = msg;
    }
}
