"""MCP 工具链 DAG 规划器。

借鉴 14_mcp_tool_hub 的 DAG 编排思想，在 yunxi3.0 内重写。
根据工具间的隐式依赖关系生成可执行的最小工具链拓扑。
"""

from typing import Any, Dict, List, Optional, Set

import networkx as nx


class DAGPlanner:
    """
    工具链 DAG 规划器。

    职责：
    - 维护工具间的隐式依赖规则
    - 根据候选工具列表生成拓扑有序的执行计划
    - 检测并处理循环依赖（退化为安全顺序）
    """

    def __init__(self):
        # 工具名 -> 依赖工具名列表
        self.implicit_deps: Dict[str, List[str]] = {
            "screenshot_capture": [],
            "clipboard_read": [],
            "clipboard_write": [],
            "desktop_notify": [],
            "browser_search": [],
            "browser_open": [],
            "web_page_read": ["browser_search", "browser_open"],
            "browser_follow_link": ["browser_open"],
            "browser_navigate_chain": ["browser_open"],
            "browser_extract_links": ["browser_open"],
            "browser_click": ["browser_open"],
            "browser_type": ["browser_open"],
            "browser_session_open": [],
            "browser_session_snapshot": ["browser_session_open"],
            "browser_session_click": ["browser_session_open"],
            "browser_session_type": ["browser_session_open"],
            "browser_session_fill_form": ["browser_session_open"],
            "browser_session_submit": ["browser_session_open"],
            "list_dir": [],
            "file_read": [],
            "document_read": [],
            "glob": [],
            "grep": [],
            "file_write": [],
            "file_append": [],
            "file_copy": ["file_read"],
            "file_move": [],
            "gui_observe": [],
            "gui_click": ["gui_observe"],
            "gui_type": ["gui_observe"],
            "gui_hotkey": [],
            "gui_run_task": ["gui_observe"],
            "gui_save_macro": [],
            "gui_list_macros": [],
            "gui_macro_stats": ["gui_list_macros"],
            "gui_verify_text": ["gui_observe"],
            "gui_run_macro": ["gui_list_macros"],
            "window_focus_ui": [],
            "app_launch_ui": [],
            "media_control_ui": [],
        }

    def register_dependency(self, tool_name: str, depends_on: List[str]) -> None:
        """注册一个工具的隐式依赖。"""
        self.implicit_deps[tool_name] = depends_on

    def plan(
        self,
        intent_text: str,
        candidate_tools: List[Any],
    ) -> List[Any]:
        """
        根据意图和候选工具生成拓扑有序的执行计划。

        Args:
            intent_text: 用户原始意图（当前版本仅作日志/调试用途）。
            candidate_tools: 候选工具对象列表（元素需有 name 属性）。

        Returns:
            拓扑排序后的工具对象列表。
        """
        tool_names = [getattr(t, "name", "") for t in candidate_tools]
        graph = nx.DiGraph()

        for name in tool_names:
            graph.add_node(name)

        for name in tool_names:
            deps = self.implicit_deps.get(name, [])
            for dep in deps:
                if dep in tool_names:
                    graph.add_edge(dep, name)

        if not nx.is_directed_acyclic_graph(graph):
            # 出现循环依赖时，退化为原始顺序（安全降级）
            return list(candidate_tools)

        ordered_names = list(nx.topological_sort(graph))
        name_to_tool = {getattr(t, "name", ""): t for t in candidate_tools}
        ordered_tools = [name_to_tool[name] for name in ordered_names]
        return ordered_tools

    def topological_sort(
        self,
        plans: List[Any],
    ) -> List[Any]:
        """
        对已有的执行计划（含显式 depends_on）进行拓扑排序。

        Args:
            plans: 执行计划列表，每个元素需有 call_id 和 depends_on 属性。

        Returns:
            拓扑排序后的计划列表。
        """
        graph = nx.DiGraph()
        id_to_plan: Dict[str, Any] = {}

        for plan in plans:
            call_id = getattr(plan, "call_id", "")
            graph.add_node(call_id)
            id_to_plan[call_id] = plan

        for plan in plans:
            call_id = getattr(plan, "call_id", "")
            deps = getattr(plan, "depends_on", [])
            for dep in deps:
                if dep in id_to_plan:
                    graph.add_edge(dep, call_id)

        if not nx.is_directed_acyclic_graph(graph):
            # 环检测失败时按原顺序返回
            return list(plans)

        ordered_ids = list(nx.topological_sort(graph))
        return [id_to_plan[iid] for iid in ordered_ids]

    def detect_cycles(self, tool_names: List[str]) -> Optional[List[str]]:
        """
        检测给定工具集合中是否存在循环依赖。

        Returns:
            如果存在循环，返回循环中的工具名列表；否则返回 None。
        """
        graph = nx.DiGraph()
        for name in tool_names:
            graph.add_node(name)
        for name in tool_names:
            for dep in self.implicit_deps.get(name, []):
                if dep in tool_names:
                    graph.add_edge(dep, name)

        try:
            cycle = nx.find_cycle(graph, orientation="original")
            return [node for node, _, _ in cycle]
        except nx.NetworkXNoCycle:
            return None
