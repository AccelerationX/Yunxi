"""主动性与连续性模块。"""

from core.initiative.continuity import (
    CompanionContinuityService,
    ConversationExchange,
    OpenThread,
)
from core.initiative.event_system import (
    InitiativeEvent,
    InitiativeEventLayer,
    ThreeLayerInitiativeEventSystem,
    load_initiative_events,
)
from core.initiative.expression_context import (
    ExpressionContextBuilder,
    ProactiveExpressionContext,
)
from core.initiative.generator import ProactiveGenerationContextBuilder

__all__ = [
    "CompanionContinuityService",
    "ConversationExchange",
    "ExpressionContextBuilder",
    "InitiativeEvent",
    "InitiativeEventLayer",
    "OpenThread",
    "ProactiveGenerationContextBuilder",
    "ProactiveExpressionContext",
    "ThreeLayerInitiativeEventSystem",
    "load_initiative_events",
]
