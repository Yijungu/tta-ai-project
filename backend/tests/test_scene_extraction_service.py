import asyncio
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from fastapi import UploadFile

# Ensure backend package is importable when running tests from repository root.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.scene_extraction import SceneExtractionService  # noqa: E402


def _create_sample_video(tmp_path: Path) -> Path:
    cv2 = pytest.importorskip("cv2")

    height, width = 64, 64
    video_path = tmp_path / "sample.avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(video_path), fourcc, 5.0, (width, height))

    if not writer.isOpened():  # pragma: no cover - environment guard
        pytest.skip("OpenCV VideoWriter is not available in this environment.")

    colors = [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
    ]
    for color in colors:
        frame = np.full((height, width, 3), color, dtype=np.uint8)
        for _ in range(12):
            writer.write(frame)

    writer.release()

    if not video_path.exists():  # pragma: no cover - defensive guard
        pytest.skip("동영상을 생성하지 못했습니다.")

    return video_path


def test_scene_extraction_service_generates_scene_archive(tmp_path: Path) -> None:
    video_path = _create_sample_video(tmp_path)
    service = SceneExtractionService(scene_threshold=0.4, min_scene_length=3)

    upload = UploadFile(filename="demo.avi", file=io.BytesIO(video_path.read_bytes()))
    result = asyncio.run(service.extract_from_upload(upload))

    assert result.scene_count >= 3
    assert result.frame_count >= 30
    assert result.filename.endswith("-scenes.zip")

    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        files = archive.namelist()

    assert len(files) == result.scene_count
    assert all(name.endswith('.jpg') for name in files)

