from .core import (
    Config, Persona, Input, InputVar, OutputSchema, BaseStep, PromptStep,
    RetrieveStep, ToolStep, CodeStep, IfStep, LoopStep, Constraints, Workflow,
    PilProgram, parse_step, StepType, LoopType, Context
)
from .interpreter import Interpreter
from .utils import render_template_string, safe_eval_code_string
from dotenv import load_dotenv

# Load .env file if present at the time the library is imported.
# This allows users to manage API keys etc. in a .env file for development.
load_dotenv()

__all__ = [
    # From core
    "Config", "Persona", "Input", "InputVar", "OutputSchema", "BaseStep",
    "PromptStep", "RetrieveStep", "ToolStep", "CodeStep", "IfStep", "LoopStep",
    "Constraints", "Workflow", "PilProgram", "parse_step", "StepType",
    "LoopType", "Context",
    # From interpreter
    "Interpreter",
    # From utils
    "render_template_string",
    "safe_eval_code_string",
]

__version__ = "0.0.1"
