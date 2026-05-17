using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Wires a UI Button to <see cref="VRGuiBridge"/> at runtime (Awake).
/// Used by the editor menu that builds the wrist panel so we do not depend on
/// UnityEditor.Events.UnityEventTools (API varies by Unity version).
/// </summary>
[DisallowMultipleComponent]
[RequireComponent(typeof(Button))]
public class WristButtonRelay : MonoBehaviour
{
    public enum Action
    {
        ToggleVRDrive,
        ToggleArmMirror,
        ToggleBodyDrive,
        ToggleKeyboardTeleop,
        StopAllDrive
    }

    public VRGuiBridge bridge;
    public Action action;

    void Awake()
    {
        var btn = GetComponent<Button>();
        if (bridge == null || btn == null)
            return;
        btn.onClick.AddListener(OnClick);
    }

    void OnClick()
    {
        if (bridge == null)
            return;
        switch (action)
        {
            case Action.ToggleVRDrive: bridge.ToggleVRDrive(); break;
            case Action.ToggleArmMirror: bridge.ToggleArmMirror(); break;
            case Action.ToggleBodyDrive: bridge.ToggleBodyDrive(); break;
            case Action.ToggleKeyboardTeleop: bridge.ToggleKeyboardTeleop(); break;
            case Action.StopAllDrive: bridge.StopAllDrive(); break;
        }
    }
}
