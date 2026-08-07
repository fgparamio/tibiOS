"""Tests for `tibios_ray.config` — the per-engine configuration surface
(`worker-configuration` spec, design decision D19).

Table-driven over the D19 test table (`design.md`'s Testing Strategy):
empty `env` -> every `WorkerConfig` field `None`; one engine's env vars
present -> only that engine's config object is non-`None`; ONNX model
path present without tokenizer path -> raises (and the symmetric case);
`TIBIOS_RAY_LLAMACPP_POOL_SIZE="abc"` and `"0"` -> both raise; a
configured path is returned byte-identical to the input string.
"""

import dataclasses

import pytest

from tibios_ray.config import (
    DEFAULT_LLAMACPP_POOL_SIZE,
    ConfigError,
    LlamaCppConfig,
    OnnxConfig,
    VllmConfig,
    WorkerConfig,
)


class TestEmptyEnvironment:
    def test_every_engine_config_is_none(self) -> None:
        config = WorkerConfig.from_env({})

        assert config.llamacpp is None
        assert config.vllm is None
        assert config.onnx_embedding is None
        assert config.onnx_rerank is None


class TestOnlyOneEngineConfigured:
    def test_llamacpp_configured_leaves_others_none(self) -> None:
        config = WorkerConfig.from_env({"TIBIOS_RAY_LLAMACPP_GGUF": "/models/model.gguf"})

        assert config.llamacpp is not None
        assert config.vllm is None
        assert config.onnx_embedding is None
        assert config.onnx_rerank is None

    def test_vllm_configured_leaves_others_none(self) -> None:
        config = WorkerConfig.from_env({"TIBIOS_RAY_VLLM_MODEL": "meta-llama/model"})

        assert config.llamacpp is None
        assert config.vllm is not None
        assert config.onnx_embedding is None
        assert config.onnx_rerank is None

    def test_onnx_embedding_configured_leaves_others_none(self) -> None:
        config = WorkerConfig.from_env(
            {
                "TIBIOS_RAY_ONNX_EMBEDDING_MODEL": "/models/embed.onnx",
                "TIBIOS_RAY_ONNX_EMBEDDING_TOKENIZER": "/models/embed-tokenizer",
            }
        )

        assert config.llamacpp is None
        assert config.vllm is None
        assert config.onnx_embedding is not None
        assert config.onnx_rerank is None

    def test_onnx_rerank_configured_leaves_others_none(self) -> None:
        config = WorkerConfig.from_env(
            {
                "TIBIOS_RAY_ONNX_RERANK_MODEL": "/models/rerank.onnx",
                "TIBIOS_RAY_ONNX_RERANK_TOKENIZER": "/models/rerank-tokenizer",
            }
        )

        assert config.llamacpp is None
        assert config.vllm is None
        assert config.onnx_embedding is None
        assert config.onnx_rerank is not None


class TestConfiguredValuesAreByteIdentical:
    def test_llamacpp_gguf_path_is_returned_unmodified(self) -> None:
        config = WorkerConfig.from_env({"TIBIOS_RAY_LLAMACPP_GGUF": "/models/exact-path.gguf"})

        assert config.llamacpp is not None
        assert config.llamacpp.model_path == "/models/exact-path.gguf"

    def test_vllm_model_is_returned_unmodified(self) -> None:
        config = WorkerConfig.from_env({"TIBIOS_RAY_VLLM_MODEL": "org/exact-model-id"})

        assert config.vllm is not None
        assert config.vllm.model == "org/exact-model-id"

    def test_onnx_paths_are_returned_unmodified(self) -> None:
        config = WorkerConfig.from_env(
            {
                "TIBIOS_RAY_ONNX_EMBEDDING_MODEL": "/models/exact-embed.onnx",
                "TIBIOS_RAY_ONNX_EMBEDDING_TOKENIZER": "/models/exact-embed-tokenizer",
                "TIBIOS_RAY_ONNX_EMBEDDING_OUTPUT_NAME": "exact_output",
            }
        )

        assert config.onnx_embedding is not None
        assert config.onnx_embedding.model_path == "/models/exact-embed.onnx"
        assert config.onnx_embedding.tokenizer_path == "/models/exact-embed-tokenizer"
        assert config.onnx_embedding.output_name == "exact_output"


