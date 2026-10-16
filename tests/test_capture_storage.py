import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from capture_storage import CaptureStorage, camera_directories


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.roots = [Path(self.temp.name) / role for role in ('left', 'mid', 'right')]
        self.storage = CaptureStorage()

    def prepare(self):
        batch = self.storage.prepare(self.roots)
        self.addCleanup(batch.close)
        return batch

    def test_empty_directories_start_at_one(self):
        batch = self.prepare()
        self.assertEqual(batch.number, 1)
        self.assertEqual([p.name for p in batch.outputs],
                         ['pic_1_left.bmp', 'pic_1_mid.bmp', 'pic_1_right.bmp'])

    def test_maximum_across_directories_and_restart(self):
        self.prepare().close()
        (self.roots[0] / 'pic_1_left.bmp').touch()
        restarted = CaptureStorage().prepare(self.roots)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.number, 2)
        (self.roots[1] / 'pic_10_mid.bmp').touch()
        (self.roots[2] / 'PIC_7_RIGHT.BMP').touch()
        (self.roots[0] / 'unrelated_999.bmp').touch()
        (self.roots[0] / 'pic_999_left.bmp').mkdir()
        batch = CaptureStorage().prepare(self.roots)
        self.addCleanup(batch.close)
        self.assertEqual(batch.number, 11)

    def test_partial_capture_keeps_batch_and_advances(self):
        batch = self.prepare()
        source = batch.temp_dir / 'image.bmp'
        source.write_bytes(b'finished BMP')
        batch.publish(0, source)
        batch.publish(2, source)
        batch.close()
        following = CaptureStorage().prepare(self.roots)
        self.addCleanup(following.close)
        self.assertEqual(following.number, 2)
        self.assertTrue((self.roots[0] / 'pic_1_left.bmp').exists())
        self.assertFalse((self.roots[1] / 'pic_1_mid.bmp').exists())

    def test_all_failed_attempt_still_advances_in_session(self):
        self.prepare().close()
        self.assertEqual(self.prepare().number, 2)

    def test_existing_file_never_overwritten(self):
        batch = self.prepare()
        source = batch.temp_dir / 'image.bmp'
        source.write_bytes(b'new')
        batch.outputs[0].write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            batch.publish(0, source)
        self.assertEqual(batch.outputs[0].read_bytes(), b'original')

    def test_failed_write_removes_partial_output(self):
        batch = self.prepare()
        source = batch.temp_dir / 'image.bmp'
        source.write_bytes(b'new')
        def fail_copy(source_file, output):
            output.write(b'partial')
            raise OSError('disk full')
        with patch('capture_storage.shutil.copyfileobj', side_effect=fail_copy):
            with self.assertRaises(OSError):
                batch.publish(0, source)
        self.assertFalse(batch.outputs[0].exists())

    def test_shared_folder_and_folder_switch(self):
        first = self.storage.prepare([self.roots[0]] * 3)
        self.addCleanup(first.close)
        self.assertEqual(len(set(first.outputs)), 3)
        self.assertEqual(self.prepare().number, 1)

    def test_invalid_path_stops_before_capture(self):
        with self.assertRaises(ValueError):
            self.storage.prepare(['', *self.roots[1:]])
        file = Path(self.temp.name) / 'not-a-directory'
        file.touch()
        with self.assertRaises(OSError):
            self.storage.prepare([file, *self.roots[1:]])

    def test_old_config_defaults_preserve_camera_parameters(self):
        config = {'save_root': 'D:/Old', 'cameras': [{'serial': str(i)} for i in range(3)]}
        self.assertEqual([Path(p).name for p in camera_directories(config)], ['left', 'mid', 'right'])
        self.assertEqual(config['cameras'][0], {'serial': '0'})
        config['cameras'][1]['save_dir'] = 'D:/Custom'
        self.assertEqual(camera_directories(config)[1], 'D:/Custom')
