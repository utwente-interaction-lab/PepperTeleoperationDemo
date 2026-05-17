using UnityEngine;
using UnityEngine.UI;
using TMPro;

/// <summary>
/// Lightweight depth HUD for Pepper teleoperation.
/// Reads the depth stream texture (grayscale JPEG), computes simple risk metrics,
/// and updates a status label/background for VR users.
/// </summary>
public class DepthAssistHUD : MonoBehaviour
{
    [Header("Depth source")]
    [Tooltip("PepperCameraStream set to WhichCamera = DepthGrayscale.")]
    public PepperCameraStream depthStream;

    [Tooltip("Optional fallback renderer if depthStream is not set.")]
    public Renderer depthRendererFallback;

    [Header("UI outputs")]
    [Tooltip("Legacy UI Text (optional).")]
    public Text statusText;
    [Tooltip("TextMeshPro text (optional). Use this for Text (TMP) components.")]
    public TMP_Text statusTextTMP;
    public Image statusPanel;

    [Header("Sampling")]
    [Tooltip("How often to compute depth risk (Hz).")]
    [Range(2f, 20f)]
    public float sampleRateHz = 8f;

    [Tooltip("Sample every N pixels (bigger = cheaper, less detail).")]
    [Range(2, 16)]
    public int sampleStride = 8;

    [Header("Thresholds (0=far, 1=very near)")]
    [Range(0f, 1f)] public float cautionCenterNear = 0.45f;
    [Range(0f, 1f)] public float stopCenterNear = 0.65f;
    [Range(0f, 1f)] public float sideWarnNear = 0.55f;

    [Header("Colors")]
    public Color clearColor = new Color(0.10f, 0.55f, 0.15f, 0.80f);
    public Color cautionColor = new Color(0.78f, 0.58f, 0.10f, 0.86f);
    public Color stopColor = new Color(0.75f, 0.18f, 0.18f, 0.90f);
    public Color missingColor = new Color(0.20f, 0.20f, 0.20f, 0.75f);

    float _sampleTimer;
    readonly Color32[] _empty = new Color32[0];

    enum RiskState
    {
        NoSignal,
        Clear,
        Caution,
        Stop
    }

    void Start()
    {
        SetStatusText("Depth Assist\nWaiting for depth stream...");
        if (statusPanel != null)
            statusPanel.color = missingColor;
    }

    void Update()
    {
        float dt = Time.unscaledDeltaTime;
        _sampleTimer += dt;
        float period = 1f / Mathf.Max(0.01f, sampleRateHz);
        if (_sampleTimer < period)
            return;
        _sampleTimer = 0f;

        Texture2D tex = ResolveDepthTexture();
        if (tex == null)
        {
            SetUi(RiskState.NoSignal, 0f, 0f, 0f);
            return;
        }

        Color32[] px;
        try
        {
            px = tex.GetPixels32();
        }
        catch
        {
            // GetPixels32 requires Read/Write texture access. PepperCameraStream uses readable textures by default.
            px = _empty;
        }

        if (px.Length == 0 || tex.width <= 4 || tex.height <= 4)
        {
            SetUi(RiskState.NoSignal, 0f, 0f, 0f);
            return;
        }

        float centerNear, leftNear, rightNear;
        EvaluateRisk(px, tex.width, tex.height, sampleStride, out centerNear, out leftNear, out rightNear);
        RiskState state = ComputeState(centerNear, leftNear, rightNear);
        SetUi(state, centerNear, leftNear, rightNear);
    }

    Texture2D ResolveDepthTexture()
    {
        if (depthStream != null && depthStream.targetRenderer != null && depthStream.targetRenderer.material != null)
            return depthStream.targetRenderer.material.mainTexture as Texture2D;

        if (depthRendererFallback != null && depthRendererFallback.material != null)
            return depthRendererFallback.material.mainTexture as Texture2D;

        return null;
    }

