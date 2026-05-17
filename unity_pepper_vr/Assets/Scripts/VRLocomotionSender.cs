using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.XR;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
using XRInputDevice = UnityEngine.XR.InputDevice;
#else
using XRInputDevice = UnityEngine.XR.InputDevice;
#endif

/// <summary>
/// Reads VR controller thumbsticks and headset orientation, then sends
/// movement commands to the Pepper teleop server via HTTP POST.
///
/// Left stick  → translate (forward/back + strafe)
/// Right stick → rotate (yaw)
/// Head yaw/pitch are sent so the Python side can optionally drive Pepper's head.
///
/// Attach to any active GameObject in the XR rig scene.
/// </summary>
public class VRLocomotionSender : MonoBehaviour
{
    public enum LocomotionMode
    {
        Thumbstick = 0,
        WalkInPlace = 1
    }

    [Header("Server")]
    [Tooltip("Teleop PC base URL (same as PepperCameraStream.streamBase).")]
    public string serverBase = "http://192.168.1.123:8080";

    [Header("Mode")]
    [Tooltip("Thumbstick = current behavior. WalkInPlace = natural walking-in-place.")]
    public LocomotionMode locomotionMode = LocomotionMode.Thumbstick;

    [Header("Speed")]
    [Tooltip("Max forward/back speed sent to Pepper (0-1 range for moveToward).")]
    [Range(0.05f, 1f)] public float maxTranslateSpeed = 0.55f;

    [Tooltip("Max strafe speed.")]
    [Range(0.05f, 1f)] public float maxStrafeSpeed = 0.40f;

    [Tooltip("Max rotation speed.")]
    [Range(0.05f, 1f)] public float maxRotateSpeed = 0.50f;

    [Header("Input")]
    [Tooltip("Thumbstick deadzone.")]
    [Range(0.01f, 0.4f)] public float deadzone = 0.12f;

    [Tooltip("Send rate in Hz (how many HTTP POSTs per second).")]
    [Range(5f, 30f)] public float sendRateHz = 12f;

    [Tooltip("Use head orientation to steer movement direction (left stick forward = head-forward).")]
    public bool headRelativeMovement = true;

    [Header("Walk In Place")]
    [Tooltip("Follow room-scale HMD translation (walk around your VR space).")]
    public bool walkUseRoomScaleTranslation = true;

    [Tooltip("Sensitivity for room-scale translation -> Pepper speed.")]
    [Range(0.1f, 6f)] public float roomScaleSensitivity = 2.0f;

    [Tooltip("Turn Pepper from headset yaw changes while in walk mode.")]
    public bool walkUseHeadYawTurn = true;

    [Tooltip("Gain for yaw-change-based turning.")]
    [Range(0.1f, 8f)] public float headYawTurnGain = 1.8f;

    [Tooltip("Fallback: allow right-stick turn in walk mode.")]
    public bool walkUseRightStickTurn = true;

    [Tooltip("Minimum vertical bob speed to count as stepping.")]
    [Range(0.02f, 0.6f)] public float stepVelocityThreshold = 0.08f;

    [Tooltip("How quickly walk speed ramps up/down.")]
    [Range(0.5f, 12f)] public float walkSpeedSmoothing = 4f;

    [Tooltip("How long no step evidence is tolerated before stopping.")]
    [Range(0.1f, 1.5f)] public float walkStopTimeout = 0.45f;

    [Tooltip("Sensitivity multiplier for walk-in-place speed.")]
    [Range(0.2f, 3f)] public float walkSensitivity = 1.15f;

    [Tooltip("Press this key to calibrate neutral headset height while standing still.")]
    public KeyCode calibrateWalkKey = KeyCode.C;

    [Header("Keyboard Fallback (non-VR testing)")]
    [Tooltip("Enable IJKL+UO keyboard input when no VR controllers detected.")]
    public bool keyboardFallback = true;

    [Header("Pepper Head")]
    [Tooltip("Keep Pepper head neutral while driving (prevents autonomous drift).")]
    public bool lockPepperHead = true;

    [Header("XR Rig Coexistence")]
    [Tooltip("Disable XR rig move/turn providers so thumbsticks only drive Pepper.")]
    public bool disableRigLocomotionProviders = true;

    [Header("Status")]
    [Tooltip("Read-only: last server response or error.")]
    [TextArea(1, 2)] public string lastStatus = "";

