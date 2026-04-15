"""视觉断言模块。

通过操作前后的截图对比，验证桌面操作是否产生了预期效果。
借鉴 13_computer_use_agent 的视觉验证思想，在 yunxi3.0 内重写。
"""

from typing import Tuple

import cv2
import numpy as np
from PIL import ImageGrab


class VisualAssertion:
    """
    视觉断言器。

    提供截图捕获、像素级差异分析、均方误差计算等能力。
    """

    def capture(self) -> np.ndarray:
        """
        截取全屏并转换为 OpenCV BGR 格式。

        Returns:
            全屏截图的 numpy 数组。
        """
        pil_img = ImageGrab.grab(all_screens=True)
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def pixel_diff(
        self,
        before: np.ndarray,
        after: np.ndarray,
        threshold: float = 0.02,
    ) -> bool:
        """
        判断两张截图之间是否存在显著像素变化。

        Args:
            before: 操作前的截图。
            after: 操作后的截图。
            threshold: 差异像素占比阈值，超过则认为"有变化"。

        Returns:
            True 表示检测到显著变化，False 表示变化不明显。
        """
        if before.shape != after.shape:
            # 分辨率变化直接视为有变化
            return True

        diff = cv2.absdiff(before, after)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)

        changed_pixels = np.count_nonzero(thresh)
        total_pixels = thresh.size
        ratio = changed_pixels / total_pixels

        return ratio > threshold

    def diff_ratio(self, before: np.ndarray, after: np.ndarray) -> float:
        """
        计算两张截图的像素差异比例（精确值）。

        Returns:
            差异像素占总像素的比例，范围 [0.0, 1.0]。
        """
        if before.shape != after.shape:
            return 1.0

        diff = cv2.absdiff(before, after)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)

        changed_pixels = np.count_nonzero(thresh)
        total_pixels = thresh.size
        return changed_pixels / total_pixels

    def mse(self, before: np.ndarray, after: np.ndarray) -> float:
        """
        计算两张截图的均方误差（Mean Squared Error）。

        Args:
            before: 操作前的截图。
            after: 操作后的截图。

        Returns:
            MSE 值，分辨率不一致时返回 inf。
        """
        if before.shape != after.shape:
            return float("inf")

        error = np.sum((before.astype("float") - after.astype("float")) ** 2)
        return error / float(before.size)
