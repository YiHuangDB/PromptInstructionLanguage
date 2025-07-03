from __future__ import annotations # Must be the first line

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

# Type aliases for better readability
YamlData = Dict[str, Any]
# StepType still needs to use forward references (strings) if defined before component classes.
# from __future__ import annotations handles this for type hints within class/function bodies.
StepType = Union['PromptStep', 'RetrieveStep', 'ToolStep', 'CodeStep', 'IfStep', 'LoopStep']

@dataclass
class Config:
    """Represents the 'config' block in a PIL program, holding global settings."""
    model: Optional[str] = None
    api_key: Optional[str] = None # Note: Sensitive, consider environment variables for actual use
    parameters: Dict[str, Any] = field(default_factory=dict) # e.g., temperature, max_tokens

    @classmethod
    def from_yaml(cls, data: Optional[YamlData]) -> 'Config':
        """Creates a Config instance from YAML data."""
        if not data:
            return cls()
        return cls(
            model=data.get('model'),
            api_key=data.get('api_key'),
            parameters=data.get('parameters', {})
        )

@dataclass
class Persona:
    """Defines the LLM's persona using 'role', 'style', 'tone', etc."""
    role: Optional[str] = None
    style: Optional[str] = None
    tone: Optional[str] = None
    audience: Optional[str] = None

    @classmethod
    def from_yaml(cls, data: Optional[YamlData]) -> 'Persona':
        """Creates a Persona instance from YAML data."""
        if not data:
            return cls()
        return cls(
            role=data.get('role'),
            style=data.get('style'),
            tone=data.get('tone'),
            audience=data.get('audience')
        )

@dataclass
class InputVar:
    """Describes a single input variable for the PIL program."""
    name: str
    type: str # e.g., "string", "int", "boolean", "array", "object"
    description: Optional[str] = None

@dataclass
class Input:
    """Contains a list of input variables (InputVar) for the PIL program."""
    vars: List[InputVar] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, data: Optional[YamlData]) -> 'Input':
        """Creates an Input instance from YAML data."""
        if not data:
            return cls()

        vars_data = data.get('vars', {})
        input_vars = []
        if isinstance(vars_data, dict): # vars: { user_query: string, document_id: int }
            for name, type_str in vars_data.items():
                 input_vars.append(InputVar(name=name, type=type_str))
        elif isinstance(vars_data, list): # vars: [ { name: "user_query", type: "string"} ]
            for item in vars_data:
                if isinstance(item, dict) and 'name' in item and 'type' in item:
                    input_vars.append(InputVar(name=item['name'], type=item['type'], description=item.get('description')))
        return cls(vars=input_vars)


@dataclass
class OutputSchema:
    schema: YamlData = field(default_factory=dict) # JSON Schema as a dict

    @classmethod
    def from_yaml(cls, data: Optional[YamlData]) -> 'OutputSchema':
        if not data:
            return cls()
        return cls(schema=data.get('schema', {}))

@dataclass
class BaseStep:
    # def_var is now a required argument in the generated __init__,
    # but Optional, so None can be passed.
    # from_yaml methods will pass data.get('def'), which handles missing 'def' by passing None.
    def_var: Optional[str]

    def __post_init__(self):
        # Common logic for all steps, if any.
        # 'def' is a reserved keyword in Python, so we use 'def_var' internally
        # and allow 'def' in YAML.
        pass

@dataclass
class PromptStep(BaseStep):
    text: str
    examples: List[Dict[str, str]] = field(default_factory=list) # List of {"input": "...", "output": "..."}
    constraints: Optional[Constraints] = None # Changed from Dict to Constraints object
    max_retries: int = 0 # Maximum number of self-correction retries
    # def_var is inherited for the output variable name

    @classmethod
    def from_yaml(cls, data: YamlData) -> 'PromptStep':
        # Ensure 'constraints' data is parsed into a Constraints object if present
        constraints_data = data.get('constraints')
        parsed_constraints = Constraints.from_yaml(constraints_data) if constraints_data else None

        return cls(
            text=data['text'],
            examples=data.get('examples', []),
            constraints=parsed_constraints,
            max_retries=int(data.get('max_retries', 0)), # Ensure it's an int
            def_var=data.get('def')
        )