    bool _sending;
    float _sendTimer;
    float _lastX, _lastY, _lastTheta;
    float _headYaw, _headPitch;
    bool _vrControllersDetected;
    int _consecutiveErrors;
    XRInputDevice _leftHand;
    XRInputDevice _rightHand;
    XRInputDevice _headDevice;
    float _lastHmdY;
    float _hmdYVelFiltered;
    float _lastStepAt;
    float _walkSpeedSmoothed;
    float _walkStrafeSmoothed;
    float _neutralHeadY;
    bool _hasNeutralHeadY;
    bool _prevVerticalGoingUp;
    Vector3 _lastHeadPos;
    bool _hasLastHeadPos;
    float _lastHeadYawDeg;
    bool _hasLastHeadYaw;
    readonly List<Behaviour> _disabledRigProviders = new List<Behaviour>();

#if ENABLE_INPUT_SYSTEM
    InputAction _leftStickAction;
    InputAction _rightStickAction;
#endif

    void Start()
    {
        if (disableRigLocomotionProviders)
            DisableRigLocomotionProviders();
        RefreshDevices();
        TryInitializeHeadCalibration();
        StartCoroutine(DeviceRefreshLoop());
#if ENABLE_INPUT_SYSTEM
        SetupInputSystemActions();
#endif
    }

    void OnDestroy()
    {
        RestoreRigLocomotionProviders();
#if ENABLE_INPUT_SYSTEM
        _leftStickAction?.Disable();
        _rightStickAction?.Disable();
        _leftStickAction?.Dispose();
        _rightStickAction?.Dispose();
        _leftStickAction = null;
        _rightStickAction = null;
#endif
    }

#if ENABLE_INPUT_SYSTEM
    void SetupInputSystemActions()
    {
        _leftStickAction = new InputAction(
            "PepperVR_LeftStick",
            type: InputActionType.Value,
            binding: "<XRController>{LeftHand}/thumbstick",
            expectedControlType: "Vector2");
        _leftStickAction.AddBinding("<XRController>{LeftHand}/{Primary2DAxis}");
        _leftStickAction.AddBinding("<Gamepad>/leftStick");
        _leftStickAction.Enable();

        _rightStickAction = new InputAction(
            "PepperVR_RightStick",
            type: InputActionType.Value,
            binding: "<XRController>{RightHand}/thumbstick",
            expectedControlType: "Vector2");
        _rightStickAction.AddBinding("<XRController>{RightHand}/{Primary2DAxis}");
        _rightStickAction.AddBinding("<Gamepad>/rightStick");
        _rightStickAction.Enable();
    }
#endif

    IEnumerator DeviceRefreshLoop()
    {
        var wait = new WaitForSeconds(3f);
        while (true)
        {
            yield return wait;
            RefreshDevices();
        }
    }

    void RefreshDevices()
    {
        _leftHand = InputDevices.GetDeviceAtXRNode(XRNode.LeftHand);
        _rightHand = InputDevices.GetDeviceAtXRNode(XRNode.RightHand);
        _headDevice = InputDevices.GetDeviceAtXRNode(XRNode.Head);
#if ENABLE_INPUT_SYSTEM
        bool inputSysHasStick =
            (_leftStickAction != null && _leftStickAction.controls.Count > 0) ||
            (_rightStickAction != null && _rightStickAction.controls.Count > 0);
        _vrControllersDetected = _leftHand.isValid || _rightHand.isValid || inputSysHasStick;
#else
        _vrControllersDetected = _leftHand.isValid || _rightHand.isValid;
#endif
    }

    Vector2 ReadLeftStick()
    {
        Vector2 v = Vector2.zero;
#if ENABLE_INPUT_SYSTEM
        if (_leftStickAction != null && _leftStickAction.controls.Count > 0)
            v = _leftStickAction.ReadValue<Vector2>();
#endif
        if (v.sqrMagnitude < 0.0001f && _leftHand.isValid)
            _leftHand.TryGetFeatureValue(UnityEngine.XR.CommonUsages.primary2DAxis, out v);
        return v;
    }

