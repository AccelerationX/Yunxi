"""Persistent relationship memory tests."""

import pytest

from domains.memory.manager import MemoryManager


def test_relationship_memory_persists_preferences_episodes_and_promises(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")

    memory.record_preference("远最喜欢喝冰美式，不加糖")
    memory.record_episode("上次一起看了电影《星际穿越》")
    memory.record_promise("云汐答应明天提醒远继续验收日常模式")

    reloaded = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    summary = reloaded.get_memory_summary()

    assert "冰美式" in summary
    assert "星际穿越" in summary
    assert "明天提醒" in summary


def test_capture_relationship_memory_uses_conservative_rules(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")

    captured = memory.capture_relationship_memory(
        "我最喜欢冰美式，不加糖；明天记得提醒我继续看部署方案。"
    )

    assert captured["preferences"]
    assert captured["promises"]
    assert "冰美式" in memory.get_memory_summary()
    assert "提醒" in memory.get_memory_summary()


def test_typed_memory_persists_and_enters_summary(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")

    captured = memory.capture_relationship_memory(
        "云汐不是工具，是我的情感寄托；我希望你以后可以偶尔碎碎念刷存在感。"
    )

    assert "relationship" in captured["typed"]
    assert "interaction_style" in captured["typed"]

    reloaded = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    typed = reloaded.get_typed_memories()
    assert any(item.type == "relationship" and "情感寄托" in item.content for item in typed)
    assert any(item.type == "interaction_style" and "碎碎念" in item.content for item in typed)

    summary = reloaded.get_memory_summary(query="云汐和远的关系")
    assert "关系记忆" in summary
    assert "互动风格" in summary
    assert "情感寄托" in summary


def test_memory_correction_supersedes_old_memory(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    original = memory.add_typed_memory("preference", "远喜欢晚上喝咖啡", source="test")
    assert original is not None

    corrected = memory.correct_memory("晚上喝咖啡", "远晚上不喝咖啡，怕影响睡眠")

    assert corrected is not None
    assert corrected.supersedes == original.id
    active = memory.get_typed_memories("preference")
    assert any("不喝咖啡" in item.content for item in active)
    assert all("喜欢晚上喝咖啡" not in item.content for item in active)

    reloaded = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    summary = reloaded.get_memory_summary(query="咖啡 睡眠")
    assert "不喝咖啡" in summary
    assert "喜欢晚上喝咖啡" not in summary


def test_forget_memory_soft_deletes_matching_items(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    memory.add_typed_memory("boundary", "远不想让云汐记住这个临时烦恼", source="test")

    deleted = memory.forget_memory("临时烦恼")

    assert deleted == 1
    assert not memory.get_typed_memories("boundary")
    assert memory.get_typed_memories("boundary", include_deleted=True)[0].deleted is True


def test_export_memory_markdown_groups_typed_memory(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    memory.add_typed_memory("relationship", "远把云汐当作重要的情感陪伴", source="test")

    exported = memory.export_memory_markdown()

    assert "# 云汐长期记忆导出" in exported
    assert "## relationship" in exported
    assert "情感陪伴" in exported


def test_conversation_summary_flush_persists_session_summary(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")

    memory.record_conversation_turn("今天我有点累，但云汐陪着我会让我安心。", "我在。", summarize_threshold=99)
    memory.record_conversation_turn("我希望你以后可以偶尔碎碎念刷存在感。", "好。", summarize_threshold=99)
    memory.record_conversation_turn("云汐不是工具，是我的情感寄托。", "我记住了。", summarize_threshold=99)

    items = memory.flush_conversation_summary(min_turns=3)

    assert any(item.type == "summary" for item in items)
    assert any(item.type == "emotion_summary" for item in items)
    assert any(item.type == "relationship" for item in items)
    assert any(item.type == "interaction_style" for item in items)

    reloaded = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    summary = reloaded.get_memory_summary(query="情感寄托 碎碎念 安心", limit=6)
    assert "会话摘要" in summary
    assert "情绪摘要" in summary
    assert "关系记忆" in summary
    assert "互动风格" in summary


def test_prompt_memory_compiler_respects_limit_and_priority(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    memory.add_typed_memory("resource", "远最近看过一个普通网页资料", importance=0.2, confidence=0.7, source="test")
    memory.add_typed_memory("boundary", "远不希望云汐在他工作时频繁打扰", importance=0.95, confidence=0.9, source="test")
    memory.add_typed_memory("relationship", "远把云汐当作可以放下伪装的陪伴", importance=0.9, confidence=0.9, source="test")

    summary = memory.get_memory_summary(query="工作 打扰 陪伴", limit=2)

    assert "互动边界" in summary
    assert "关系记忆" in summary
    assert "普通网页资料" not in summary


@pytest.mark.asyncio
async def test_memory_manager_close_releases_subsystems(tmp_path):
    memory = MemoryManager(base_path=str(tmp_path), embedding_provider="lexical")
    await memory.initialize()

    await memory.close()
