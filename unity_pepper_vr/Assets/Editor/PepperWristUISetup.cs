#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.XR;
using TMPro;

/// <summary>
/// Creates a left-wrist World Space canvas (pixel layout + 0.001 scale) with
/// TextMeshPro buttons wired to VRGuiBridge for Python GUI remote control.
/// Menu: Tools / Pepper VR / Create Left Wrist Control UI
/// </summary>
public static class PepperWristUISetup
{
    const string MenuPath = "Tools/Pepper VR/Create Left Wrist Control UI";

    [MenuItem(MenuPath, priority = 35)]
    public static void CreateLeftWristUI()
    {
        Transform left = FindLeftController();
        if (left == null)
        {
            EditorUtility.DisplayDialog(
                "Left controller not found",
                "Could not find a transform named like \"Left Controller\", \"LeftController\", or containing \"Left\" + \"Controller\".\n\n" +
                "Create or rename your XR left hand object, then run this again.",
                "OK");
            return;
        }

        string baseUrl = "http://192.168.1.123:8080";
#pragma warning disable CS0618
        PepperCameraStream[] streams = Object.FindObjectsOfType<PepperCameraStream>(true);
#pragma warning restore CS0618
        foreach (PepperCameraStream s in streams)
        {
            if (s != null && !string.IsNullOrWhiteSpace(s.streamBase))
            {
                baseUrl = s.streamBase.Trim().TrimEnd('/');
                break;
            }
        }

#pragma warning disable CS0618
        VRGuiBridge existingBridge = Object.FindObjectOfType<VRGuiBridge>(true);
        VRLocomotionSender locomotion = Object.FindObjectOfType<VRLocomotionSender>(true);
#pragma warning restore CS0618
        if (existingBridge != null && !string.IsNullOrWhiteSpace(existingBridge.serverBase))
            baseUrl = existingBridge.serverBase.Trim().TrimEnd('/');

        GameObject wristRoot = new GameObject("PepperWristUI_Left");
        Undo.RegisterCreatedObjectUndo(wristRoot, "Create Left Wrist UI");
        wristRoot.transform.SetParent(left, false);
        wristRoot.transform.localPosition = new Vector3(0.05f, 0.02f, 0.04f);
        wristRoot.transform.localRotation = Quaternion.Euler(75f, 0f, -10f);
        wristRoot.transform.localScale = Vector3.one;

        GameObject scaleRoot = new GameObject("CanvasScale_0p001");
        Undo.RegisterCreatedObjectUndo(scaleRoot, "Canvas scale");
        scaleRoot.transform.SetParent(wristRoot.transform, false);
        scaleRoot.transform.localPosition = Vector3.zero;
        scaleRoot.transform.localRotation = Quaternion.identity;
        scaleRoot.transform.localScale = new Vector3(0.001f, 0.001f, 0.001f);

        GameObject canvasGo = new GameObject("WristCanvas");
        Undo.RegisterCreatedObjectUndo(canvasGo, "Wrist canvas");
        canvasGo.transform.SetParent(scaleRoot.transform, false);
        canvasGo.transform.localPosition = Vector3.zero;
        canvasGo.transform.localRotation = Quaternion.identity;
        canvasGo.transform.localScale = Vector3.one;

        Canvas canvas = canvasGo.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.WorldSpace;

        const float canvasW = 900f;
        const float canvasH = 720f;

        RectTransform crt = canvasGo.GetComponent<RectTransform>();
        crt.anchorMin = crt.anchorMax = new Vector2(0.5f, 0.5f);
        crt.pivot = new Vector2(0.5f, 0.5f);
        crt.sizeDelta = new Vector2(canvasW, canvasH);
        crt.anchoredPosition = Vector2.zero;

        CanvasScaler scaler = canvasGo.AddComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(canvasW, canvasH);
        scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
        scaler.matchWidthOrHeight = 0.5f;

        canvasGo.AddComponent<GraphicRaycaster>();

        System.Type xriRay = System.Type.GetType(
            "UnityEngine.XR.Interaction.Toolkit.UI.TrackedDeviceGraphicRaycaster, Unity.XR.Interaction.Toolkit");
        if (xriRay != null)
            canvasGo.AddComponent(xriRay);

        VRGuiBridge bridge = canvasGo.AddComponent<VRGuiBridge>();
        bridge.serverBase = baseUrl;
        bridge.pollStatus = true;
        bridge.pollEverySeconds = 1f;

        GameObject panel = new GameObject("Panel");
        Undo.RegisterCreatedObjectUndo(panel, "Wrist panel");
        panel.transform.SetParent(canvasGo.transform, false);
        RectTransform prt = panel.AddComponent<RectTransform>();
        prt.anchorMin = Vector2.zero;
        prt.anchorMax = Vector2.one;
        prt.offsetMin = Vector2.zero;
        prt.offsetMax = Vector2.zero;

        Image bg = panel.AddComponent<Image>();
        bg.color = new Color(0.06f, 0.07f, 0.1f, 0.96f);

        VerticalLayoutGroup vlg = panel.AddComponent<VerticalLayoutGroup>();
        vlg.padding = new RectOffset(18, 18, 16, 14);
        vlg.spacing = 8;
        vlg.childAlignment = TextAnchor.UpperCenter;
        vlg.childControlWidth = true;
        vlg.childControlHeight = true;
        vlg.childForceExpandWidth = true;
        vlg.childForceExpandHeight = false;

        GameObject titleGo = new GameObject("Title");
        titleGo.transform.SetParent(panel.transform, false);
        TextMeshProUGUI titleTmp = titleGo.AddComponent<TextMeshProUGUI>();
        titleTmp.text = "Pepper GUI";
        titleTmp.fontSize = 24;
        titleTmp.alignment = TextAlignmentOptions.Center;
        titleTmp.color = new Color(0.92f, 0.94f, 0.97f, 1f);
        LayoutElement titleLe = titleGo.AddComponent<LayoutElement>();
        titleLe.minHeight = 32f;
        titleLe.flexibleHeight = 0f;

        CreateTmpButton(panel.transform, bridge, WristButtonRelay.Action.ToggleVRDrive, "VR Drive");
        CreateTmpButton(panel.transform, bridge, WristButtonRelay.Action.ToggleArmMirror, "Arm Mirror");
        CreateTmpButton(panel.transform, bridge, WristButtonRelay.Action.ToggleBodyDrive, "Body Drive");
        CreateTmpButton(panel.transform, bridge, WristButtonRelay.Action.ToggleKeyboardTeleop, "Keyboard teleop");
        CreateTmpButton(panel.transform, bridge, WristButtonRelay.Action.StopAllDrive, "Stop all drive");

        CreateSpacer(panel.transform, 6f);

        CreateSectionLabel(panel.transform, "VR locomotion");

        CreateLocomotionButton(panel.transform, locomotion, WristLocomotionRelay.Action.CycleLocomotionMode, "Switch mode · Thumbstick ↔ Walk");
        CreateLocomotionButton(panel.transform, locomotion, WristLocomotionRelay.Action.CalibrateWalkNeutral, "Calibrate walk (standing)");

        GameObject gridGo = new GameObject("LocoToggleGrid");
        Undo.RegisterCreatedObjectUndo(gridGo, "Locomotion toggles");
        gridGo.transform.SetParent(panel.transform, false);
        GridLayoutGroup grid = gridGo.AddComponent<GridLayoutGroup>();
        float innerW = canvasW - vlg.padding.left - vlg.padding.right;
        float colW = (innerW - 10f) * 0.5f;
        grid.cellSize = new Vector2(colW, 44f);
        grid.spacing = new Vector2(10f, 8f);
        grid.constraint = GridLayoutGroup.Constraint.FixedColumnCount;
        grid.constraintCount = 2;
        grid.startCorner = GridLayoutGroup.Corner.UpperLeft;
        grid.startAxis = GridLayoutGroup.Axis.Horizontal;
        grid.childAlignment = TextAnchor.UpperCenter;
        LayoutElement gridLe = gridGo.AddComponent<LayoutElement>();
        gridLe.minHeight = 3f * 44f + 2f * 8f + 4f;
        gridLe.flexibleHeight = 0f;
        gridLe.flexibleWidth = 1f;

        CreateLocomotionToggle(gridGo.transform, locomotion, WristLocomotionToggleRelay.Field.LockPepperHead, "Lock Pepper head");
        CreateLocomotionToggle(gridGo.transform, locomotion, WristLocomotionToggleRelay.Field.HeadRelativeMovement, "Head-relative move");
        CreateLocomotionToggle(gridGo.transform, locomotion, WristLocomotionToggleRelay.Field.WalkRoomScale, "Walk room-scale");
        CreateLocomotionToggle(gridGo.transform, locomotion, WristLocomotionToggleRelay.Field.WalkHeadYawTurn, "Walk head-yaw turn");
        CreateLocomotionToggle(gridGo.transform, locomotion, WristLocomotionToggleRelay.Field.KeyboardFallback, "Keyboard fallback");
        CreateLocomotionToggle(gridGo.transform, locomotion, WristLocomotionToggleRelay.Field.DisableRigLocomotionProviders, "Disable XR rig move");

        GameObject footerGo = new GameObject("Footer");
        Undo.RegisterCreatedObjectUndo(footerGo, "Wrist footer");
        footerGo.transform.SetParent(panel.transform, false);
        VerticalLayoutGroup fvlg = footerGo.AddComponent<VerticalLayoutGroup>();
        fvlg.spacing = 6;
        fvlg.childAlignment = TextAnchor.UpperLeft;
        fvlg.childControlWidth = true;
        fvlg.childControlHeight = true;
        fvlg.childForceExpandWidth = true;
        fvlg.childForceExpandHeight = false;
        fvlg.padding = new RectOffset(0, 0, 10, 0);
        LayoutElement fle = footerGo.AddComponent<LayoutElement>();
        fle.minHeight = 112f;
        fle.flexibleHeight = 0f;

        GameObject vrHudGo = new GameObject("VRLocomotionHud");
        vrHudGo.transform.SetParent(footerGo.transform, false);
        TextMeshProUGUI vrHudTmp = vrHudGo.AddComponent<TextMeshProUGUI>();
        vrHudTmp.fontSize = 14;
        vrHudTmp.alignment = TextAlignmentOptions.TopLeft;
        vrHudTmp.color = new Color(0.55f, 0.82f, 0.78f, 1f);
        vrHudTmp.enableWordWrapping = true;
        vrHudTmp.text = "Mode: —";
        LayoutElement vrHudLe = vrHudGo.AddComponent<LayoutElement>();
        vrHudLe.minHeight = 48f;
        vrHudLe.flexibleHeight = 0f;
        WristLocomotionHud locoHud = canvasGo.AddComponent<WristLocomotionHud>();
        locoHud.locomotion = locomotion;
        locoHud.label = vrHudTmp;

        GameObject statusGo = new GameObject("Status");
        statusGo.transform.SetParent(footerGo.transform, false);
        Text statusTxt = statusGo.AddComponent<Text>();
        Font uiFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        if (uiFont == null)
            uiFont = Resources.GetBuiltinResource<Font>("Arial.ttf");
        statusTxt.font = uiFont;
        statusTxt.fontSize = 13;
        statusTxt.color = new Color(0.7f, 0.76f, 0.84f, 1f);
        statusTxt.alignment = TextAnchor.UpperLeft;
        statusTxt.horizontalOverflow = HorizontalWrapMode.Wrap;
        statusTxt.verticalOverflow = VerticalWrapMode.Overflow;
        statusTxt.text = "Python: (connect Pepper GUI)";
        LayoutElement sle = statusGo.AddComponent<LayoutElement>();
        sle.minHeight = 48f;
        sle.flexibleHeight = 0f;
        bridge.statusLabel = statusTxt;

        PepperWristUIToggle wristToggle = wristRoot.AddComponent<PepperWristUIToggle>();
        wristToggle.contentRoot = scaleRoot;
        wristToggle.xrHand = XRNode.LeftHand;
        wristToggle.toggleButton = PepperWristUIToggle.ToggleButton.Secondary;

        Selection.activeGameObject = wristRoot;
        EditorGUIUtility.PingObject(wristRoot);
        if (locomotion == null)
            Debug.LogWarning("[Pepper VR] No VRLocomotionSender in scene — VR buttons will find one at runtime if you add it.");
        Debug.Log("[Pepper VR] Left wrist UI created under '" + left.name + "'. serverBase=" + baseUrl);
    }