    Vector2 ReadRightStick()
    {
        Vector2 v = Vector2.zero;
#if ENABLE_INPUT_SYSTEM
        if (_rightStickAction != null && _rightStickAction.controls.Count > 0)
            v = _rightStickAction.ReadValue<Vector2>();
#endif
        if (v.sqrMagnitude < 0.0001f && _rightHand.isValid)
            _rightHand.TryGetFeatureValue(UnityEngine.XR.CommonUsages.primary2DAxis, out v);
        return v;
    }

    void Update()
    {
        if (IsKeyPressedThisFrame(calibrateWalkKey))
            CalibrateWalkNeutral();

        ReadInput(out float x, out float y, out float theta);
        ReadHeadOrientation(out float headYaw, out float headPitch);
        if (lockPepperHead)
        {
            headYaw = 0f;
            headPitch = -6f;
        }

        if (headRelativeMovement && locomotionMode != LocomotionMode.WalkInPlace &&
            (Mathf.Abs(x) > 0.001f || Mathf.Abs(y) > 0.001f))
        {
            float rad = headYaw * Mathf.Deg2Rad;
            float cosA = Mathf.Cos(rad);
            float sinA = Mathf.Sin(rad);
            float rx = x * cosA - y * sinA;
            float ry = x * sinA + y * cosA;
            x = rx;
            y = ry;
        }

        _lastX = x;
        _lastY = y;
        _lastTheta = theta;
        _headYaw = headYaw;
        _headPitch = headPitch;

        _sendTimer += Time.unscaledDeltaTime;
        float period = 1f / Mathf.Max(1f, sendRateHz);
        if (_sendTimer >= period && !_sending)
        {
            _sendTimer = 0f;
            StartCoroutine(SendCommand(_lastX, _lastY, _lastTheta, _headYaw, _headPitch));
        }

        Vector2 debugL = ReadLeftStick();
        Vector2 debugR = ReadRightStick();
        lastStatus = string.Format(
            System.Globalization.CultureInfo.InvariantCulture,
            "stickL=({0:F2},{1:F2}) stickR=({2:F2},{3:F2}) cmd x={4:F2} y={5:F2} th={6:F2}",
            debugL.x, debugL.y, debugR.x, debugR.y, x, y, theta);
    }

    void ReadInput(out float x, out float y, out float theta)
    {
        if (locomotionMode == LocomotionMode.WalkInPlace)
        {
            ReadWalkInPlaceInput(out x, out y, out theta);
            return;
        }

        x = 0f;
        y = 0f;
        theta = 0f;

        Vector2 leftStick = ReadLeftStick();
        Vector2 rightStick = ReadRightStick();

        // Thumbsticks (zero if controllers inactive)
        x = ApplyDeadzone(leftStick.y) * maxTranslateSpeed;
        y = ApplyDeadzone(leftStick.x) * maxStrafeSpeed;
        theta = -ApplyDeadzone(rightStick.x) * maxRotateSpeed;

        // Keyboard ALWAYS contributes (additive). This keeps WASD/IJKL reliable
        // even when OpenXR intermittently reports a controller as "connected"
        // while the user is actually at the desk. Keys override zero-stick axes.
        if (keyboardFallback)
        {
            float kx = 0f, ky = 0f, kth = 0f;
            if (IsKeyHeld(KeyCode.I) || IsKeyHeld(KeyCode.W)) kx += maxTranslateSpeed;
            if (IsKeyHeld(KeyCode.K) || IsKeyHeld(KeyCode.S)) kx -= maxTranslateSpeed;
            if (IsKeyHeld(KeyCode.J) || IsKeyHeld(KeyCode.A)) ky += maxStrafeSpeed;
            if (IsKeyHeld(KeyCode.L) || IsKeyHeld(KeyCode.D)) ky -= maxStrafeSpeed;
            if (IsKeyHeld(KeyCode.U) || IsKeyHeld(KeyCode.Q)) kth += maxRotateSpeed;
            if (IsKeyHeld(KeyCode.O) || IsKeyHeld(KeyCode.E)) kth -= maxRotateSpeed;

            if (Mathf.Abs(kx) > 0.001f) x = kx;
            if (Mathf.Abs(ky) > 0.001f) y = ky;
            if (Mathf.Abs(kth) > 0.001f) theta = kth;
        }
    }

