"""Camera output paths and batch numbering, independent of Qt and the MVS SDK."""
import os
import re
import shutil
import tempfile
from pathlib import Path

CAMERA_ROLES = ('left', 'mid', 'right')
PHOTO_NAME = re.compile(r'pic_([0-9]+)_(?:left|mid|right)\.bmp', re.IGNORECASE)


def camera_directories(config):
    """Migrate old configurations in memory without touching camera parameters."""
    root = config.get('save_root', 'D:/CameraCaptures')
    return [entry.get('save_dir') or str(Path(root) / role)
            for entry, role in zip(config['cameras'], CAMERA_ROLES)]


class CaptureStorage:
    def __init__(self):
        self._last_numbers = {}

    def prepare(self, directories):
        if len(directories) != 3:
            raise ValueError('必须为三台相机设置保存目录')
        roots = []
        for directory in directories:
            if not str(directory).strip():
                raise ValueError('保存目录不能为空')
            root = Path(directory).expanduser().resolve()
            # The native MVS BMP writer requires ASCII-only paths.
            str(root).encode('ascii')
            root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=root):
                pass
            roots.append(root)
        maximum = 0
        for root in set(roots):
            for path in root.iterdir():
                match = PHOTO_NAME.fullmatch(path.name)
                if match and path.is_file():
                    maximum = max(maximum, int(match[1]))
        key = tuple(os.path.normcase(str(root)) for root in roots)
        number = max(maximum, self._last_numbers.get(key, 0)) + 1
        batch = CaptureBatch(number, roots)
        self._last_numbers[key] = number
        return batch


class CaptureBatch:
    def __init__(self, number, roots):
        self.number = number
        self.roots = roots
        self.outputs = [root / f'pic_{number}_{role}.bmp'
                        for root, role in zip(roots, CAMERA_ROLES)]
        self._temporary = tempfile.TemporaryDirectory(prefix='.triplecam-', dir=roots[0])
        self.temp_dir = Path(self._temporary.name)

    def publish(self, slot, source):
        """Copy a finished BMP without overwriting any existing photograph."""
        target = self.outputs[slot]
        with open(source, 'rb') as image:
            output = open(target, 'xb')
            try:
                with output:
                    shutil.copyfileobj(image, output)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
        return str(target)

    def close(self):
        self._temporary.cleanup()