    static void EvaluateRisk(Color32[] px, int w, int h, int stride,
        out float centerNear, out float leftNear, out float rightNear)
    {
        // Use lower-middle rows where navigation obstacles are usually visible.
        int y0 = Mathf.FloorToInt(h * 0.35f);
        int y1 = Mathf.FloorToInt(h * 0.90f);
        y0 = Mathf.Clamp(y0, 0, h - 1);
        y1 = Mathf.Clamp(y1, y0 + 1, h);

        int cx0 = Mathf.FloorToInt(w * 0.35f);
        int cx1 = Mathf.FloorToInt(w * 0.65f);
        cx0 = Mathf.Clamp(cx0, 0, w - 1);
        cx1 = Mathf.Clamp(cx1, cx0 + 1, w);

        float centerSum = 0f, leftSum = 0f, rightSum = 0f;
        int centerN = 0, leftN = 0, rightN = 0;

        int s = Mathf.Max(1, stride);
        for (int y = y0; y < y1; y += s)
        {
            int row = y * w;
            for (int x = 0; x < w; x += s)
            {
                Color32 c = px[row + x];
                // Depth image is grayscale JPEG; lower brightness means nearer.
                float lum = (c.r + c.g + c.b) / (3f * 255f);
                float near = 1f - lum;

                if (x >= cx0 && x < cx1)
                {
                    centerSum += near;
                    centerN++;
                }
                else if (x < w / 2)
                {
                    leftSum += near;
                    leftN++;
                }
                else
                {
                    rightSum += near;
                    rightN++;
                }
            }
        }

        centerNear = centerN > 0 ? centerSum / centerN : 0f;
        leftNear = leftN > 0 ? leftSum / leftN : 0f;
        rightNear = rightN > 0 ? rightSum / rightN : 0f;
    }

    RiskState ComputeState(float centerNear, float leftNear, float rightNear)
    {
        if (centerNear >= stopCenterNear)
            return RiskState.Stop;
        if (centerNear >= cautionCenterNear || leftNear >= sideWarnNear || rightNear >= sideWarnNear)
            return RiskState.Caution;
        return RiskState.Clear;
    }

    void SetUi(RiskState state, float centerNear, float leftNear, float rightNear)
    {
        string lateral = "CENTER";
        if (leftNear > rightNear + 0.08f)
            lateral = "OBSTACLE LEFT";
        else if (rightNear > leftNear + 0.08f)
            lateral = "OBSTACLE RIGHT";

        switch (state)
        {
            case RiskState.Stop:
                SetStatusText("Depth Assist: STOP\n" + lateral +
                              "\nC:" + centerNear.ToString("0.00") +
                              " L:" + leftNear.ToString("0.00") +
                              " R:" + rightNear.ToString("0.00"));
                break;
            case RiskState.Caution:
                SetStatusText("Depth Assist: CAUTION\n" + lateral +
                              "\nC:" + centerNear.ToString("0.00") +
                              " L:" + leftNear.ToString("0.00") +
                              " R:" + rightNear.ToString("0.00"));
                break;
            case RiskState.Clear:
                SetStatusText("Depth Assist: CLEAR\n" + lateral +
                              "\nC:" + centerNear.ToString("0.00") +
                              " L:" + leftNear.ToString("0.00") +
                              " R:" + rightNear.ToString("0.00"));
                break;
            default:
                SetStatusText("Depth Assist\nNo depth signal");
                break;
        }

        if (statusPanel != null)
        {
            switch (state)
            {
                case RiskState.Stop: statusPanel.color = stopColor; break;
                case RiskState.Caution: statusPanel.color = cautionColor; break;
                case RiskState.Clear: statusPanel.color = clearColor; break;
                default: statusPanel.color = missingColor; break;
            }
        }
    }

    void SetStatusText(string value)
    {
        if (statusText != null)
            statusText.text = value;
        if (statusTextTMP != null)
            statusTextTMP.text = value;
    }
}
