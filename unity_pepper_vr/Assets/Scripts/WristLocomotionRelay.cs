using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Wires wrist UI buttons to <see cref="VRLocomotionSender"/> (Unity-side VR settings).
/// </summary>
[DisallowMultipleComponent]
[RequireComponent(typeof(Button))]
public class WristLocomotionRelay : MonoBehaviour
{
    public enum Action
    {
        CycleLocomotionMode,
        CalibrateWalkNeutral,
        ToggleLockPepperHead,
        ToggleHeadRelativeMovement,
        ToggleWalkRoomScale,
        ToggleWalkHeadYawTurn,
        ToggleKeyboardFallback,
        ToggleDisableRigLocomotionProviders
    }

    public VRLocomotionSender locomotion;
    public Action action;

    void Awake()
    {
        if (locomotion == null)
        {
#pragma warning disable CS0618
            locomotion = Object.FindObjectOfType<VRLocomotionSender>(true);
#pragma warning restore CS0618
        }

        var btn = GetComponent<Button>();
        if (locomotion == null || btn == null)
            return;
        btn.onClick.AddListener(OnClick);
    }

    void OnClick()
    {
        if (locomotion == null)
            return;
        switch (action)
        {
            case Action.CycleLocomotionMode: locomotion.CycleLocomotionMode(); break;
            case Action.CalibrateWalkNeutral: locomotion.CalibrateWalkNeutral(); break;
            case Action.ToggleLockPepperHead: locomotion.ToggleLockPepperHead(); break;
            case Action.ToggleHeadRelativeMovement: locomotion.ToggleHeadRelativeMovement(); break;
            case Action.ToggleWalkRoomScale: locomotion.ToggleWalkRoomScale(); break;
            case Action.ToggleWalkHeadYawTurn: locomotion.ToggleWalkHeadYawTurn(); break;
            case Action.ToggleKeyboardFallback: locomotion.ToggleKeyboardFallback(); break;
            case Action.ToggleDisableRigLocomotionProviders: locomotion.ToggleDisableRigLocomotionProviders(); break;
        }
    }
}