    static void CreateSectionLabel(Transform parent, string text)
    {
        GameObject go = new GameObject("Section_" + text.Replace(" ", "").Replace("(", "").Replace(")", ""));
        Undo.RegisterCreatedObjectUndo(go, "Section " + text);
        go.transform.SetParent(parent, false);
        TextMeshProUGUI tmp = go.AddComponent<TextMeshProUGUI>();
        tmp.text = text;
        tmp.fontSize = 18;
        tmp.fontStyle = FontStyles.Bold;
        tmp.alignment = TextAlignmentOptions.Left;
        tmp.color = new Color(0.72f, 0.78f, 0.86f, 1f);
        LayoutElement le = go.AddComponent<LayoutElement>();
        le.minHeight = 26f;
        le.flexibleHeight = 0f;
    }

    static void CreateSpacer(Transform parent, float height)
    {
        GameObject s = new GameObject("Spacer");
        Undo.RegisterCreatedObjectUndo(s, "Spacer");
        s.transform.SetParent(parent, false);
        LayoutElement le = s.AddComponent<LayoutElement>();
        le.minHeight = height;
        le.flexibleHeight = 0f;
    }

    static void CreateLocomotionToggle(Transform parent, VRLocomotionSender locomotion, WristLocomotionToggleRelay.Field field, string label)
    {
        GameObject row = new GameObject("Tgl_" + label.Replace(" ", "").Replace("·", ""));
        Undo.RegisterCreatedObjectUndo(row, "Toggle " + label);
        row.transform.SetParent(parent, false);

        Image rowBg = row.AddComponent<Image>();
        rowBg.color = new Color(0.12f, 0.14f, 0.18f, 0.95f);
        Toggle t = row.AddComponent<Toggle>();
        t.transition = Selectable.Transition.ColorTint;
        ColorBlock cb = t.colors;
        cb.normalColor = rowBg.color;
        cb.highlightedColor = new Color(0.16f, 0.19f, 0.24f, 1f);
        cb.pressedColor = new Color(0.2f, 0.24f, 0.3f, 1f);
        cb.selectedColor = Color.white;
        cb.disabledColor = new Color(0.4f, 0.4f, 0.4f, 0.5f);
        cb.colorMultiplier = 1f;
        cb.fadeDuration = 0.08f;
        t.colors = cb;
        t.targetGraphic = rowBg;

        GameObject checkGo = new GameObject("Checkmark");
        checkGo.transform.SetParent(row.transform, false);
        Image chk = checkGo.AddComponent<Image>();
        chk.color = new Color(0.35f, 0.85f, 0.62f, 1f);
        t.graphic = chk;
        RectTransform chkRt = chk.rectTransform;
        chkRt.anchorMin = new Vector2(0f, 0.5f);
        chkRt.anchorMax = new Vector2(0f, 0.5f);
        chkRt.pivot = new Vector2(0.5f, 0.5f);
        chkRt.anchoredPosition = new Vector2(18f, 0f);
        chkRt.sizeDelta = new Vector2(22f, 22f);

        GameObject labelGo = new GameObject("Label");
        labelGo.transform.SetParent(row.transform, false);
        TextMeshProUGUI tmp = labelGo.AddComponent<TextMeshProUGUI>();
        tmp.text = label;
        tmp.fontSize = 16;
        tmp.alignment = TextAlignmentOptions.MidlineLeft;
        tmp.color = new Color(0.93f, 0.94f, 0.96f, 1f);
        tmp.overflowMode = TextOverflowModes.Ellipsis;
        RectTransform labRt = tmp.rectTransform;
        labRt.anchorMin = Vector2.zero;
        labRt.anchorMax = Vector2.one;
        labRt.offsetMin = new Vector2(44f, 4f);
        labRt.offsetMax = new Vector2(-8f, -4f);

        WristLocomotionToggleRelay relay = row.AddComponent<WristLocomotionToggleRelay>();
        relay.locomotion = locomotion;
        relay.field = field;
    }