class TestOnnxIncompleteConfigurationRaises:
    def test_model_present_without_tokenizer_raises(self) -> None:
        with pytest.raises(ConfigError):
            WorkerConfig.from_env({"TIBIOS_RAY_ONNX_EMBEDDING_MODEL": "/models/embed.onnx"})

    def test_tokenizer_present_without_model_raises(self) -> None:
        with pytest.raises(ConfigError):
            WorkerConfig.from_env(
                {"TIBIOS_RAY_ONNX_EMBEDDING_TOKENIZER": "/models/embed-tokenizer"}
            )

    def test_rerank_model_present_without_tokenizer_raises(self) -> None:
        with pytest.raises(ConfigError):
            WorkerConfig.from_env({"TIBIOS_RAY_ONNX_RERANK_MODEL": "/models/rerank.onnx"})

    def test_output_name_absent_is_valid_and_none(self) -> None:
        config = WorkerConfig.from_env(
            {
                "TIBIOS_RAY_ONNX_EMBEDDING_MODEL": "/models/embed.onnx",
                "TIBIOS_RAY_ONNX_EMBEDDING_TOKENIZER": "/models/embed-tokenizer",
            }
        )

        assert config.onnx_embedding is not None
        assert config.onnx_embedding.output_name is None


class TestLlamaCppPoolSizeMalformedRaises:
    def test_non_integer_pool_size_raises(self) -> None:
        with pytest.raises(ConfigError):
            WorkerConfig.from_env(
                {
                    "TIBIOS_RAY_LLAMACPP_GGUF": "/models/model.gguf",
                    "TIBIOS_RAY_LLAMACPP_POOL_SIZE": "abc",
                }
            )

    def test_zero_pool_size_raises(self) -> None:
        with pytest.raises(ConfigError):
            WorkerConfig.from_env(
                {
                    "TIBIOS_RAY_LLAMACPP_GGUF": "/models/model.gguf",
                    "TIBIOS_RAY_LLAMACPP_POOL_SIZE": "0",
                }
            )

    def test_negative_pool_size_raises(self) -> None:
        with pytest.raises(ConfigError):
            WorkerConfig.from_env(
                {
                    "TIBIOS_RAY_LLAMACPP_GGUF": "/models/model.gguf",
                    "TIBIOS_RAY_LLAMACPP_POOL_SIZE": "-1",
                }
            )

    def test_stray_pool_size_without_gguf_is_ignored(self) -> None:
        # Engine unconfigured (no GGUF path) takes priority — a stray
        # pool-size value has no engine to size and is not validated.
        config = WorkerConfig.from_env({"TIBIOS_RAY_LLAMACPP_POOL_SIZE": "abc"})

        assert config.llamacpp is None


class TestLlamaCppPoolSizeDefault:
    # `worker-configuration` spec: "Backend-Internal Resource Sizing Is
    # Independently Configurable" — both scenarios.
    def test_configured_pool_size_is_read_from_its_own_value(self) -> None:
        config = WorkerConfig.from_env(
            {
                "TIBIOS_RAY_LLAMACPP_GGUF": "/models/model.gguf",
                "TIBIOS_RAY_LLAMACPP_POOL_SIZE": "4",
            }
        )

        assert config.llamacpp is not None
        assert config.llamacpp.pool_size == 4

    def test_absent_pool_size_falls_back_to_documented_default(self) -> None:
        # Artifact configured, TIBIOS_RAY_LLAMACPP_POOL_SIZE absent ->
        # construction succeeds with the documented default pool size,
        # not treated as absent artifact config.
        config = WorkerConfig.from_env({"TIBIOS_RAY_LLAMACPP_GGUF": "/models/model.gguf"})

        assert config.llamacpp is not None
        assert config.llamacpp.pool_size == DEFAULT_LLAMACPP_POOL_SIZE


class TestFromEnvDefaultsToOsEnviron:
    def test_from_env_with_no_argument_reads_os_environ(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TIBIOS_RAY_VLLM_MODEL", "org/from-environ")
        monkeypatch.delenv("TIBIOS_RAY_LLAMACPP_GGUF", raising=False)

        config = WorkerConfig.from_env()

        assert config.vllm is not None
        assert config.vllm.model == "org/from-environ"


class TestConfigDataclassShape:
    def test_llamacpp_config_is_frozen(self) -> None:
        config = LlamaCppConfig(model_path="/models/model.gguf")
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.model_path = "mutated"  # type: ignore[misc]

    def test_vllm_config_is_frozen(self) -> None:
        config = VllmConfig(model="org/model")
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.model = "mutated"  # type: ignore[misc]

    def test_onnx_config_is_frozen(self) -> None:
        config = OnnxConfig(model_path="/m.onnx", tokenizer_path="/tok")
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.model_path = "mutated"  # type: ignore[misc]

    def test_worker_config_is_frozen(self) -> None:
        config = WorkerConfig(llamacpp=None, vllm=None, onnx_embedding=None, onnx_rerank=None)
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.llamacpp = None  # type: ignore[misc]

    def test_llamacpp_config_rejects_positional_arguments(self) -> None:
        with pytest.raises(TypeError):
            LlamaCppConfig("/models/model.gguf")  # type: ignore[misc,call-arg]

    def test_worker_config_rejects_positional_arguments(self) -> None:
        with pytest.raises(TypeError):
            WorkerConfig(None, None, None, None)  # type: ignore[misc,call-arg]
