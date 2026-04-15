"""参数填充器。

借鉴 15_agent_lifelong_learning 的参数填充思想重写。
从用户请求中提取技能模板所需的具体参数值。
"""

import re
from typing import Any, Dict


class ParamFiller:
    """参数填充器。"""

    def fill(self, request: str, skill: Dict[str, Any]) -> Dict[str, str]:
        """从用户请求中提取技能模板所需的具体参数值。"""
        params = {}
        for param in skill.get("parameters", []):
            params[param] = self._extract_param(request, param)
        return params

    def _extract_param(self, request: str, param_name: str) -> str:
        """根据参数名提取对应的值。"""
        rules = {
            "city": r"(?:查询|查|看)?\s*(.+?)[的]?(天气|温度|下雨)",
            "stock_name": r"([\u4e00-\u9fa5]{2,4})",
            "expression": r"计算\s*([\d\+\-\*\/\(\)\.]+)",
            "app_name": r"打开\s*(.+?)(?:$|并|然后|再)",
            "file_path": r"([A-Za-z]:\\[^\s]+|\/[^\s]+)",
            "url": r"(https?://[^\s]+)",
        }

        pattern = rules.get(param_name)
        if pattern:
            match = re.search(pattern, request)
            if match:
                return match.group(1).strip()

        return ""
