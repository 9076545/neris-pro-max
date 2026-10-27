"""Pipecat voice pipeline for Neris Pro Max.

Pass provider-specific STT, LLM, TTS, transport, and VAD processors into
``build_voice_pipeline``. Configure STT for ``pt-BR`` and the selected voice
provider for Brazilian Portuguese when constructing those services.

Application callbacks are responsible for enforcing authorization and for
pausing or resuming orchestration outside the voice pipeline.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from pipecat.audio.vad.vad_analyzer import VADAnalyzer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.workers.runner import WorkerRunner

from core.brain import CloudflareWorkersAI
from core.storage import mock_mode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

PT_BR_SYSTEM_INSTRUCTION = (
    "Responda sempre em português brasileiro (pt-BR), com clareza, naturalidade "
    "e frases concisas, apropriadas para uma conversa por voz."
)


class VoiceCommandType(str, Enum):
    STOP = "stop"
    CONTINUE = "continue"
    IMPROVE = "improve"


@dataclass(frozen=True)
class VoiceCommand:
    type: VoiceCommandType
    instruction: str | None = None


VoiceCommandHandler = Callable[[VoiceCommand], Awaitable[None]]


def _normalize_transcript(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", without_accents)).strip()


def parse_voice_command(transcript: str) -> VoiceCommand | None:
    """Parse a global Neris command from a final speech-to-text transcript."""
    normalized = _normalize_transcript(transcript)

    if re.fullmatch(r"neris\s+(?:por favor\s+)?(?:pare|parar|pausa)", normalized):
        return VoiceCommand(VoiceCommandType.STOP)

    if re.fullmatch(
        r"neris\s+(?:por favor\s+)?(?:continue|continuar|retome|retomar)", normalized
    ):
        return VoiceCommand(VoiceCommandType.CONTINUE)

    if re.fullmatch(r"neris\s+melhore\s+isso(?:\s+.+)?", normalized):
        match = re.fullmatch(
            r"\s*neris[\s,;:!?-]+melhore[\s,;:!?-]+isso"
            r"(?:[\s,;:!?-]+(.+?))?[\s.!?]*",
            transcript,
            flags=re.IGNORECASE,
        )
        instruction = match.group(1).strip() if match and match.group(1) else None
        return VoiceCommand(VoiceCommandType.IMPROVE, instruction)

    return None


class GlobalVoiceCommandProcessor(FrameProcessor):
    """Intercept commands without adding them to the LLM conversation."""

    def __init__(self, command_handler: VoiceCommandHandler) -> None:
        super().__init__()
        self._command_handler = command_handler

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if (
            direction == FrameDirection.DOWNSTREAM
            and isinstance(frame, TranscriptionFrame)
        ):
            command = parse_voice_command(frame.text)
            if command is not None:
                if command.type == VoiceCommandType.STOP:
                    await self.push_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
                await self._command_handler(command)
                return

        await self.push_frame(frame, direction)


@dataclass(frozen=True)
class VoicePipelineConfig:
    audio_in_sample_rate: int = 16000
    audio_out_sample_rate: int = 24000
    enable_metrics: bool = True
    system_instruction: str = PT_BR_SYSTEM_INSTRUCTION


def create_cloudflare_llm() -> OpenAILLMService:
    """Create a Pipecat-compatible client for Cloudflare's OpenAI-compatible API."""
    if mock_mode():
        return OpenAILLMService(
            api_key="mock-cloudflare-token",
            base_url=os.getenv(
                "NERIS_MOCK_LLM_BASE_URL", "http://127.0.0.1:8000/mock/v1"
            ),
            settings=OpenAILLMService.Settings(
                model=os.getenv(
                    "CLOUDFLARE_AI_MODEL", "@cf/meta/llama-3.1-8b-instruct"
                )
            ),
        )

    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    missing = [
        name
        for name, value in (
            ("CLOUDFLARE_ACCOUNT_ID", account_id),
            ("CLOUDFLARE_API_TOKEN", api_token),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing Cloudflare configuration: {', '.join(missing)}.")
    ai = CloudflareWorkersAI(
        account_id=account_id,
        api_token=api_token,
    )
    return OpenAILLMService(
        api_key=api_token,
        base_url=(
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{ai._account_id}/ai/v1"
        ),
        settings=OpenAILLMService.Settings(
            model=ai.model,
        ),
    )


def create_elevenlabs_tts() -> ElevenLabsTTSService:
    """Create streaming ElevenLabs speech using credentials from the project .env."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    missing = [
        name
        for name, value in (
            ("ELEVENLABS_API_KEY", api_key),
            ("ELEVENLABS_VOICE_ID", voice_id),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"{', '.join(missing)} must be set in {PROJECT_ROOT / '.env'}."
        )

    return ElevenLabsTTSService(
        api_key=api_key,
        settings=ElevenLabsTTSService.Settings(
            model="eleven_flash_v2_5",
            voice=voice_id,
            stability=0.80,
            similarity_boost=0.85,
            style=0.15,
            use_speaker_boost=True,
        ),
    )


def create_deepgram_stt() -> DeepgramSTTService:
    """Create pt-BR real-time transcription from DEEPGRAM_API_KEY."""
    api_key = os.getenv("DEEPGRAM_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            f"DEEPGRAM_API_KEY must be configured in {PROJECT_ROOT / '.env'} "
            "before starting voice sessions."
        )
    return DeepgramSTTService(
        api_key=api_key,
        settings=DeepgramSTTService.Settings(
            model="nova-3-general",
            language="pt-BR",
        ),
    )


def build_voice_pipeline(
    *,
    transport: BaseTransport,
    command_handler: VoiceCommandHandler,
    stt: FrameProcessor | None = None,
    vad_analyzer: VADAnalyzer | None = None,
    llm: FrameProcessor | None = None,
    tts: FrameProcessor | None = None,
    config: VoicePipelineConfig = VoicePipelineConfig(),
) -> Pipeline:
    """Build a voice pipeline with VAD-based barge-in and explicit commands.

    Pipecat's user-turn interruption handling cancels in-flight LLM/TTS work
    when VAD detects a new user turn. ``Neris, pare`` additionally emits an
    ``InterruptionFrame`` to clear current speech output.
    """
    stt_service = stt if stt is not None else create_deepgram_stt()
    vad = vad_analyzer if vad_analyzer is not None else SileroVADAnalyzer()
    llm_service = llm if llm is not None else create_cloudflare_llm()
    tts_service = tts if tts is not None else create_elevenlabs_tts()
    context = LLMContext(
        messages=[{"role": "system", "content": config.system_instruction}]
    )
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=vad),
    )
    commands = GlobalVoiceCommandProcessor(command_handler)

    return Pipeline(
        [
            transport.input(),
            stt_service,
            commands,
            aggregators.user(),
            llm_service,
            tts_service,
            transport.output(),
            aggregators.assistant(),
        ]
    )


def build_voice_worker(
    pipeline: Pipeline,
    config: VoicePipelineConfig = VoicePipelineConfig(),
) -> PipelineWorker:
    """Create a Pipecat worker with the configured audio and metrics settings."""
    return PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=config.audio_in_sample_rate,
            audio_out_sample_rate=config.audio_out_sample_rate,
            enable_metrics=config.enable_metrics,
        ),
    )


async def run_voice_worker(worker: PipelineWorker) -> None:
    """Run the worker until the session ends or the runner is cancelled."""
    runner = WorkerRunner()
    await runner.add_workers(worker)
    await runner.run()