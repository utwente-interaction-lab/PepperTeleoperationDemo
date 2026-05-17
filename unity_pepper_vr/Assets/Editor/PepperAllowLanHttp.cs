#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

/// <summary>
/// Unity 2022.2+ blocks plain http:// in UnityWebRequest unless Player Settings allow it.
/// Use the menu item once per project (or set it manually in Player Settings).
/// </summary>
public static class PepperAllowLanHttp
{
    const string MenuPath = "Tools/Pepper VR/Allow HTTP for LAN camera streams";

    [MenuItem(MenuPath, priority = 10)]
    public static void AllowHttp()
    {
#if UNITY_2022_2_OR_NEWER
        if (PlayerSettings.insecureHttpOption != InsecureHttpOption.AlwaysAllowed)
        {
            PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
            Debug.Log("[Pepper VR] Set Player Settings: Allow downloads over HTTP -> Always Allowed. " +
                      "If quads were white, press Play again.");
        }
        else
            Debug.Log("[Pepper VR] HTTP downloads are already allowed for all builds.");
#else
        Debug.LogWarning("[Pepper VR] This Unity version is older than 2022.2. " +
            "If UnityWebRequest fails on http://, check Edit -> Project Settings -> Player -> Other Settings " +
            "for an HTTP / insecure downloads option, or upgrade Unity.");
#endif
    }
}
#endif