    void ReadWalkInPlaceInput(out float x, out float y, out float theta)
    {
        x = 0f;
        y = 0f;
        theta = 0f;

        float dt = Mathf.Max(Time.unscaledDeltaTime, 0.0001f);
        Vector3 hmdPos = ReadHeadLocalPosition();
        if (!_hasLastHeadPos)
        {
            _lastHeadPos = hmdPos;
            _hasLastHeadPos = true;
        }
        Vector3 d = hmdPos - _lastHeadPos;
        _lastHeadPos = hmdPos;

        if (walkUseRoomScaleTranslation)
        {
            float tx = Mathf.Clamp((d.z / dt) * roomScaleSensitivity, -maxTranslateSpeed, maxTranslateSpeed);
            float ty = Mathf.Clamp((d.x / dt) * roomScaleSensitivity, -maxStrafeSpeed, maxStrafeSpeed);
            float speedAlpha = 1f - Mathf.Exp(-walkSpeedSmoothing * dt);
            _walkSpeedSmoothed = Mathf.Lerp(_walkSpeedSmoothed, tx, speedAlpha);
            _walkStrafeSmoothed = Mathf.Lerp(_walkStrafeSmoothed, ty, speedAlpha);
            x = Mathf.Abs(_walkSpeedSmoothed) < deadzone * 0.25f ? 0f : _walkSpeedSmoothed;
            y = Mathf.Abs(_walkStrafeSmoothed) < deadzone * 0.25f ? 0f : _walkStrafeSmoothed;
        }

        if (walkUseHeadYawTurn)
        {
            ReadHeadOrientation(out float yawNow, out _);
            if (!_hasLastHeadYaw)
            {
                _lastHeadYawDeg = yawNow;
                _hasLastHeadYaw = true;
            }
            float dYaw = Mathf.DeltaAngle(_lastHeadYawDeg, yawNow);
            _lastHeadYawDeg = yawNow;
            theta = Mathf.Clamp((dYaw / dt) * 0.01f * headYawTurnGain, -maxRotateSpeed, maxRotateSpeed);
        }
        else if (walkUseRightStickTurn)
        {
            Vector2 rightStick = ReadRightStick();
            theta = -ApplyDeadzone(rightStick.x) * maxRotateSpeed;
        }

        if (keyboardFallback)
        {
            if (IsKeyHeld(KeyCode.I) || IsKeyHeld(KeyCode.W)) x = maxTranslateSpeed;
            if (IsKeyHeld(KeyCode.K) || IsKeyHeld(KeyCode.S)) x = 0f;
            if (IsKeyHeld(KeyCode.U) || IsKeyHeld(KeyCode.Q)) theta = maxRotateSpeed;
            if (IsKeyHeld(KeyCode.O) || IsKeyHeld(KeyCode.E)) theta = -maxRotateSpeed;
            if (IsKeyHeld(KeyCode.J) || IsKeyHeld(KeyCode.A)) y = maxStrafeSpeed;
            if (IsKeyHeld(KeyCode.L) || IsKeyHeld(KeyCode.D)) y = -maxStrafeSpeed;
        }

        if (IsKeyHeld(KeyCode.LeftShift))
            x *= 0.5f;
    }

    bool IsKeyHeld(KeyCode key)
    {
#if ENABLE_INPUT_SYSTEM
        if (Keyboard.current == null)
            return false;
        Key k = ToInputSystemKey(key);
        return k != Key.None && Keyboard.current[k].isPressed;
#else
        return Input.GetKey(key);
#endif
    }

    bool IsKeyPressedThisFrame(KeyCode key)
    {
#if ENABLE_INPUT_SYSTEM
        if (Keyboard.current == null)
            return false;
        Key k = ToInputSystemKey(key);
        return k != Key.None && Keyboard.current[k].wasPressedThisFrame;
#else
        return Input.GetKeyDown(key);
#endif
    }

#if ENABLE_INPUT_SYSTEM
    static Key ToInputSystemKey(KeyCode key)
    {
        switch (key)
        {
            case KeyCode.I: return Key.I;
            case KeyCode.K: return Key.K;
            case KeyCode.J: return Key.J;
            case KeyCode.L: return Key.L;
            case KeyCode.U: return Key.U;
            case KeyCode.O: return Key.O;
            case KeyCode.C: return Key.C;
            case KeyCode.LeftShift: return Key.LeftShift;
            default: return Key.None;
        }
    }
#endif

    float ApplyDeadzone(float v)
    {
        if (Mathf.Abs(v) < deadzone) return 0f;
        float sign = Mathf.Sign(v);
        return sign * Mathf.InverseLerp(deadzone, 1f, Mathf.Abs(v));
    }

