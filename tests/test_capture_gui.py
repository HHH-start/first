"""Exercise the real Qt widgets and BMP writer with only the MVS boundary mocked."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QImage
except ImportError:
    QApplication = None


class FakeCamera:
    def __init__(self, failure=False):
        self.failure = failure
        self.frame_count = 0
        self.st_frame_info = types.SimpleNamespace(nFrameLen=1)
        self.buf_lock = threading.Lock()

    def trigger_once(self):
        if self.failure:
            return 1
        self.frame_count += 1
        return 0

    def save_bmp(self, path, expected_frame_count):
        image = QImage(12, 10, QImage.Format_RGB32)
        image.fill(0xff336699)
        return 0 if image.save(path, 'BMP') else 1


@unittest.skipIf(QApplication is None, 'PyQt5 is required for GUI tests')
class CaptureGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        stubs = {}
        for name in ('MvCameraControl_class', 'CamOperation_OneClick', 'CameraParams_header'):
            stubs[name] = types.ModuleType(name)
        stubs['CamOperation_OneClick'].CameraOperation = object
        stubs['CameraParams_header'].MV_CC_DEVICE_INFO_LIST = object
        stubs['CameraParams_header'].MV_CC_DEVICE_INFO = object
        spec = importlib.util.spec_from_file_location('studio_under_test', Path(__file__).resolve().parents[1] / 'TripleCamStudio.py')
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', stubs):
            spec.loader.exec_module(cls.module)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / 'config.json'
        config = json.loads((Path(__file__).resolve().parents[1] / 'config.example.json').read_text())
        for i, camera in enumerate(config['cameras']):
            camera['roi'] = [1, 2, 5, 4]
            camera['save_dir'] = str(self.root / str(i))
        config['save_metadata'] = True
        self.config.write_text(json.dumps(config))
        self.addCleanup(patch.stopall)
        patch.object(self.module, 'CONFIG', self.config).start()
        self.warnings = patch.object(self.module.QMessageBox, 'warning').start()
        self.callbacks = []
        patch.object(self.module.QTimer, 'singleShot', side_effect=lambda delay, fn: self.callbacks.append(fn)).start()
        self.window = self.module.Studio()
        self.addCleanup(self.window.deleteLater)
        self.window.ready = True
        self.window.cams = [FakeCamera() for _ in range(3)]

    def capture(self):
        self.window.capture_once()
        while self.callbacks:
            self.callbacks.pop(0)()
        self.assertFalse(self.window.busy)
        self.assertTrue(all(p.isEnabled() for p in self.window.save_paths))

    def test_real_bmp_save_roi_and_directory_memory(self):
        custom = self.root / 'chosen-left'
        self.window.save_paths[0].setText(str(custom))
        self.window.save_paths[0].editingFinished.emit()
        restored = self.module.Studio()
        self.addCleanup(restored.deleteLater)
        self.assertEqual(restored.save_paths[0].text(), str(custom))
        self.capture()
        for i, role in enumerate(('left', 'mid', 'right')):
            directory = Path(self.window.save_paths[i].text())
            output = directory / f'pic_1_{role}.bmp'
            image = QImage(str(output))
            self.assertEqual((image.width(), image.height()), (5, 4))
            self.assertFalse(any(p.is_dir() for p in directory.iterdir()))
        metadata = json.loads((custom / 'pic_1_capture.json').read_text())
        self.assertEqual(metadata['batch'], 1)
        self.assertEqual(metadata['cameras'][2]['file'], str(self.root / '2' / 'pic_1_right.bmp'))
        (self.root / '2' / 'pic_10_right.bmp').write_bytes(b'old')
        self.capture()
        self.assertTrue((custom / 'pic_11_left.bmp').exists())
        self.assertFalse(self.warnings.called)

    def test_partial_failure_retains_success_and_batch_number(self):
        self.window.cams[1].failure = True
        self.capture()
        self.assertTrue((self.root / '0' / 'pic_1_left.bmp').exists())
        self.assertFalse((self.root / '1' / 'pic_1_mid.bmp').exists())
        self.assertTrue((self.root / '2' / 'pic_1_right.bmp').exists())
        self.window.cams[1].failure = False
        self.capture()
        self.assertTrue((self.root / '1' / 'pic_2_mid.bmp').exists())
        self.assertEqual(self.warnings.call_count, 1)

    def test_invalid_destination_does_not_trigger(self):
        file = self.root / 'file'
        file.touch()
        self.window.save_paths[1].setText(str(file))
        self.window.capture_once()
        self.assertEqual([c.frame_count for c in self.window.cams], [0, 0, 0])
        self.assertFalse(self.window.busy)
        self.warnings.assert_called_once()

    def test_metadata_failure_does_not_lock_ui_or_lose_photos(self):
        directory = self.root / '0'
        directory.mkdir()
        (directory / 'pic_1_capture.json').write_text('keep this')
        self.capture()
        self.assertEqual((directory / 'pic_1_capture.json').read_text(), 'keep this')
        self.assertTrue((directory / 'pic_1_left.bmp').exists())
        self.assertTrue(self.window.capture.isEnabled())
