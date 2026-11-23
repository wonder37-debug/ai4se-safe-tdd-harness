"""Tool registry: schema validation, unknown tools, error containment."""

from pydantic import BaseModel

from safefix.models import Action, Observation
from safefix.tools.registry import ToolContext, ToolRegistry


class EchoArgs(BaseModel):
    text: str


class EchoTool:
    name = "echo"
    args_model = EchoArgs

    async def execute(self, args: EchoArgs, ctx: ToolContext) -> Observation:
        return Observation(ok=True, content=args.text)


class BoomTool:
    name = "boom"
    args_model = EchoArgs

    async def execute(self, args, ctx):
        raise RuntimeError("tool exploded")


def make_registry():
    return ToolRegistry([EchoTool(), BoomTool()])


async def test_dispatch_validates_and_executes(tmp_path):
    obs = await make_registry().dispatch(
        Action(tool="echo", args={"text": "hi"}), ToolContext(workspace=tmp_path)
    )
    assert obs.ok and obs.content == "hi"


async def test_unknown_tool_rejected(tmp_path):
    obs = await make_registry().dispatch(Action(tool="nope", args={}), ToolContext(workspace=tmp_path))
    assert not obs.ok and "unknown tool" in obs.error


async def test_invalid_arguments_rejected_without_execution(tmp_path):
    obs = await make_registry().dispatch(Action(tool="echo", args={}), ToolContext(workspace=tmp_path))
    assert not obs.ok and "invalid arguments" in obs.error


async def test_wrong_argument_type_rejected(tmp_path):
    obs = await make_registry().dispatch(
        Action(tool="echo", args={"text": 5}), ToolContext(workspace=tmp_path)
    )
    assert not obs.ok


async def test_tool_exception_contained(tmp_path):
    obs = await make_registry().dispatch(
        Action(tool="boom", args={"text": "x"}), ToolContext(workspace=tmp_path)
    )
    assert not obs.ok and "tool exploded" in obs.error


def test_schemas_exposed_for_native_tool_calling():
    schemas = make_registry().schemas()
    echo = next(s for s in schemas if s["function"]["name"] == "echo")
    assert echo["type"] == "function"
    assert "text" in echo["function"]["parameters"]["properties"]
