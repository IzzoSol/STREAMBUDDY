import pytest
import numpy as np
from src.voice import SpeechToText


class TestSpeechToText:
    @pytest.mark.asyncio
    async def test_detect_help_request(self):
        stt = SpeechToText()

        is_help, keyword = await stt.detect_help_request("how do I beat the final boss")
        assert is_help
        assert keyword == "how do i"

        is_help, keyword = await stt.detect_help_request("nice weather today")
        assert not is_help

    @pytest.mark.asyncio
    async def test_extract_game_context(self):
        stt = SpeechToText()

        ctx = await stt.extract_game_context("how do I kill the dragon boss")
        assert "combat" in ctx["categories"]
        assert ctx["is_help_request"]

        ctx = await stt.extract_game_context("where is the hidden treasure")
        assert "exploration" in ctx["categories"]
        assert ctx["is_help_request"]
