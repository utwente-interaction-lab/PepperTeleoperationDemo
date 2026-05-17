using UnityEngine;
using UnityEngine.XR;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

/// <summary>
/// Shows/hides the wrist panel with a Meta Quest controller button (default: left Y).
/// Put this on the parent object that stays active (e.g. <c>PepperWristUI_Left</c>);
/// assign <see cref="contentRoot"/> to the child that holds the canvas (e.g. <c>CanvasScale_0p001</c>)
/// so disabling does not stop this script.
/// </summary>
[DisallowMultipleComponent]
public class PepperWristUIToggle : MonoBehaviour
{
    [Tooltip("Child to enable/disable (e.g. CanvasScale_0p001). Leave empty to use first child named CanvasScale_0p001.")]
    public GameObject contentRoot;

    [Tooltip("Visible when the scene starts.")]
    public bool startVisible = true;

    [Header("Controller (Meta Quest)")]
    [Tooltip("Which controller reads the toggle button.")]
    public XRNode xrHand = XRNode.LeftHand;

    public enum ToggleButton
    {
        Secondary, // Y (left) / B (right)
        Primary,   // X (left) / A (right)
        Menu       // left menu / right system (varies by runtime)
    }

    [Tooltip("Which face button toggles the panel.")]
    public ToggleButton toggleButton = ToggleButton.Secondary;

    [Header("Keyboard (Editor / desktop)")]
    public bool keyboardFallback = true;
    public KeyCode keyboardKey = KeyCode.T;

#if ENABLE_INPUT_SYSTEM
    InputAction _toggleAction;
#endif
    bool _prevHeld;

    void Awake()
    {
        if (contentRoot == null)
        {
            Transform t = transform.Find("CanvasScale_0p001");
            if (t != null)
                contentRoot = t.gameObject;
            else if (transform.childCount > 0)
                contentRoot = transform.GetChild(0).gameObject;
        }

        if (contentRoot != null)
            contentRoot.SetActive(startVisible);
    }

    void OnEnable()
    {
#if ENABLE_INPUT_SYSTEM
        string hand = xrHand == XRNode.LeftHand ? "LeftHand" : "RightHand";
        string sub = ToggleButtonToControlPath(toggleButton);
        _toggleAction = new InputAction("PepperWristUIToggle", type: InputActionType.Button);
        _toggleAction.AddBinding("<XRController>{" + hand + "}/" + sub);
        _toggleAction.Enable();
#endif
    }

    void OnDisable()
    {
#if ENABLE_INPUT_SYSTEM
        _toggleAction?.Disable();
        _toggleAction?.Dispose();
        _toggleAction = null;
#endif
    }

    void Update()
    {
        if (contentRoot == null)
            return;

#if ENABLE_INPUT_SYSTEM
        if (keyboardFallback && Keyboard.current != null)
        {
            Key k = KeyCodeToKey(keyboardKey);
            if (k != Key.None && Keyboard.current[k].wasPressedThisFrame)
            {
                Flip();
                return;
            }
        }
#else
        if (keyboardFallback && Input.GetKeyDown(keyboardKey))
        {
            Flip();
            return;
        }
#endif

#if ENABLE_INPUT_SYSTEM
        if (_toggleAction != null && _toggleAction.controls.Count > 0)
        {
            if (_toggleAction.WasPressedThisFrame())
                Flip();
            return;
        }
#endif
        // XR legacy API — must qualify: Input System also defines InputDevice/CommonUsages.
        UnityEngine.XR.InputDevice dev = InputDevices.GetDeviceAtXRNode(xrHand);
        if (!dev.isValid)
            return;

        bool held = false;
        switch (toggleButton)
        {
            case ToggleButton.Secondary:
                dev.TryGetFeatureValue(UnityEngine.XR.CommonUsages.secondaryButton, out held);
                break;
            case ToggleButton.Primary:
                dev.TryGetFeatureValue(UnityEngine.XR.CommonUsages.primaryButton, out held);
                break;
            case ToggleButton.Menu:
                dev.TryGetFeatureValue(UnityEngine.XR.CommonUsages.menuButton, out held);
                break;
        }

        if (held && !_prevHeld)
            Flip();
        _prevHeld = held;
    }

    void Flip()
    {
        if (contentRoot != null)
            contentRoot.SetActive(!contentRoot.activeSelf);
    }

#if ENABLE_INPUT_SYSTEM
    static string ToggleButtonToControlPath(ToggleButton b)
    {
        switch (b)
        {
            case ToggleButton.Primary: return "primaryButton";
            case ToggleButton.Menu: return "menuButton";
            default: return "secondaryButton";
        }
    }

    static Key KeyCodeToKey(KeyCode code)
    {
        switch (code)
        {
            case KeyCode.T: return Key.T;
            case KeyCode.Y: return Key.Y;
            case KeyCode.B: return Key.B;
            case KeyCode.M: return Key.M;
            default: return Key.None;
        }
    }
#endif
}
