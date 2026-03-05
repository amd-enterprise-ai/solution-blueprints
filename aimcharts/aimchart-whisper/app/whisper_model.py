# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""
Whisper-based Speech-to-Text Engine.
"""

import os
import time  # Timing utilities

import numpy as np  # Audio signal processing
import torch  # Deep learning framework
from pydub import AudioSegment  # Audio format conversion


class AudioTranscriber:
    """Audio-to-text transcription using Whisper models."""

    _DEFAULT_MODEL = "openai/whisper-small"

    def __init__(
        self,
        pretrained_model: str = None,
        language_code: str = "english",
        target_device: str = "cpu",
        max_seq_length: int = 8192,
        timestamp_support: bool = False,
    ):
        self.device_target = target_device
        self.lang_code = language_code
        self.seq_max = max_seq_length
        self.use_timestamps = timestamp_support

        self.model_id = os.getenv("ASR_MODEL_PATH", pretrained_model or self._DEFAULT_MODEL)

        self._setup_habana_acceleration()

        print(f"Initializing model: {self.model_id}")
        self._load_model_components()

        self.model.eval()

    def _setup_habana_acceleration(self):
        if self.device_target.lower() == "hpu":
            print("[HPU] Activation Habana Gaudi support...")
            from optimum.habana.transformers.modeling_utils import adapt_transformers_to_gaudi

            adapt_transformers_to_gaudi()
        self.device_target = self.device_target.lower()

    def _load_model_components(self):
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        self.model = WhisperForConditionalGeneration.from_pretrained(self.model_id).to(self.device_target).eval()

        self.processor = WhisperProcessor.from_pretrained(self.model_id)

    def _convert_audio_segment(self, audio_segment: AudioSegment) -> np.ndarray:
        """Convert pydub AudioSegment to normalized float32 waveform."""
        mono_channel = audio_segment.split_to_mono()[0]
        raw_samples = mono_channel.get_array_of_samples()

        if raw_samples.typecode == "h":  # int16
            max_val: float = 32767
        elif raw_samples.typecode == "H":  # uint16
            max_val = 32768
        elif raw_samples.typecode == "i":  # int32
            max_val = 2147483647
        else:
            max_val = 1.0

        waveform = np.array(raw_samples, dtype=np.float32)
        waveform /= max_val
        return waveform.reshape(-1)

    def _prepare_hpu_graph(self, audio_file_path: str):
        """Warmup HPU compilation cache."""
        print("[ASR] Pre-compiling model graph...")
        audio_data = AudioSegment.from_file(audio_file_path).set_frame_rate(16000)
        waveform = self._convert_audio_segment(audio_data)

        inputs = self._preprocess_audio(waveform)
        inputs = {k: v.to(self.device_target) for k, v in inputs.items()}

        with torch.no_grad():
            _ = self.model.generate(**inputs, language=self.lang_code)

    def _preprocess_audio(self, waveform: np.ndarray) -> dict:
        processor_config = {
            "sampling_rate": 16000,
            "return_tensors": "pt",
            "return_attention_mask": True,
            "padding": "longest",
            "truncation": False,
        }

        inputs = self.processor(waveform, **processor_config)

        feature_len = inputs.input_features.shape[-1]
        if feature_len > 3000 and self.device_target != "hpu":
            inputs.input_features = inputs.input_features[..., :3000]
            if "attention_mask" in inputs:
                inputs.attention_mask = inputs.attention_mask[..., :3000]

        return inputs

    def transcribe(self, audio_file: str) -> str:
        """Transcribe audio file to text."""
        inference_start = time.time()

        # Load audio
        audio_data = AudioSegment.from_file(audio_file).set_frame_rate(16000).set_channels(1)
        raw_data = audio_data.raw_data
        sample_width = audio_data.sample_width

        if sample_width == 1:
            dtype = np.uint8
            max_val = 127.5
        elif sample_width == 2:
            dtype = np.int16
            max_val = 32767.0
        elif sample_width == 4:
            dtype = np.int32
            max_val = 2147483647.0
        else:
            dtype = np.float32
            max_val = 1.0

        waveform = np.frombuffer(raw_data, dtype=dtype).astype(np.float32)
        waveform /= max_val

        # Preprocess
        model_inputs = self._preprocess_audio(waveform)
        model_inputs = {k: v.to(self.device_target) for k, v in model_inputs.items()}

        feature_len = model_inputs["input_features"].shape[-1]
        use_timestamps = self.use_timestamps or feature_len > 3000

        generate_params = {**model_inputs, "language": self.lang_code, "return_timestamps": use_timestamps}

        with torch.no_grad():
            tokens = self.model.generate(**generate_params)

        transcript = self.processor.batch_decode(tokens, skip_special_tokens=True)[0]

        elapsed = time.time() - inference_start
        print(
            f"Transcription completed in {elapsed:.2f}s ({feature_len} features, timestamps={use_timestamps}): {transcript}"
        )
        return transcript