    static void CreateLocomotionButton(Transform parent, VRLocomotionSender locomotion, WristLocomotionRelay.Action action, string label)
    {
        GameObject go = new GameObject("LocoBtn_" + label.Replace(" ", "").Replace(":", "").Replace("/", ""));
        Undo.RegisterCreatedObjectUndo(go, "Loco " + label);
        go.transform.SetParent(parent, false);

        LayoutElement le = go.AddComponent<LayoutElement>();
        le.minHeight = 42f;
        le.flexibleWidth = 1f;

        Image img = go.AddComponent<Image>();
        img.color = new Color(0.14f, 0.42f, 0.38f, 1f);

        Button btn = go.AddComponent<Button>();
        ColorBlock colors = btn.colors;
        colors.highlightedColor = new Color(0.2f, 0.52f, 0.46f, 1f);
        colors.pressedColor = new Color(0.1f, 0.32f, 0.28f, 1f);
        btn.colors = colors;

        GameObject textGo = new GameObject("Text");
        textGo.transform.SetParent(go.transform, false);
        TextMeshProUGUI tmp = textGo.AddComponent<TextMeshProUGUI>();
        tmp.text = label;
        tmp.fontSize = 18;
        tmp.alignment = TextAlignmentOptions.Center;
        tmp.color = Color.white;

        RectTransform trt = textGo.GetComponent<RectTransform>();
        trt.anchorMin = Vector2.zero;
        trt.anchorMax = Vector2.one;
        trt.offsetMin = Vector2.zero;
        trt.offsetMax = Vector2.zero;

        WristLocomotionRelay relay = go.AddComponent<WristLocomotionRelay>();
        relay.locomotion = locomotion;
        relay.action = action;
    }

