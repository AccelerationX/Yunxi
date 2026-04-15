"""技能蒸馏器。

借鉴 15_agent_lifelong_learning 的技能抽象思想重写。
将 PatternMiner 发现的模式泛化为带参数的技能模板。
"""

import re
from typing import Any, Dict, List


class SkillDistiller:
    """技能蒸馏器。"""

    def distill(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        """将 pattern 泛化为带参数的技能模板。"""
        intent = pattern["representative_intent"]
        actions = pattern["actions"]

        params = self._extract_params(intent)
        triggers = self._generalize_triggers(intent, params)

        skill = {
            "skill_name": self._generate_skill_name(intent),
            "trigger_patterns": triggers,
            "parameters": list(params.keys()),
            "actions": actions,
            "source_pattern": pattern,
            "version": 1,
        }
        return skill

    def _extract_params(self, intent: str) -> Dict[str, str]:
        """从意图中提取可能的参数占位符。"""
        params = {}

        if "天气" in intent or "温度" in intent or "下雨" in intent:
            city_match = re.search(r"(?:查询|查|看)?\s*(.+?)[的]?(天气|温度|下雨)", intent)
            if city_match:
                params["city"] = city_match.group(1).strip()
        elif "计算" in intent:
            math_match = re.search(r"计算\s*([\d\+\-\*\/\(\)\.]+)", intent)
            if math_match:
                params["expression"] = math_match.group(1)
        elif "打开" in intent:
            app_match = re.search(r"打开\s*(.+?)(?:$|并|然后)", intent)
            if app_match:
                params["app_name"] = app_match.group(1).strip()
        else:
            stock_match = re.search(r"([\u4e00-\u9fa5]{2,4})", intent)
            if stock_match:
                params["stock_name"] = stock_match.group(1)

        return params

    def _generalize_triggers(self, intent: str, params: Dict[str, str]) -> List[str]:
        """生成泛化的触发模式。"""
        triggers = [intent]

        generalized = intent
        for key, value in params.items():
            generalized = generalized.replace(value, f"{{{key}}}")

        if generalized != intent:
            triggers.append(generalized)

        return triggers

    def _generate_skill_name(self, intent: str) -> str:
        """基于意图生成技能名称。"""
        if "天气" in intent:
            return "query_weather"
        elif "计算" in intent:
            return "calculate_expression"
        elif "打开" in intent:
            return "launch_application"
        elif "截图" in intent:
            return "capture_screenshot"
        elif "剪贴板" in intent or "复制" in intent:
            return "clipboard_operation"
        else:
            words = intent.replace("，", " ").replace("。", " ").split()[:3]
            return "_".join(words) or "unknown_skill"
