#if UNITY_EDITOR
using TMPro;
using UnityEditor;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

/// <summary>
/// One-click scene helper: creates a world-space depth overlay HUD and wires
/// DepthOverlayAssist to Pepper top/depth streams.
/// </summary>
public static class PepperDepthOverlaySetup
{
    const string MenuPath = "Tools/Pepper VR/Create Depth Overlay Assist Rig";

    [MenuItem(MenuPath, priority = 20)]
    public static void CreateRig()
    {
        PepperCameraStream top;
        PepperCameraStream depth;
        FindStreams(out top, out depth);

        if (top == null || depth == null)
        {
            EditorUtility.DisplayDialog(
                "Pepper streams not found",
                "Could not find both required PepperCameraStream components.\n\n" +
                "Need:\n- one with WhichCamera = TopForehead\n- one with WhichCamera = DepthGrayscale\n\n" +
                "Add those first, then run this menu again.",
                "OK"
            );
            return;
        }

        EnsureEventSystem();

        GameObject root = new GameObject("PepperDepthOverlayHUD");
        Undo.RegisterCreatedObjectUndo(root, "Create Pepper depth overlay HUD");

        RectTransform rootRect = root.AddComponent<RectTransform>();
        Canvas canvas = root.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.WorldSpace;
        canvas.worldCamera = Camera.main;
        root.AddComponent<CanvasScaler>();
        root.AddComponent<GraphicRaycaster>();

        // Reasonable default world-space size and placement.
        rootRect.sizeDelta = new Vector2(1000, 700);
        Transform cam = Camera.main != null ? Camera.main.transform : null;
        if (cam != null)
        {
            root.transform.SetParent(cam, false);
            root.transform.localPosition = new Vector3(0f, -0.12f, 1.7f);
            root.transform.localRotation = Quaternion.identity;
            root.transform.localScale = new Vector3(0.0022f, 0.0022f, 0.0022f);
        }
        else
        {
            root.transform.position = Vector3.zero;
            root.transform.localScale = new Vector3(0.0022f, 0.0022f, 0.0022f);
        }

        // Composite panel
        GameObject panelGO = CreateUIObject("CompositePanel", root.transform);
        Image panel = panelGO.AddComponent<Image>();
        panel.color = new Color(0f, 0f, 0f, 0.55f);
        RectTransform panelRt = panelGO.GetComponent<RectTransform>();
        panelRt.anchorMin = new Vector2(0.5f, 0.5f);
        panelRt.anchorMax = new Vector2(0.5f, 0.5f);
        panelRt.pivot = new Vector2(0.5f, 0.5f);
        panelRt.anchoredPosition = Vector2.zero;
        panelRt.sizeDelta = new Vector2(920, 600);

        GameObject rawGO = CreateUIObject("CompositeRawImage", panelGO.transform);
        RawImage raw = rawGO.AddComponent<RawImage>();
        RectTransform rawRt = rawGO.GetComponent<RectTransform>();
        rawRt.anchorMin = new Vector2(0.5f, 0.5f);
        rawRt.anchorMax = new Vector2(0.5f, 0.5f);
        rawRt.pivot = new Vector2(0.5f, 0.5f);
        rawRt.anchoredPosition = new Vector2(0, 25);
        rawRt.sizeDelta = new Vector2(860, 500);
        raw.color = Color.white;

        // Indicators
        Image left = CreateIndicator("LeftIndicator", panelGO.transform, new Vector2(-390, 25));
        Image right = CreateIndicator("RightIndicator", panelGO.transform, new Vector2(390, 25));
        Image center = CreateIndicator("CenterIndicator", panelGO.transform, new Vector2(0, -210));
        center.rectTransform.sizeDelta = new Vector2(170, 30);

        // Status text (TMP)
        GameObject txtGO = CreateUIObject("StatusTMP", panelGO.transform);
        TextMeshProUGUI tmp = txtGO.AddComponent<TextMeshProUGUI>();
        tmp.text = "Depth overlay waiting...";
        tmp.fontSize = 34;
        tmp.alignment = TextAlignmentOptions.Center;
        tmp.color = Color.white;
        RectTransform txtRt = txtGO.GetComponent<RectTransform>();
        txtRt.anchorMin = new Vector2(0.5f, 0f);
        txtRt.anchorMax = new Vector2(0.5f, 0f);
        txtRt.pivot = new Vector2(0.5f, 0f);
        txtRt.anchoredPosition = new Vector2(0, 10);
        txtRt.sizeDelta = new Vector2(860, 85);

        DepthOverlayAssist assist = root.AddComponent<DepthOverlayAssist>();
        assist.rgbStream = top;
        assist.depthStream = depth;
        assist.compositeRawImage = raw;
        assist.leftIndicator = left;
        assist.rightIndicator = right;
        assist.centerIndicator = center;
        assist.statusTextTMP = tmp;

        Selection.activeGameObject = root;
        EditorGUIUtility.PingObject(root);
        Debug.Log("[Pepper VR] Created Depth Overlay Assist rig and auto-wired top/depth streams.");
    }

    static void FindStreams(out PepperCameraStream top, out PepperCameraStream depth)
    {
        top = null;
        depth = null;
        PepperCameraStream[] all = Object.FindObjectsByType<PepperCameraStream>(
            FindObjectsInactive.Include, FindObjectsSortMode.None);
        foreach (PepperCameraStream s in all)
        {
            if (s == null) continue;
            if (s.whichCamera == PepperCameraStream.WhichCamera.TopForehead && top == null)
                top = s;
            else if (s.whichCamera == PepperCameraStream.WhichCamera.DepthGrayscale && depth == null)
                depth = s;
        }
    }

    static void EnsureEventSystem()
    {
        if (Object.FindFirstObjectByType<EventSystem>(FindObjectsInactive.Include) != null)
            return;
        GameObject es = new GameObject("EventSystem");
        Undo.RegisterCreatedObjectUndo(es, "Create EventSystem");
        es.AddComponent<EventSystem>();
        es.AddComponent<StandaloneInputModule>();
    }

    static GameObject CreateUIObject(string name, Transform parent)
    {
        GameObject go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent, false);
        return go;
    }

    static Image CreateIndicator(string name, Transform parent, Vector2 anchoredPos)
    {
        GameObject go = CreateUIObject(name, parent);
        Image img = go.AddComponent<Image>();
        img.color = new Color(1f, 1f, 1f, 0.18f);
        RectTransform rt = img.rectTransform;
        rt.anchorMin = new Vector2(0.5f, 0.5f);
        rt.anchorMax = new Vector2(0.5f, 0.5f);
        rt.pivot = new Vector2(0.5f, 0.5f);
        rt.anchoredPosition = anchoredPos;
        rt.sizeDelta = new Vector2(80, 260);
        return img;
    }
}
#endif