    static void CreateTmpButton(Transform parent, VRGuiBridge bridge, WristButtonRelay.Action action, string label)
    {
        GameObject go = new GameObject("Btn_" + label.Replace(" ", ""));
        Undo.RegisterCreatedObjectUndo(go, "Button " + label);
        go.transform.SetParent(parent, false);

        LayoutElement le = go.AddComponent<LayoutElement>();
        le.minHeight = 42f;
        le.flexibleWidth = 1f;

        Image img = go.AddComponent<Image>();
        img.color = new Color(0.22f, 0.4f, 0.72f, 1f);

        Button btn = go.AddComponent<Button>();
        ColorBlock colors = btn.colors;
        colors.highlightedColor = new Color(0.32f, 0.5f, 0.88f, 1f);
        colors.pressedColor = new Color(0.14f, 0.28f, 0.58f, 1f);
        btn.colors = colors;

        GameObject textGo = new GameObject("Text");
        textGo.transform.SetParent(go.transform, false);
        TextMeshProUGUI tmp = textGo.AddComponent<TextMeshProUGUI>();
        tmp.text = label;
        tmp.fontSize = 18;
        tmp.alignment = TextAlignmentOptions.Center;
        tmp.color = Color.white;

        RectTransform trt = textGo.GetComponent<RectTransform>();
        trt.anchorMin = Vector2.zero;
        trt.anchorMax = Vector2.one;
        trt.offsetMin = Vector2.zero;
        trt.offsetMax = Vector2.zero;

        WristButtonRelay relay = go.AddComponent<WristButtonRelay>();
        relay.bridge = bridge;
        relay.action = action;
    }

    static Transform FindLeftController()
    {
        string[] exact = { "Left Controller", "LeftController", "Left Hand", "LeftHand" };
        foreach (string n in exact)
        {
            GameObject go = GameObject.Find(n);
            if (go != null)
                return go.transform;
        }

#pragma warning disable CS0618
        foreach (Transform t in Object.FindObjectsOfType<Transform>(true))
#pragma warning restore CS0618
        {
            string name = t.name;
            if (name.IndexOf("left", System.StringComparison.OrdinalIgnoreCase) < 0)
                continue;
            if (name.IndexOf("controller", System.StringComparison.OrdinalIgnoreCase) >= 0 ||
                name.IndexOf("hand", System.StringComparison.OrdinalIgnoreCase) >= 0)
                return t;
        }

        return null;
    }

    [MenuItem(MenuPath, true)]
    static bool Validate()
    {
        return !Application.isPlaying;
    }
}
#endif
