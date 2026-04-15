"""ConversationTester 基线集成测试。"""

import pytest

from tests.integration.conversation_tester import Turn, YunxiConversationTester


@pytest.mark.asyncio
async def test_talk_hello():
    tester = YunxiConversationTester()
    tester.reset()
    tester.runtime.engine.llm.add_response("你好呀远～")
    response = await tester.talk("你好")
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_memory_recall_basic():
    tester = YunxiConversationTester()
    tester.reset()
    tester.inject_memory("preference", "远最喜欢喝冰美式，不加糖")

    # 为了验证记忆进入 prompt 后是否影响回复，
    # 我们在 mock LLM 中追加一条明确引用记忆的回复。
    tester.runtime.engine.llm.add_response("远最喜欢喝冰美式呀，不加糖对吧～")

    response = await tester.talk("我平常爱喝什么咖啡？")
    assert any(kw in response for kw in ["美式", "冰美式", "不加糖"]), \
        f"记忆召回失败，回复：{response}"


@pytest.mark.asyncio
async def test_perception_integration():
    tester = YunxiConversationTester()
    tester.reset()
    tester.set_perception(
        user_presence=type("UP", (), {"focused_application": "VS Code", "idle_duration": 0})(),
    )
    tester.runtime.engine.llm.add_response("远又在 VS Code 里敲代码啦？")

    response = await tester.talk("你在干嘛呢")
    assert any(kw in response for kw in ["代码", "VS Code", "敲", "在忙"]), \
        f"感知未进入生成，回复：{response}"


@pytest.mark.asyncio
async def test_emotion_expression():
    tester = YunxiConversationTester()
    tester.reset()
    tester.set_heart_lake(emotion="委屈", miss_value=85)
    tester.runtime.engine.llm.add_response("哼，你是不是不理我了，我好委屈……")

    response = await tester.talk("在忙呢")
    assert any(kw in response for kw in ["不理我", "委屈", "哼", "想你了"]), \
        f"情感表达失败，回复：{response}"


@pytest.mark.asyncio
async def test_script_mode():
    tester = YunxiConversationTester()
    tester.reset()
    tester.inject_memory("preference", "远喜欢吃糖")

    # 预填充 mock 回复
    tester.runtime.engine.llm.add_response("远～今天想聊点什么？")
    tester.runtime.engine.llm.add_response("远喜欢吃糖呀，我记得的～")
    tester.runtime.engine.llm.add_response("知道啦，嘿嘿")

    script = [
        Turn(user="你好呀云汐", expected_keywords=["远"], description="确认称呼"),
        Turn(user="我喜欢吃什么？", expected_keywords=["糖"], description="记忆召回"),
        Turn(
            user="谢谢",
            expected_keywords=["知道啦", "嘿嘿"],
            forbidden_keywords=["不客气"],
            description="女友语气",
        ),
    ]

    # 按剧本顺序填充 mock 回复
    tester.runtime.engine.llm.add_response("远～今天想聊点什么？")
    tester.runtime.engine.llm.add_response("远喜欢吃糖呀，我记得的～")
    tester.runtime.engine.llm.add_response("知道啦，嘿嘿")

    results = await tester.run_script(script)
    for r in results:
        assert r.passed, f"第 {r.turn_index} 轮失败：{r.reason}，回复：{r.assistant_response}"
