using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Binds a UI <see cref="Toggle"/> to bool fields on <see cref="VRLocomotionSender"/>.
/// </summary>
[DisallowMultipleComponent]
[RequireComponent(typeof(Toggle))]
public class WristLocomotionToggleRelay : MonoBehaviour
{
    public enum Field
    {
        LockPepperHead,
        HeadRelativeMovement,
        WalkRoomScale,
        WalkHeadYawTurn,
        KeyboardFallback,
        DisableRigLocomotionProviders
    }

    public VRLocomotionSender locomotion;
    public Field field;

    Toggle _toggle;

    void Awake()
    {
        _toggle = GetComponent<Toggle>();
        if (locomotion == null)
        {
#pragma warning disable CS0618
            locomotion = Object.FindObjectOfType<VRLocomotionSender>(true);
#pragma warning restore CS0618
        }
    }

    void Start()
    {
        if (_toggle == null || locomotion == null)
            return;
        _toggle.SetIsOnWithoutNotify(ReadValue());
        _toggle.onValueChanged.AddListener(OnValueChanged);
    }

    bool ReadValue()
    {
        switch (field)
        {
            case Field.LockPepperHead: return locomotion.lockPepperHead;
            case Field.HeadRelativeMovement: return locomotion.headRelativeMovement;
            case Field.WalkRoomScale: return locomotion.walkUseRoomScaleTranslation;
            case Field.WalkHeadYawTurn: return locomotion.walkUseHeadYawTurn;
            case Field.KeyboardFallback: return locomotion.keyboardFallback;
            case Field.DisableRigLocomotionProviders: return locomotion.disableRigLocomotionProviders;
            default: return false;
        }
    }

    void OnValueChanged(bool value)
    {
        if (locomotion == null)
            return;
        switch (field)
        {
            case Field.LockPepperHead: locomotion.SetLockPepperHead(value); break;
            case Field.HeadRelativeMovement: locomotion.SetHeadRelativeMovement(value); break;
            case Field.WalkRoomScale: locomotion.SetWalkRoomScale(value); break;
            case Field.WalkHeadYawTurn: locomotion.SetWalkHeadYawTurn(value); break;
            case Field.KeyboardFallback: locomotion.SetKeyboardFallback(value); break;
            case Field.DisableRigLocomotionProviders: locomotion.SetDisableRigLocomotionProviders(value); break;
        }
    }
}