@dataclass
class RetrieveStep(BaseStep):
    from_source: str # 'from' is a keyword
    query: str
    k: int = 3
    # def_var is inherited

    @classmethod
    def from_yaml(cls, data: YamlData) -> 'RetrieveStep':
        return cls(
            from_source=data['from'],
            query=data['query'],
            k=data.get('k', 3),
            def_var=data.get('def')
        )

@dataclass
class ToolStep(BaseStep):
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    # def_var is inherited

    @classmethod
    def from_yaml(cls, data: YamlData) -> 'ToolStep':
        return cls(
            name=data['name'],
            args=data.get('args', {}),
            def_var=data.get('def')
        )

@dataclass
class CodeStep(BaseStep):
    lang: str
    script: str
    # def_var is inherited

    @classmethod
    def from_yaml(cls, data: YamlData) -> 'CodeStep':
        return cls(
            lang=data['lang'],
            script=data['script'],
            def_var=data.get('def')
        )

@dataclass
class IfStep(BaseStep): # BaseStep might not be fully applicable here if 'def' is not typical for 'if'
    condition: str # An expression to be evaluated
    then_steps: List[StepType] = field(default_factory=list) # List of Step objects
    else_steps: List[StepType] = field(default_factory=list) # List of Step objects

    @classmethod
    def from_yaml(cls, data: YamlData, step_parser_func: callable) -> 'IfStep':
        # 'def' is unlikely for an 'if' block itself, but BaseStep is harmless
        return cls(
            condition=data['if'], # 'if' is the key for condition
            then_steps=[step_parser_func(step_data) for step_data in data.get('then', [])],
            else_steps=[step_parser_func(step_data) for step_data in data.get('else', [])],
            def_var=data.get('def') # Though unusual for an if block itself
        )

import re
from enum import Enum, auto

class LoopType(Enum):
    FOR_EACH = auto()
    FOR_RANGE = auto()
    WHILE = auto()
    INVALID = auto() # For parsing errors or unrecognized patterns

