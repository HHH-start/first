TripleCam Studio V2.0 beta (Windows / Hikrobot MVS)
===================================================
This is a development preview. Not yet factory-qualified.

INSTALL
1. Keep the working MVS installation and its Python SDK environment.
2. Copy TripleCamStudio.py, CamOperation_OneClick.py, capture_storage.py and config.json to:
   D:\MVS\Development\Samples\Python\AreaScanCamera\MultipleCameras\
3. Keep the official SDK imports (MvCameraControl_class.py,
   CameraParams_header.py, MvErrorDefine_const.py) accessible as before.
4. Open CMD in that directory and run:
   python TripleCamStudio.py

USAGE
1. Click One-click Configure (一键配置) to open 3 cameras in preview mode.
2. Change individual exposure and click Apply Exposure.
3. Click Edit ROI to select the rectangle on a snapshot of the live image.
4. Click End Preview / Ready for Capture to enter software-trigger mode.
5. Select a fixed folder for each camera (left/mid/right), then click One-click Capture.
   Files share a batch number: pic_1_left.bmp, pic_1_mid.bmp, pic_1_right.bmp.
   The next number is the largest photo number across all three folders plus one.
6. If a camera fails, successful images remain in that folder.

CONFIG
- config.json is loaded at startup and saved after UI parameter changes.
- Per-camera save_dir is remembered; see README.md for migration and numbering.
- save_metadata: false (default), true to write pic_<number>_capture.json in the left camera folder.
- frame_timeout_ms, pre_trigger_delay_ms are editable.
- Each camera serial must match the physical camera serial number.
- Paths used for native SDK intermediate BMP files MUST be ASCII-only.
- ROI values are original image pixels: [x, y, width, height].
- Editing ROI requires preview mode; there is no password, as requested.

IMPORTANT LIMITATIONS
- NOT tested against physical cameras in this environment.
- ROI uses full-frame acquisition and software crop (not sensor AOI).
- The camera commands are issued sequentially, not hardware synchronized.
- The editor uses a fresh snapshot of the current preview frame.
- No automated recovery for cable unplug/network loss yet.
- Configure / SDK calls are on UI thread and may temporarily block UI.
- SDK conversion via QImage BMP loading must be tested with actual pixel format.
- No EXE package yet. Test with your existing working Python/MVS setup first.