    void ReadHeadOrientation(out float yaw, out float pitch)
    {
        yaw = 0f;
        pitch = 0f;

        if (_headDevice.isValid)
        {
            if (_headDevice.TryGetFeatureValue(UnityEngine.XR.CommonUsages.deviceRotation, out Quaternion rot))
            {
                Vector3 euler = rot.eulerAngles;
                yaw = euler.y > 180f ? euler.y - 360f : euler.y;
                pitch = euler.x > 180f ? euler.x - 360f : euler.x;
                return;
            }
        }

        if (Camera.main != null)
        {
            Vector3 euler = Camera.main.transform.eulerAngles;
            yaw = euler.y > 180f ? euler.y - 360f : euler.y;
            pitch = euler.x > 180f ? euler.x - 360f : euler.x;
        }
    }

    float ReadHeadLocalY()
    {
        if (_headDevice.isValid)
        {
            if (_headDevice.TryGetFeatureValue(UnityEngine.XR.CommonUsages.devicePosition, out Vector3 pos))
                return pos.y;
        }
        if (Camera.main != null)
            return Camera.main.transform.position.y;
        return 0f;
    }

    Vector3 ReadHeadLocalPosition()
    {
        if (_headDevice.isValid &&
            _headDevice.TryGetFeatureValue(UnityEngine.XR.CommonUsages.devicePosition, out Vector3 pos))
            return pos;
        if (Camera.main != null)
            return Camera.main.transform.localPosition;
        return Vector3.zero;
    }

    void TryInitializeHeadCalibration()
    {
        _neutralHeadY = ReadHeadLocalY();
        _lastHmdY = _neutralHeadY;
        _hasNeutralHeadY = true;
        _lastHeadPos = ReadHeadLocalPosition();
        _hasLastHeadPos = true;
        ReadHeadOrientation(out _lastHeadYawDeg, out _);
        _hasLastHeadYaw = true;
    }

    /// <summary>Call from VR wrist UI or hotkey — resets walk-in-place baseline while standing still.</summary>
    public void CalibrateWalkNeutral()
    {
        _neutralHeadY = ReadHeadLocalY();
        _lastHmdY = _neutralHeadY;
        _walkSpeedSmoothed = 0f;
        _walkStrafeSmoothed = 0f;
        _hmdYVelFiltered = 0f;
        _lastStepAt = 0f;
        _hasNeutralHeadY = true;
        _lastHeadPos = ReadHeadLocalPosition();
        _hasLastHeadPos = true;
        ReadHeadOrientation(out _lastHeadYawDeg, out _);
        _hasLastHeadYaw = true;
        lastStatus = "Calibrated walk neutral";
        Debug.Log("[VRLocomotionSender] Walk neutral calibrated.");
    }

    /// <summary>Thumbstick ↔ Walk-in-place (VR wrist UI).</summary>
    public void CycleLocomotionMode()
    {
        locomotionMode = locomotionMode == LocomotionMode.Thumbstick
            ? LocomotionMode.WalkInPlace
            : LocomotionMode.Thumbstick;
        lastStatus = "Locomotion: " + locomotionMode;
    }

    public void ToggleLockPepperHead()
    {
        lockPepperHead = !lockPepperHead;
        lastStatus = "Lock Pepper head: " + lockPepperHead;
    }

    public void SetLockPepperHead(bool value)
    {
        if (lockPepperHead == value) return;
        lockPepperHead = value;
        lastStatus = "Lock Pepper head: " + lockPepperHead;
    }

    public void ToggleHeadRelativeMovement()
    {
        headRelativeMovement = !headRelativeMovement;
        lastStatus = "Head-relative move: " + headRelativeMovement;
    }

    public void SetHeadRelativeMovement(bool value)
    {
        if (headRelativeMovement == value) return;
        headRelativeMovement = value;
        lastStatus = "Head-relative move: " + headRelativeMovement;
    }

    public void ToggleWalkRoomScale()
    {
        walkUseRoomScaleTranslation = !walkUseRoomScaleTranslation;
        lastStatus = "Walk room-scale: " + walkUseRoomScaleTranslation;
    }