@dataclass
class LoopStep(BaseStep):
    expression: str  # Original expression string, e.g., "item in ${my_list}", "i in range(5)", "while ${count} < 10"
    steps: List[StepType] = field(default_factory=list)  # Steps to execute in each iteration

    # Fields to be populated by parsing the expression
    loop_type: LoopType = LoopType.INVALID
    loop_var_name: Optional[str] = None  # e.g., "item" or "i"
    iterable_var_name: Optional[str] = None  # e.g., "my_list" (name of variable in context)
    range_args_str: Optional[List[str]] = None  # e.g., ["5"] or ["0", "10", "2"] (as strings, to be evaluated later)
    condition_expr: Optional[str] = None  # e.g., "${count} < 10"

    # Regex patterns for parsing loop expressions
    _FOR_EACH_PATTERN = re.compile(r"^\s*(\w+)\s+in\s+\$\{(\w+)\}\s*$") # "item in ${collection}"
    _FOR_RANGE_PATTERN = re.compile(r"^\s*(\w+)\s+in\s+range\s*\((.+)\)\s*$") # "i in range(...)"
    _WHILE_PATTERN = re.compile(r"^\s*while\s+(.+)\s*$") # "while condition"

    @classmethod
    def from_yaml(cls, data: YamlData, step_parser_func: callable) -> 'LoopStep':
        loop_type_key = None
        expression_str = None

        if 'for' in data:
            loop_type_key = 'for'
            expression_str = data['for']
        elif 'while' in data:
            loop_type_key = 'while'
            expression_str = data['while']
        elif 'loop' in data: # Generic 'loop' key, could be a 'while true' or a more complex future type
            # For now, assume 'loop' implies a while-like structure if it's not 'for'
            # Or treat it as an error if expression doesn't match 'while' pattern
            loop_type_key = 'loop' # Treat as 'while' for parsing for now
            expression_str = data['loop']
        else:
            raise ValueError("Loop step must contain 'for', 'while', or 'loop' key defining the loop expression.")

        if not isinstance(expression_str, str):
            raise ValueError(f"Loop expression for '{loop_type_key}' must be a string. Got: {expression_str}")

        instance = cls(
            expression=expression_str,
            steps=[step_parser_func(step_data) for step_data in data.get('steps', [])],
            def_var=data.get('def')
        )

        # Parse the expression string
        if loop_type_key == 'for':
            # Try "for ... in range(...)"
            match_range = cls._FOR_RANGE_PATTERN.match(expression_str)
            if match_range:
                instance.loop_type = LoopType.FOR_RANGE
                instance.loop_var_name = match_range.group(1)
                # Split args by comma, strip whitespace. Args will be evaluated later.
                instance.range_args_str = [arg.strip() for arg in match_range.group(2).split(',')]
                if not instance.range_args_str or not all(instance.range_args_str): # check for empty strings after split
                    raise ValueError(f"Invalid range arguments in 'for' loop: {expression_str}")
                return instance

            # Try "for ... in ${...}"
            match_each = cls._FOR_EACH_PATTERN.match(expression_str)
            if match_each:
                instance.loop_type = LoopType.FOR_EACH
                instance.loop_var_name = match_each.group(1)
                instance.iterable_var_name = match_each.group(2) # This is the name of the variable in context
                return instance

            instance.loop_type = LoopType.INVALID
            raise ValueError(f"Invalid 'for' loop expression format: '{expression_str}'. Expected 'item in ${{collection}}' or 'i in range(...)'.")

        elif loop_type_key == 'while' or loop_type_key == 'loop': # Treat 'loop' as 'while' for now
            # If 'loop' key is used, we assume it's a condition, similar to 'while'
            # For 'while' or 'loop' as while: "while condition" or "condition"
            condition_candidate = expression_str
            if expression_str.lower().startswith("while "): # If it explicitly says "while condition"
                match_while = cls._WHILE_PATTERN.match(expression_str)
                if match_while:
                    condition_candidate = match_while.group(1).strip()
                else: # Should not happen if it starts with "while " due to regex structure
                    instance.loop_type = LoopType.INVALID
                    raise ValueError(f"Malformed 'while' expression: '{expression_str}'")

            if not condition_candidate: # Check if condition is empty after stripping "while "
                 instance.loop_type = LoopType.INVALID
                 raise ValueError(f"Empty condition in '{loop_type_key}' loop: '{expression_str}'")

            instance.loop_type = LoopType.WHILE
            instance.condition_expr = condition_candidate # The part to be evaluated as boolean
            return instance

        # Should have been caught by initial key check, but as a fallback:
        instance.loop_type = LoopType.INVALID
        raise ValueError(f"Could not determine loop type or parse expression: '{expression_str}'")


@dataclass
class Constraints: # As per Table 2, this is a top-level component for output.
                  # PromptStep also has a 'constraints' field, which might be different.
    type: Optional[str] = None
    regex: Optional[str] = None
    choices: Optional[List[str]] = None
    custom_validator: Optional[str] = None # e.g. "my_validators.py:my_func"

    @classmethod
    def from_yaml(cls, data: Optional[YamlData]) -> 'Constraints':
        if not data:
            return cls()
        return cls(
            type=data.get('type'),
            regex=data.get('regex'),
            choices=data.get('choices'),
            custom_validator=data.get('custom_validator')
        )

@dataclass
class Workflow:
    steps: List[StepType] = field(default_factory=list) # Type hint will be resolved later

    @classmethod
    def from_yaml(cls, data: Optional[YamlData], step_parser_func: callable) -> 'Workflow':
        if not data or 'steps' not in data:
            return cls()

        parsed_steps = []
        for step_data in data['steps']:
            parsed_steps.append(step_parser_func(step_data))
        return cls(steps=parsed_steps)

