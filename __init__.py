"""media_generator — 媒体生成器：让 YUI 生成图片与视频。

工具：
- generate_image：文生图（dashscope 通义万相 / openai 兼容）
- generate_video：文生视频（doubao 火山方舟 Seedance / kling 可灵）

API Key 从环境变量读取（见 providers.py 文档），对话内不暴露密钥。
"""

from __future__ import annotations

from plugin.sdk.plugin import (
    NekoPluginBase,
    lifecycle,
    llm_tool,
    neko_plugin,
)

from . import providers


# 当前已配置的 provider 摘要（不泄露 key 本身）
def _configured_summary() -> str:
    parts = providers.list_configured_providers()
    if not parts:
        return "当前未配置任何媒体 API Key（文生图/文生视频暂不可用）"
    return "当前已配置：" + "、".join(parts)


@neko_plugin
class MediaGeneratorPlugin(NekoPluginBase):
    """媒体生成器 — 文生图 / 文生视频。"""

    def __init__(self, ctx):
        super().__init__(ctx)
        self._save_dir = None

    # ══════════ 生命周期 ══════════

    @lifecycle(id="startup")
    async def on_startup(self, **_):
        try:
            self._save_dir = self.data_path("generated")
        except Exception:
            self._save_dir = None
        return {"status": "ready", "plugin": "media_generator"}

    @lifecycle(id="shutdown")
    async def on_shutdown(self, **_):
        return {"status": "shutdown"}

    # ══════════ 工具：文生图 ══════════

    @llm_tool(
        name="generate_image",
        description=(
            "生成图片。何时用：用户要求'画/生成一张图''做个封面''画个头像''画个示意图'等文生图需求时。"
            "参数 prompt：图片描述（越具体越好，含主体、风格、配色、构图）；"
            "size：可选，1024x1024 / 768x1024 / 1024x768 / 512x512，默认 1024x1024；"
            "provider：可选，dashscope（通义万相）/ openai，默认自动选择已配置的 provider。"
            "限制：需要对应 API Key（见插件说明）；生成的图片以 URL 形式返回，可直接展示给用户。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "图片描述，越具体越好"},
                "size": {"type": "string", "description": "可选：1024x1024 / 768x1024 / 1024x768 / 512x512"},
                "provider": {"type": "string", "description": "可选：dashscope / openai，默认 auto"},
            },
            "required": ["prompt"],
        },
        timeout=150.0,
    )
    async def generate_image(self, *, prompt: str = "", size: str = "", provider: str = "", **_):
        params = _.get("parameters") or {}
        prompt = (prompt or params.get("prompt") or "").strip()
        if not prompt:
            return {"output": "需要提供图片描述（prompt）。请告诉我你想生成什么样的图。", "is_error": True, "error": "NO_PROMPT"}
        size = (size or params.get("size") or "").strip() or "1024x1024"
        provider = (provider or params.get("provider") or "").strip().lower()

        available = providers.list_configured_providers()
        if not available:
            return {"output": _configured_summary() + "。请先在环境中设置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY。", "is_error": True, "error": "NO_PROVIDER"}

        if provider in ("", "auto"):
            provider = "dashscope" if "dashscope" in available else "openai"
        if provider not in ("dashscope", "openai"):
            return {"output": f"未知 provider '{provider}'。支持：dashscope / openai。", "is_error": True, "error": "UNKNOWN_PROVIDER"}
        if provider not in available:
            return {"output": f"provider={provider} 未配置对应 API Key。可用：{'、'.join(available)}。", "is_error": True, "error": "PROVIDER_NOT_CONFIGURED"}

        if provider == "dashscope":
            return await providers.generate_image_dashscope(prompt, size)
        if provider == "openai":
            return await providers.generate_image_openai(prompt, size, save_dir=self._save_dir)
        return {"output": f"未知 provider '{provider}'。支持：dashscope / openai。", "is_error": True, "error": "UNKNOWN_PROVIDER"}

    # ══════════ 工具：文生视频 ══════════

    @llm_tool(
        name="generate_video",
        description=(
            "生成视频。何时用：用户要求'生成/做一个视频''做个宣传视频''做个动态画面'等文生视频需求时。"
            "参数 prompt：视频内容描述（场景、动作、镜头、风格）；"
            "duration：可选，秒数（5 或 10，默认 5，具体范围取决于服务商）；"
            "provider：可选，doubao（火山方舟 Seedance）/ kling（可灵），默认自动选择已配置的 provider。"
            "限制：需要对应 API Key；视频生成耗时较长（约 1-4 分钟），返回视频 URL。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "视频内容描述"},
                "duration": {"type": "integer", "description": "可选：5 或 10 秒"},
                "provider": {"type": "string", "description": "可选：doubao / kling，默认 auto"},
            },
            "required": ["prompt"],
        },
        timeout=300.0,
    )
    async def generate_video(self, *, prompt: str = "", duration: int = 0, provider: str = "", **_):
        params = _.get("parameters") or {}
        prompt = (prompt or params.get("prompt") or "").strip()
        if not prompt:
            return {"output": "需要提供视频内容描述（prompt）。请告诉我你想生成什么样的视频。", "is_error": True, "error": "NO_PROMPT"}
        try:
            duration = int(duration or params.get("duration") or 5)
        except (TypeError, ValueError):
            duration = 5
        provider = (provider or params.get("provider") or "").strip().lower()

        available = providers.list_configured_providers()
        video_available = [p for p in ("doubao", "kling") if p in available]
        if not video_available:
            return {"output": "未配置视频生成 API Key。可设置 DOUBAO_ARK_API_KEY+DOUBAO_ARK_ENDPOINT（Seedance）或 KLING_API_KEY+KLING_SECRET_KEY（可灵）。", "is_error": True, "error": "NO_VIDEO_PROVIDER"}

        if provider in ("", "auto"):
            provider = "doubao" if "doubao" in video_available else "kling"
        if provider not in ("doubao", "kling"):
            return {"output": f"未知 provider '{provider}'。支持：doubao / kling。", "is_error": True, "error": "UNKNOWN_PROVIDER"}
        if provider not in video_available:
            return {"output": f"provider={provider} 未配置对应 API Key。可用：{'、'.join(video_available)}。", "is_error": True, "error": "PROVIDER_NOT_CONFIGURED"}

        if provider == "doubao":
            return await providers.generate_video_doubao(prompt, duration)
        if provider == "kling":
            return await providers.generate_video_kling(prompt, duration)
        return {"output": f"未知 provider '{provider}'。支持：doubao / kling。", "is_error": True, "error": "UNKNOWN_PROVIDER"}
