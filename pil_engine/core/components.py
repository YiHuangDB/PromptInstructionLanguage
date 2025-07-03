from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

# Type aliases for better readability
YamlData = Dict[str, Any]
StepType = Union['PromptStep', 'RetrieveStep', 'ToolStep', 'CodeStep', 'IfStep', 'LoopStep'] # Forward declaration for type hinting

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
    def_var: Optional[str] = None # Stores the name of the variable to define with the step's output

    def __post_init__(self):
        # Common logic for all steps, if any.
        # 'def' is a reserved keyword in Python, so we use 'def_var' internally
        # and allow 'def' in YAML.
        pass

@dataclass
class PromptStep(BaseStep):
    text: str
    examples: List[Dict[str, str]] = field(default_factory=list) # List of {"input": "...", "output": "..."}
    constraints: Optional[Dict[str, Any]] = None # Simplified for now
    # def_var is inherited for the output variable name

    @classmethod
    def from_yaml(cls, data: YamlData) -> 'PromptStep':
        return cls(
            text=data['text'],
            examples=data.get('examples', []),
            constraints=data.get('constraints'),
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
    then_steps: List[Any] = field(default_factory=list) # List of Step objects
    else_steps: List[Any] = field(default_factory=list) # List of Step objects

    @classmethod
    def from_yaml(cls, data: YamlData, step_parser_func: callable) -> 'IfStep':
        # 'def' is unlikely for an 'if' block itself, but BaseStep is harmless
        return cls(
            condition=data['if'], # 'if' is the key for condition
            then_steps=[step_parser_func(step_data) for step_data in data.get('then', [])],
            else_steps=[step_parser_func(step_data) for step_data in data.get('else', [])],
            def_var=data.get('def') # Though unusual for an if block itself
        )

@dataclass
class LoopStep(BaseStep): # TODO: Define loop semantics (e.g., for_each, while)
    # For now, a simple conceptual placeholder
    expression: str # e.g., "item in ${my_list}" or "count < 10"
    steps: List[Any] = field(default_factory=list) # Steps to execute in each iteration

    @classmethod
    def from_yaml(cls, data: YamlData, step_parser_func: callable) -> 'LoopStep':
        # This is a simplified placeholder. Real loop implementation would be more complex.
        # It needs to define how 'expression' is used (e.g. 'for', 'while', 'count')
        # and how loop variables are handled.
        loop_type_key = None
        for key in ['for', 'while', 'loop']: # 'loop' is generic from doc
             if key in data:
                 loop_type_key = key
                 break
        if not loop_type_key:
            raise ValueError("Loop step must contain 'for', 'while', or 'loop' key.")

        return cls(
            expression=data[loop_type_key],
            steps=[step_parser_func(step_data) for step_data in data.get('steps', [])],
            def_var=data.get('def') # Output of a loop could be an aggregation
        )

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

# Update forward references now that all classes are defined
for step_list_type in [IfStep.then_steps, IfStep.else_steps, LoopStep.steps, Workflow.steps]:
    # This is tricky with dataclasses. A better way is to use string literal for types
    # and then call typing.update_forward_refs() at the end of the module.
    # For now, the StepType Union with forward declaration strings handles this.
    pass
import typing
typing.update_forward_refs(Config)
typing.update_forward_refs(Persona)
typing.update_forward_refs(Input)
typing.update_forward_refs(OutputSchema)
typing.update_forward_refs(PromptStep)
typing.update_forward_refs(RetrieveStep)
typing.update_forward_refs(ToolStep)
typing.update_forward_refs(CodeStep)
typing.update_forward_refs(IfStep)
typing.update_forward_refs(LoopStep)
typing.update_forward_refs(Workflow)
typing.update_forward_refs(PilProgram)
typing.update_forward_refs(Constraints)

# Final check: Ensure StepType Union is correctly defined
# This might be better done by directly listing the classes in the Union
# StepType = Union[PromptStep, RetrieveStep, ToolStep, CodeStep, IfStep, LoopStep]
# The forward declaration string method is generally more robust for complex dependencies.
# The current StepType = Union['PromptStep', ...] should work with update_forward_refs.
# Let's explicitly redefine for clarity if needed after testing.
ActualStepType = Union[PromptStep, RetrieveStep, ToolStep, CodeStep, IfStep, LoopStep]
Workflow.steps.__type__ = List[ActualStepType]
IfStep.then_steps.__type__ = List[ActualStepType]
IfStep.else_steps.__type__ = List[ActualStepType]
LoopStep.steps.__type__ = List[ActualStepType]

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