    public void SetWalkRoomScale(bool value)
    {
        if (walkUseRoomScaleTranslation == value) return;
        walkUseRoomScaleTranslation = value;
        lastStatus = "Walk room-scale: " + walkUseRoomScaleTranslation;
    }

    public void ToggleWalkHeadYawTurn()
    {
        walkUseHeadYawTurn = !walkUseHeadYawTurn;
        lastStatus = "Walk head-yaw turn: " + walkUseHeadYawTurn;
    }

    public void SetWalkHeadYawTurn(bool value)
    {
        if (walkUseHeadYawTurn == value) return;
        walkUseHeadYawTurn = value;
        lastStatus = "Walk head-yaw turn: " + walkUseHeadYawTurn;
    }

    public void ToggleKeyboardFallback()
    {
        keyboardFallback = !keyboardFallback;
        lastStatus = "Keyboard fallback: " + keyboardFallback;
    }

    public void SetKeyboardFallback(bool value)
    {
        if (keyboardFallback == value) return;
        keyboardFallback = value;
        lastStatus = "Keyboard fallback: " + keyboardFallback;
    }

    /// <summary>Disable XR rig snap/smooth move so sticks only drive Pepper (runtime toggle).</summary>
    public void ToggleDisableRigLocomotionProviders()
    {
        disableRigLocomotionProviders = !disableRigLocomotionProviders;
        if (disableRigLocomotionProviders)
            DisableRigLocomotionProviders();
        else
            RestoreRigLocomotionProviders();
        lastStatus = "Disable rig locomotion: " + disableRigLocomotionProviders;
    }

    /// <summary>Used by wrist UI toggles (absolute on/off).</summary>
    public void SetDisableRigLocomotionProviders(bool value)
    {
        if (disableRigLocomotionProviders == value) return;
        disableRigLocomotionProviders = value;
        if (disableRigLocomotionProviders)
            DisableRigLocomotionProviders();
        else
            RestoreRigLocomotionProviders();
        lastStatus = "Disable rig locomotion: " + disableRigLocomotionProviders;
    }

    IEnumerator SendCommand(float x, float y, float theta, float headYaw, float headPitch)
    {
        _sending = true;

        string url = string.Format(
            System.Globalization.CultureInfo.InvariantCulture,
            "{0}/vr_move?x={1:F3}&y={2:F3}&theta={3:F3}&head_yaw={4:F1}&head_pitch={5:F1}",
            serverBase.TrimEnd('/'),
            x, y, theta, headYaw, headPitch);

        using (UnityWebRequest req = UnityWebRequest.Get(url))
        {
            req.timeout = 2;
            yield return req.SendWebRequest();

#if UNITY_2020_2_OR_NEWER
            bool ok = req.result == UnityWebRequest.Result.Success;
#else
            bool ok = !req.isNetworkError && !req.isHttpError;
#endif
            if (ok)
            {
                _consecutiveErrors = 0;
            }
            else
            {
                _consecutiveErrors++;
                if (_consecutiveErrors <= 3 || _consecutiveErrors % 30 == 0)
                {
                    string err = req.error ?? "unknown";
                    lastStatus = "NET ERR: " + err;
                    Debug.LogWarning("[VRLocomotionSender] " + err + " -> " + url);
                }
            }
        }

        _sending = false;
    }

    void OnDisable()
    {
        RestoreRigLocomotionProviders();
        StartCoroutine(SendCommand(0f, 0f, 0f, 0f, 0f));
    }

    void DisableRigLocomotionProviders()
    {
        _disabledRigProviders.Clear();
        var all = FindObjectsOfType<MonoBehaviour>(true);
        for (int i = 0; i < all.Length; i++)
        {
            var mb = all[i];
            if (mb == null || mb == this || !mb.gameObject.scene.IsValid())
                continue;
            string tn = mb.GetType().Name;
            if (tn.IndexOf("MoveProvider", StringComparison.OrdinalIgnoreCase) >= 0 ||
                tn.IndexOf("TurnProvider", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                var b = mb as Behaviour;
                if (b != null && b.enabled)
                {
                    b.enabled = false;
                    _disabledRigProviders.Add(b);
                }
            }
        }
    }

    void RestoreRigLocomotionProviders()
    {
        for (int i = 0; i < _disabledRigProviders.Count; i++)
        {
            var b = _disabledRigProviders[i];
            if (b != null) b.enabled = true;
        }
        _disabledRigProviders.Clear();
    }
}
