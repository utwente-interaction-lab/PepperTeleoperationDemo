# NAO Dance Study — operator guide

Behind-the-scenes (Wizard-of-Oz) control for the Group 10 study: NAO leads a
simple head / shoulders / knees / toes exercise, the participant (or a
confederate) deliberately gets it wrong, and NAO responds in one of four ways.

| Scenario | What NAO does when the struggle trigger fires |
|---|---|
| **A – Continue** | Nothing changes; keeps dancing at the same tempo |
| **B – Slow down** | Keeps dancing, every move takes *slow-down factor* × longer (default 1.6×) |
| **C – Stop & wait** | Finishes the current move, returns to neutral, looks at the participant and waits. Press **Resume** when the participant restarts. |
| **D – Stop & check in** | Same as C, but asks *"Are you okay? How are you doing?"*. Press **Resume** after they answer; NAO says *"Okay, let's continue together!"* |

NAO speaks **English**: the panel switches NAO's speech language to English
when it connects and again before each take (lab robots are often set to
Dutch). To change it, edit `ROBOT_LANGUAGE` in `utils/nao_dance.py`.

After C or D, NAO restarts the round it stopped in (can be switched off).
Every take is identical up to the trigger, so the response is the only thing
that differs between the four videos.

## Starting the panel

* **Browser control panel (default):** double-click `Start_NAO_Study.bat`
  (or `Start_NAO_Study.bat --ip 192.168.1.70 --connect`). The panel opens on
  the **NAO Study** tab. Connect to NAO in the **Teleoperation** tab, then pick
  **Live NAO** in the study tab. `Start_Pepper_Azure.bat` opens the same panel
  with the body tracker running too.
  On NAO, the panel disables Body Drive, keyboard / VR driving, the tablet and the
  Pepper ask-demos, because on a legged robot those commands would make NAO
  walk. Arm Mirror still works.
* **Rehearsal without a robot:** keep **Simulation** selected. Timing, the
  event log and the CSV output are the same as with the robot, so you can
  practise with the confederate.
* **Old Tk windows:** `pepper_gui.py` → **Open NAO Study Panel**, or set
  `STUDY_SCRIPT=nao_study_gui.py` in `Start_NAO_Study.bat`.

The large **Participant struggles** / **Resume** panel stays pinned at the top
while you scroll. In the **Choreography** grid, click any move to set the
auto-trigger point.

## Running a take

1. Enter the participant / take ID and pick scenario A–D.
2. Press **Start take**. NAO stands up, says the intro, and starts the rounds.
3. The struggle trigger fires either
   * automatically at the configured round / move (default: round 3, move 3 =
     the first "knees"), which keeps takes repeatable, or
   * by hand with **Participant struggles NOW** or the **Space** key (untick
     *Auto trigger* to rely on this only).
   NAO reacts at the next move boundary (within one beat).
4. For C / D, press **Resume** (key **R**) when the participant restarts / has answered.
5. **Stop** (key **Esc**) halts NAO immediately where it is. Use **Stand up** or
   **Sit down + rest** afterwards.

Hotkeys are ignored while the cursor is in a text field. **Esc** is "Stop all" in the browser panel: it stops the take and every other mode.

## Logs

Each take writes `study_logs/<date>_<time>_<take>_<scenario>.csv` with
millisecond wall-clock time plus seconds since take start for every event
(`move`, `struggle_trigger`, `intervention`, `waiting_for_resume`, `resumed`,
`said`, …). Start the camera first, then use these to line up the video.
Simulation takes get a `_SIM` suffix.

## Tuning the dance

The poses and the round live at the top of
`pepper_teleoperation/utils/nao_dance.py` (`MOVES`, `ROUND`). They have been
checked on Choregraphe's virtual NAO, **but not yet on the real robot**. NAO's
arms are too short to really touch its head or toes, so the poses only *indicate*
each body part.

To refine a pose on the real NAO:

1. **Stand up**, then **Relax arms (pose by hand)**. The arms and head go limp,
   and the legs stay stiff.
2. Hold NAO's arms in the pose you want and press **Capture pose**. A ready-made
   `MOVES` line is printed in the log and copied to the clipboard.
3. Paste it into `MOVES`, rename it, then **Stiffen arms** and check it with the
   preview dropdown + **Go**.

Change the knee / toe squat depth (`legs`) in small steps. Keep
`HipPitch + KneePitch + AnklePitch ≈ -0.1` so the torso stays upright.

## Safety

* NAO squats on every "knees" / "toes" move. Run the first takes on the floor
  with someone within reach, and start with a longer *Seconds per move* (e.g. 2.0).
* NAO's fall manager stays enabled. **Sit down + rest** is the safe way to
  park the robot between sessions.
* Don't run Arm Mirror during a take: the panel stops it automatically when
  started from the main GUI.

## Testing with the virtual robot

Choregraphe ships `naoqi-bin.exe`, which can run a virtual NAO:

```bat
cd "C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\bin"
naoqi-bin.exe --qi-listen-url tcp://127.0.0.1:9600 --robot-model "..\share\alrobotmodel\models\NAOH25V50.xml"
```

Then connect the panel to `127.0.0.1`, port `9600`. Or open Choregraphe,
connect to its virtual robot and use the port it shows, which lets you see the
poses in 3D.
