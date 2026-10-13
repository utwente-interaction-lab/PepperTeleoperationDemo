Pepper Teleoperation — USB handoff checklist
============================================

Goal: move this project to another Windows PC with as little friction as possible.
This app cannot run with "folder only / zero installs" — the other PC still needs
Choregraphe, Miniconda, and Python 3.10 once.

--------------------------------------------------------------------
1) PUT ON THE USB STICK
--------------------------------------------------------------------

A. This project folder (recommended name on stick: PepperTeleoperationDemo)

   INCLUDE:
   - Start_Pepper_Azure.bat
   - setup.bat
   - requirements_gui.txt
   - requirements_tracker.txt
   - requirements_azure.txt          (only if using Azure Kinect)
   - pepper_teleoperation\           (GUI)
   - openpose_wrap\                  (tracker)
   - docs\                           (optional but useful)
   - README.md
   - this file (README_USB.txt)

   SKIP / DELETE BEFORE COPY (saves space, avoids clutter):
   - .git\                           (optional; only needed if you want git history)
   - __pycache__\                    (everywhere)
   - *.pyc
   - logs\
   - openpose_wrap\keypoints_data\   (if large / not needed)
   - openpose_wrap\video_data\       (if large / not needed)
   - pepper_teleoperation\angles_data\  (if large / not needed)
   - unity_pepper_vr\ and *.unitypackage  (only needed for VR)

B. Installers (put in a folder on the stick, e.g. _installers\)

   REQUIRED:
   1. Choregraphe Suite 2.5.x for Windows
      (from SoftBank Robotics Community — you must download this yourself)
   2. Miniconda3 Windows 64-bit installer
      https://docs.conda.io/en/latest/miniconda.html
   3. Python 3.10 Windows installer
      https://www.python.org/downloads/release/python-31011/
      During install: check "Add python.exe to PATH"

   OPTIONAL:
   - Azure Kinect SDK / requirements only if using Kinect instead of webcam

--------------------------------------------------------------------
2) ON THE OTHER PC (do once)
--------------------------------------------------------------------

1. Install Choregraphe Suite 2.5
   Default path expected by the launcher:
   C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\

2. Install Miniconda3 (64-bit is fine)

3. Install Python 3.10
   Prefer the "py" launcher / Add to PATH option

4. Copy the project OFF the USB onto local disk, e.g.:
   C:\PepperTeleoperationDemo\
   (Do not run day-to-day from the USB stick.)

5. Open that folder and double-click:
   setup.bat

   This creates the pepper27_32 conda env and installs GUI + tracker packages.

6. Double-click:
   Start_Pepper_Azure.bat

--------------------------------------------------------------------
3) QUICK CHECKS IF SOMETHING FAILS
--------------------------------------------------------------------

- Pepper and PC on the same Wi-Fi/LAN; Pepper IP set in the GUI
- Webcam works (MediaPipe path)
- If Choregraphe is not in the default path, edit the top of Start_Pepper_Azure.bat:
    CHORE_LIB  and  CHORE_BIN
- Logs are written under:
    logs\azure_tracker.log
    logs\pepper_gui.log

--------------------------------------------------------------------
4) MINIMAL "OTHER PERSON" INSTRUCTIONS (copy/paste)
--------------------------------------------------------------------

1. Install Choregraphe 2.5, Miniconda, and Python 3.10 from the _installers folder.
2. Copy PepperTeleoperationDemo to C:\PepperTeleoperationDemo
3. Run setup.bat once.
4. Run Start_Pepper_Azure.bat
5. Set Pepper's IP in the GUI and connect.
