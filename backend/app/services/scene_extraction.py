"""Scene extraction service for converting videos into scene preview images."""

from __future__ import annotations

import asyncio
import io
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from fastapi import UploadFile


class SceneExtractionError(RuntimeError):
    """Raised when a video cannot be processed into scene images."""


@dataclass(frozen=True)
class SceneExtractionResult:
    """Result of the scene extraction process."""

    filename: str
    content: bytes
    scene_count: int
    frame_count: int


class SceneExtractionService:
    """Service that extracts representative images from scene changes in a video."""

    def __init__(
        self,
        *,
        scene_threshold: float = 0.48,
        min_scene_length: int = 5,
        max_scenes: int = 200,
        image_format: str = "jpg",
        jpeg_quality: int = 90,
    ) -> None:
        try:  # pragma: no cover - dependency availability is environment-specific
            import cv2  # type: ignore[import-not-found]
            import numpy as np  # type: ignore[import-not-found]
        except ImportError:
            cv2 = None  # type: ignore[assignment]
            np = None  # type: ignore[assignment]

        if max_scenes < 1:
            raise ValueError("max_scenes must be at least 1")
        if min_scene_length < 1:
            raise ValueError("min_scene_length must be at least 1")

        self._cv2: Optional[Any] = cv2
        self._np: Optional[Any] = np
        self._scene_threshold = float(scene_threshold)
        self._min_scene_length = int(min_scene_length)
        self._max_scenes = int(max_scenes)
        self._image_format = image_format.lower()
        self._jpeg_quality = int(jpeg_quality)

    async def extract_scene_archive(self, *, upload_path: Path, original_name: str | None) -> SceneExtractionResult:
        """Extract scene preview images from the provided video file."""

        self._require_dependencies()

        if not upload_path.is_file():  # pragma: no cover - defensive guard
            raise SceneExtractionError("동영상 파일을 찾을 수 없습니다.")

        result = await asyncio.to_thread(
            self._process_video, upload_path, original_name or "configuration-video"
        )
        return result

    async def extract_from_upload(self, upload: UploadFile) -> SceneExtractionResult:
        """Persist an UploadFile temporarily and extract scene images."""

        self._require_dependencies()

        filename = getattr(upload, "filename", None)
        suffix = ""
        if isinstance(filename, str) and "." in filename:
            suffix = f".{filename.rsplit('.', 1)[-1]}"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            await upload.seek(0)
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                temp_file.write(chunk)

        try:
            if temp_path.stat().st_size == 0:
                raise SceneExtractionError("업로드된 동영상이 비어 있습니다.")
            result = await self.extract_scene_archive(upload_path=temp_path, original_name=filename)
        finally:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:  # pragma: no cover - defensive
                pass

        return result

    def _process_video(self, video_path: Path, original_name: str) -> SceneExtractionResult:
        self._require_dependencies()

        cv2 = self._cv2
        np = self._np
        assert cv2 is not None  # for type checkers
        assert np is not None

        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            capture.release()
            raise SceneExtractionError("동영상을 열 수 없습니다. 다른 파일로 다시 시도해 주세요.")

        try:
            success, frame = capture.read()
            if not success:
                raise SceneExtractionError("동영상에서 프레임을 추출하지 못했습니다.")

            frames: List[Any] = []
            frames.append(frame.copy())
            total_frames = 1
            previous_hist = self._compute_histogram(frame)
            frames_since_last_scene = 1

            while True:
                success, frame = capture.read()
                if not success:
                    break

                total_frames += 1
                current_hist = self._compute_histogram(frame)
                difference = cv2.compareHist(
                    previous_hist, current_hist, cv2.HISTCMP_BHATTACHARYYA
                )

                if (
                    difference >= self._scene_threshold
                    and frames_since_last_scene >= self._min_scene_length
                    and len(frames) < self._max_scenes
                ):
                    frames.append(frame.copy())
                    frames_since_last_scene = 1
                else:
                    frames_since_last_scene += 1

                previous_hist = current_hist

            if not frames:
                raise SceneExtractionError("장면 이미지를 추출하지 못했습니다.")

            archive_bytes = self._build_archive(frames)

            sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_name).stem)
            sanitized = sanitized.strip("._") or "configuration-video"
            archive_name = f"{sanitized}-scenes.zip"

            return SceneExtractionResult(
                filename=archive_name,
                content=archive_bytes,
                scene_count=len(frames),
                frame_count=total_frames,
            )
        finally:
            capture.release()

    def _compute_histogram(self, frame):
        cv2 = self._cv2
        np = self._np
        assert cv2 is not None
        assert np is not None

        histogram = cv2.calcHist([frame], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        cv2.normalize(histogram, histogram)
        return histogram.astype(np.float32)

    def _build_archive(self, frames: List) -> bytes:
        cv2 = self._cv2
        assert cv2 is not None

        buffer = io.BytesIO()
        extension = f".{self._image_format}"

        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, frame in enumerate(frames, start=1):
                success, encoded = cv2.imencode(
                    extension,
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
                )
                if not success:
                    raise SceneExtractionError("이미지 인코딩에 실패했습니다.")

                file_name = f"scene-{index:03d}{extension}"
                archive.writestr(file_name, encoded.tobytes())

        return buffer.getvalue()

    def _require_dependencies(self) -> None:
        if self._cv2 is None or self._np is None:
            raise SceneExtractionError(
                "영상 처리를 위해 opencv-python-headless 패키지가 필요합니다. 관리자에게 설치를 요청해 주세요."
            )
