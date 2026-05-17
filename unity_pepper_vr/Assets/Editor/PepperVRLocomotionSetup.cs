#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

/// <summary>
/// One-click scene helper: adds VRLocomotionSender to the scene and
/// auto-detects the server URL from existing PepperCameraStream components.
/// </summary>
public static class PepperVRLocomotionSetup
{
    const string MenuPath = "Tools/Pepper VR/Add VR Locomotion Sender";

    [MenuItem(MenuPath, priority = 30)]
    public static void AddVRLocomotion()
    {
        VRLocomotionSender existing = Object.FindFirstObjectByType<VRLocomotionSender>(FindObjectsInactive.Include);
        if (existing != null)
        {
            Selection.activeGameObject = existing.gameObject;
            EditorGUIUtility.PingObject(existing.gameObject);
            EditorUtility.DisplayDialog(
                "Already exists",
                "VRLocomotionSender already exists on: " + existing.gameObject.name,
                "OK");
            return;
        }

        string baseUrl = "http://192.168.1.123:8080";
        PepperCameraStream[] streams = Object.FindObjectsByType<PepperCameraStream>(
            FindObjectsInactive.Include, FindObjectsSortMode.None);
        foreach (PepperCameraStream s in streams)
        {
            if (s != null && !string.IsNullOrWhiteSpace(s.streamBase))
            {
                baseUrl = s.streamBase.Trim().TrimEnd('/');
                break;
            }
        }

        GameObject go = new GameObject("PepperVRLocomotion");
        Undo.RegisterCreatedObjectUndo(go, "Add VR Locomotion Sender");
        VRLocomotionSender sender = go.AddComponent<VRLocomotionSender>();
        sender.serverBase = baseUrl;

        Selection.activeGameObject = go;
        EditorGUIUtility.PingObject(go);
        Debug.Log("[Pepper VR] Created VRLocomotionSender with server: " + baseUrl +
                  "  -- Enable VR Drive in the Python GUI before testing.");
    }

    [MenuItem(MenuPath, true)]
    static bool Validate() { return !Application.isPlaying; }
}
#endif
