using TMPro;
using UnityEngine;

/// <summary>
/// Shows a one-line summary of <see cref="VRLocomotionSender"/> settings on the wrist panel.
/// </summary>
public class WristLocomotionHud : MonoBehaviour
{
    public VRLocomotionSender locomotion;
    public TextMeshProUGUI label;

    [Tooltip("Seconds between label refreshes (0 = every frame).")]
    [Range(0f, 2f)] public float refreshInterval = 0.2f;

    float _acc;

    void Awake()
    {
        if (locomotion == null)
        {
#pragma warning disable CS0618
            locomotion = Object.FindObjectOfType<VRLocomotionSender>(true);
#pragma warning restore CS0618
        }
    }

    void Update()
    {
        if (locomotion == null || label == null)
            return;
        if (refreshInterval > 0f)
        {
            _acc += Time.unscaledDeltaTime;
            if (_acc < refreshInterval)
                return;
            _acc = 0f;
        }

        label.text = string.Format(
            System.Globalization.CultureInfo.InvariantCulture,
            "Mode: {0}\nlock {1} · move {2} · room {3} · yaw {4} · keys {5} · rig {6}",
            locomotion.locomotionMode,
            locomotion.lockPepperHead ? "on" : "off",
            locomotion.headRelativeMovement ? "on" : "off",
            locomotion.walkUseRoomScaleTranslation ? "on" : "off",
            locomotion.walkUseHeadYawTurn ? "on" : "off",
            locomotion.keyboardFallback ? "on" : "off",
            locomotion.disableRigLocomotionProviders ? "on" : "off");
    }
}
