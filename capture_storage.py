"""Camera output paths and batch numbering, independent of Qt and the MVS SDK."""
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

CAMERA_ROLES = ('left', 'mid', 'right')
PHOTO_NAME = re.compile(r'pic_([0-9]+)(?:_(B[A-Za-z0-9_]+))?_(left|mid|right)\.bmp', re.IGNORECASE)
REGISTRY_NAME = '.triplecam_batches.json'


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
        batch_id = self._batch_id_for(roots)
        batch = CaptureBatch(number, roots, batch_id)
        self._last_numbers[key] = number
        return batch

    @staticmethod
    def _batch_id_for(roots):
        """Keep one unique ID for a selected directory triplet across restarts."""
        registry_path = roots[0] / REGISTRY_NAME
        current = [os.path.normcase(str(root)) for root in roots]
        if registry_path.exists():
            registry = json.loads(registry_path.read_text(encoding='utf-8'))
            if registry.get('version') != 1 or not isinstance(registry.get('batches'), list):
                raise ValueError('采集批次记录格式无效: ' + str(registry_path))
        else:
            registry = {'version': 1, 'batches': []}
        for record in registry['batches']:
            if record.get('directories') == current:
                return record['batch_id']

        # If previously renamed photos are already present in all three roots,
        # continue their unique ID rather than creating a second one.
        existing = []
        for root in roots:
            existing.append({match.group(2) for path in root.iterdir()
                             if path.is_file() and (match := PHOTO_NAME.fullmatch(path.name))
                             and match.group(2)})
        common = set.intersection(*existing)
        used = {record['batch_id'] for record in registry['batches']}
        batch_id = next(iter(common)) if len(common) == 1 and not (common & used) else None
        if batch_id is None:
            all_existing = set.union(*existing)
            while True:
                batch_id = 'B' + datetime.now().strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:12].upper()
                if batch_id not in used and batch_id not in all_existing:
                    break
        registry['batches'].append({'directories': current, 'batch_id': batch_id})
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', prefix='.triplecam-batches-',
                                         suffix='.tmp', dir=roots[0], delete=False) as stream:
            temp_path = Path(stream.name)
            json.dump(registry, stream, ensure_ascii=False, indent=2)
        try:
            os.replace(temp_path, registry_path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
        return batch_id


class CaptureBatch:
    def __init__(self, number, roots, batch_id):
        self.number = number
        self.roots = roots
        self.batch_id = batch_id
        self.file_stem = f'pic_{number}_{batch_id}'
        self.outputs = [root / f'{self.file_stem}_{role}.bmp'
                        for root, role in zip(roots, CAMERA_ROLES)]
        self.metadata_path = roots[0] / f'{self.file_stem}_capture.json'
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