@dataclass
class PilProgram:
    config: Config = field(default_factory=Config)
    persona: Persona = field(default_factory=Persona)
    input: Input = field(default_factory=Input)
    output_schema: OutputSchema = field(default_factory=OutputSchema)
    workflow: Workflow = field(default_factory=Workflow)
    # The document also mentions a top-level 'constraints' but it's somewhat ambiguous
    # if it's separate from outputSchema or part of step constraints.
    # Table 2 lists it as a top-level component.
    constraints: Optional[Constraints] = None

    @classmethod
    def from_yaml(cls, data: YamlData, step_parser_func: callable) -> 'PilProgram':
        return cls(
            config=Config.from_yaml(data.get('config')),
            persona=Persona.from_yaml(data.get('persona')),
            input=Input.from_yaml(data.get('input')),
            output_schema=OutputSchema.from_yaml(data.get('outputSchema')),
            workflow=Workflow.from_yaml(data.get('workflow'), step_parser_func),
            constraints=Constraints.from_yaml(data.get('constraints'))
        )

def parse_step(step_data: Dict[str, Any]) -> StepType:
    """
    Parses a dictionary representing a single step from YAML into its specific Step object.
    This function acts as a factory for step objects based on unique keys in the step data.
    It's passed to from_yaml methods of PilProgram, Workflow, IfStep, LoopStep for recursive parsing.
    """
    if not isinstance(step_data, dict):
        raise ValueError(f"Step data must be a dictionary, got {type(step_data)}")

    # Determine step type by unique key presence
    if 'prompt' in step_data and isinstance(step_data['prompt'], dict): # e.g. - prompt: {text: ...}
        return PromptStep.from_yaml(step_data['prompt'])
    elif 'retrieve' in step_data and isinstance(step_data['retrieve'], dict):
        return RetrieveStep.from_yaml(step_data['retrieve'])
    elif 'tool' in step_data and isinstance(step_data['tool'], dict):
        return ToolStep.from_yaml(step_data['tool'])
    elif 'code' in step_data and isinstance(step_data['code'], dict):
        return CodeStep.from_yaml(step_data['code'])
    elif 'if' in step_data and isinstance(step_data.get('then'), list): # 'if' is the condition key
        return IfStep.from_yaml(step_data, parse_step)
    elif any(key in step_data for key in ['for', 'while', 'loop']) and isinstance(step_data.get('steps'), list):
        return LoopStep.from_yaml(step_data, parse_step)

    # Fallback for structures like: - key: { ... step content ... }
    # This was more relevant if step_data was the inner dict directly.
    # Given current YAML structure (- prompt: {...}), the above checks are primary.
    keys = list(step_data.keys())
    if len(keys) == 1:
        key = keys[0]
        value = step_data[key]
        if isinstance(value, dict): # Ensure the value (step definition) is a dictionary
            if key == 'prompt': return PromptStep.from_yaml(value)
            if key == 'retrieve': return RetrieveStep.from_yaml(value)
            if key == 'tool': return ToolStep.from_yaml(value)
            if key == 'code': return CodeStep.from_yaml(value)
            # 'if', 'for', 'while', 'loop' typically don't fit this single-key-wrapper structure
            # as their identifying key is part of the main step definition.

    raise ValueError(f"Unknown or malformed step type: {step_data}. Ensure step is defined correctly (e.g., '- prompt: {{...}}').")

# With "from __future__ import annotations", explicit update_forward_refs calls are generally not needed
# for types defined within the same module. Python resolves them at runtime when get_type_hints is called
# or when the annotations are otherwise processed.

# Add __init__.py to core and pil_engine
# Create pil_engine/core/__init__.py
# Create pil_engine/__init__.py
# Create pil_langserver/__init__.py (empty)
# Create examples/__init__.py (empty)
# Create tests/__init__.py (empty)
# Create pil_engine/core/context.py
# Create pil_engine/interpreter.py
# Create pil_engine/utils.py
# Create root __init__.py if needed (usually not for a library structure like this unless it's part of a larger namespace package)
# Create README.md (basic placeholder)
# Create .gitignore (basic python)

# Create other files mentioned above
# Note: The `create_file_with_block` tool can only create one file at a time.
# I will create the other files in subsequent tool calls.
print("Loaded pil_engine/core/components.py with PIL component classes.") # Keep some print for agent feedback
