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
    max_program_retries: int = 0 # For program-level self-correction

    @classmethod
    def from_yaml(cls, data: Optional[YamlData], is_lsp_parse: bool = False) -> 'Config': # Added is_lsp_parse
        """Creates a Config instance from YAML data."""
        if not data:
            return cls()

        line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
        node_text_preview = str(data)[:70] if data else "None"

        try:
            max_retries_raw = data.get('max_program_retries', 0)
            max_retries = int(max_retries_raw)
            if max_retries < 0:
                loc_line, loc_col = (data.lc.value('max_program_retries')[0], data.lc.value('max_program_retries')[1]) if is_lsp_parse and hasattr(data,'lc') and 'max_program_retries' in data else (line,col)
                raise PILParsingError("'max_program_retries' must be non-negative.", line=loc_line, column=loc_col, node_text=f"max_program_retries: {max_retries_raw}")
        except (ValueError, TypeError) as e:
            loc_line, loc_col = (data.lc.value('max_program_retries')[0], data.lc.value('max_program_retries')[1]) if is_lsp_parse and hasattr(data,'lc') and 'max_program_retries' in data else (line,col)
            raise PILParsingError(f"Invalid value for 'max_program_retries': {e}", line=loc_line, column=loc_col, node_text=f"max_program_retries: {data.get('max_program_retries')}") from e

        return cls(
            model=data.get('model'),
            api_key=data.get('api_key'),
            parameters=data.get('parameters', {}),
            max_program_retries=max_retries
        )

@dataclass
class Persona:
    """Defines the LLM's persona using 'role', 'style', 'tone', etc."""
    role: Optional[str] = None
    style: Optional[str] = None
    tone: Optional[str] = None
    audience: Optional[str] = None

    @classmethod
    def from_yaml(cls, data: Optional[YamlData], is_lsp_parse: bool = False) -> 'Persona': # Added is_lsp_parse
        """Creates a Persona instance from YAML data."""
        if not data:
            return cls()
        # No specific validation here that would benefit much from line numbers yet,
        # as it's mostly .get() calls. If fields were required, we'd add location.
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
    def from_yaml(cls, data: Optional[YamlData], is_lsp_parse: bool = False) -> 'Input': # Added is_lsp_parse
        """Creates an Input instance from YAML data."""
        if not data:
            return cls()

        vars_node = data.get('vars') # This could be CommentedMap or CommentedSeq
        line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
        vars_node_line, vars_node_col = (vars_node.lc.line, vars_node.lc.col) if is_lsp_parse and hasattr(vars_node, 'lc') else (line, col)


        input_vars = []
        if vars_node is None: # vars key is optional
            return cls()

        if isinstance(vars_node, dict): # Handles CommentedMap as well
            for name, type_str_node in vars_node.items():
                # Location of the key 'name'
                key_line, key_col = (vars_node.lc.key(name)[0], vars_node.lc.key(name)[1]) if is_lsp_parse and hasattr(vars_node, 'lc') else (vars_node_line, vars_node_col)
                if not isinstance(type_str_node, str):
                    val_line, val_col = (vars_node.lc.value(name)[0], vars_node.lc.value(name)[1]) if is_lsp_parse and hasattr(vars_node, 'lc') else (key_line, key_col)
                    raise PILParsingError(f"Type for input variable '{name}' must be a string.", line=val_line, column=val_col, node_text=str(type_str_node))
                input_vars.append(InputVar(name=name, type=type_str_node))
        elif isinstance(vars_node, list): # Handles CommentedSeq
            for idx, item_node in enumerate(vars_node):
                item_line, item_col = (item_node.lc.line, item_node.lc.col) if is_lsp_parse and hasattr(item_node, 'lc') else (vars_node_line, vars_node_col)
                if not isinstance(item_node, dict):
                    raise PILParsingError(f"Each item in 'vars' list must be a dictionary.", line=item_line, column=item_col, node_text=str(item_node)[:70])

                name = item_node.get('name')
                type_str = item_node.get('type')

                if not name or not isinstance(name, str):
                    name_loc_l, name_loc_c = (item_node.lc.key('name')[0],item_node.lc.key('name')[1]) if is_lsp_parse and hasattr(item_node,'lc') and 'name' in item_node else (item_line, item_col)
                    raise PILParsingError(f"Input variable item #{idx+1} missing 'name' or name is not a string.", line=name_loc_l, column=name_loc_c, node_text=str(name))
                if not type_str or not isinstance(type_str, str):
                    type_loc_l, type_loc_c = (item_node.lc.key('type')[0],item_node.lc.key('type')[1]) if is_lsp_parse and hasattr(item_node,'lc') and 'type' in item_node else (item_line, item_col)
                    raise PILParsingError(f"Input variable '{name}' (item #{idx+1}) missing 'type' or type is not a string.", line=type_loc_l, column=type_loc_c, node_text=str(type_str))

                input_vars.append(InputVar(name=name, type=type_str, description=item_node.get('description')))
        else:
            raise PILParsingError("'vars' under 'input' must be a dictionary or a list.", line=vars_node_line, column=vars_node_col, node_text=str(vars_node)[:70])

        return cls(vars=input_vars)


@dataclass
class OutputSchema:
    schema: YamlData = field(default_factory=dict) # JSON Schema as a dict

    @classmethod
    def from_yaml(cls, data: Optional[YamlData], is_lsp_parse: bool = False) -> 'OutputSchema': # Added is_lsp_parse
        if not data:
            return cls()
        # schema_node = data.get('schema', {})
        # if not isinstance(schema_node, dict):
        #     line, col = (data.lc.key('schema')[0], data.lc.key('schema')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'schema' in data else (None, None)
        #     raise PILParsingError("'schema' must be a dictionary (JSON schema object).", line=line, column=col, node_text=str(schema_node)[:70])
        return cls(schema=data.get('schema', {})) # JSON schema validation itself is complex; error location for schema content is TBD

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
    def from_yaml(cls, data: YamlData, is_lsp_parse: bool = False) -> 'PromptStep': # Added is_lsp_parse
        line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
        node_text = str(data)[:70]

        if 'text' not in data:
            key_line, key_col = (data.lc.key('text')[0], data.lc.key('text')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'text' in data else (line, col) # Fallback to node start
            raise PILParsingError("PromptStep missing required 'text' field.", line=key_line or line, column=key_col or col, node_text=node_text)

        text_val = data['text']
        if not isinstance(text_val, str):
            val_line, val_col = (data.lc.value('text')[0], data.lc.value('text')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'text' in data else (line, col)
            raise PILParsingError("'text' field in PromptStep must be a string.", line=val_line, column=val_col, node_text=str(text_val)[:50])

        constraints_data = data.get('constraints')
        # Pass is_lsp_parse to nested components
        parsed_constraints = Constraints.from_yaml(constraints_data, is_lsp_parse=is_lsp_parse) if constraints_data else None

        max_retries_raw = data.get('max_retries', 0)
        try:
            max_retries_val = int(max_retries_raw)
            if max_retries_val < 0:
                 m_line, m_col = (data.lc.value('max_retries')[0], data.lc.value('max_retries')[1]) if is_lsp_parse and hasattr(data,'lc') and 'max_retries' in data else (line,col)
                 raise PILParsingError("'max_retries' must be a non-negative integer.", line=m_line, column=m_col, node_text=f"max_retries: {max_retries_raw}")
        except (ValueError, TypeError) as e:
            m_line, m_col = (data.lc.value('max_retries')[0], data.lc.value('max_retries')[1]) if is_lsp_parse and hasattr(data,'lc') and 'max_retries' in data else (line,col)
            raise PILParsingError(f"Invalid value for 'max_retries': {e}", line=m_line, column=m_col, node_text=f"max_retries: {max_retries_raw}") from e

        examples_val = data.get('examples', [])
        if not isinstance(examples_val, list):
            ex_line, ex_col = (data.lc.value('examples')[0], data.lc.value('examples')[1]) if is_lsp_parse and hasattr(data,'lc') and 'examples' in data else (line,col)
            raise PILParsingError("'examples' in PromptStep must be a list.", line=ex_line, column=ex_col, node_text=str(examples_val)[:50])


        return cls(
            text=text_val,
            examples=examples_val,
            constraints=parsed_constraints,
            max_retries=max_retries_val,
            def_var=data.get('def')
        )

@dataclass
class RetrieveStep(BaseStep):
    from_source: str # 'from' is a keyword
    query: str
    k: int = 3
    # def_var is inherited

    @classmethod
    def from_yaml(cls, data: YamlData, is_lsp_parse: bool = False) -> 'RetrieveStep': # Added is_lsp_parse
        line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
        node_text = str(data)[:70]

        for required_key in ['from', 'query']:
            if required_key not in data:
                key_line, key_col = (data.lc.key(required_key)[0], data.lc.key(required_key)[1]) if is_lsp_parse and hasattr(data, 'lc') and required_key in data else (line, col)
                raise PILParsingError(f"RetrieveStep missing required '{required_key}' field.", line=key_line or line, column=key_col or col, node_text=node_text)
            if not isinstance(data[required_key], str):
                val_line, val_col = (data.lc.value(required_key)[0], data.lc.value(required_key)[1]) if is_lsp_parse and hasattr(data, 'lc') and required_key in data else (line,col)
                raise PILParsingError(f"'{required_key}' field in RetrieveStep must be a string.", line=val_line, column=val_col, node_text=str(data[required_key])[:50])

        k_raw = data.get('k', 3)
        try:
            k_val = int(k_raw)
            if k_val <= 0:
                k_line, k_col = (data.lc.value('k')[0],data.lc.value('k')[1]) if is_lsp_parse and hasattr(data,'lc') and 'k' in data else (line,col)
                raise PILParsingError("'k' in RetrieveStep must be a positive integer.", line=k_line, column=k_col, node_text=f"k: {k_raw}")
        except (ValueError, TypeError) as e:
            k_line, k_col = (data.lc.value('k')[0],data.lc.value('k')[1]) if is_lsp_parse and hasattr(data,'lc') and 'k' in data else (line,col)
            raise PILParsingError(f"Invalid value for 'k' in RetrieveStep: {e}", line=k_line, column=k_col, node_text=f"k: {k_raw}") from e

        return cls(
            from_source=data['from'],
            query=data['query'],
            k=k_val,
            def_var=data.get('def')
        )

@dataclass
class ToolStep(BaseStep):
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    # def_var is inherited

    @classmethod
    def from_yaml(cls, data: YamlData, is_lsp_parse: bool = False) -> 'ToolStep': # Added is_lsp_parse
        line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
        node_text = str(data)[:70]

        if 'name' not in data:
            key_line, key_col = (data.lc.key('name')[0], data.lc.key('name')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'name' in data else (line, col)
            raise PILParsingError("ToolStep missing required 'name' field.", line=key_line or line, column=key_col or col, node_text=node_text)
        if not isinstance(data['name'], str):
            val_line, val_col = (data.lc.value('name')[0], data.lc.value('name')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'name' in data else (line,col)
            raise PILParsingError("'name' field in ToolStep must be a string.", line=val_line, column=val_col, node_text=str(data['name'])[:50])

        args_val = data.get('args', {})
        if not isinstance(args_val, dict):
            args_line, args_col = (data.lc.key('args')[0], data.lc.key('args')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'args' in data else (line,col)
            raise PILParsingError("'args' field in ToolStep must be a dictionary.", line=args_line, column=args_col, node_text=str(args_val)[:50])

        return cls(
            name=data['name'],
            args=args_val,
            def_var=data.get('def')
        )

@dataclass
class CodeStep(BaseStep):
    lang: str
    script: str
    # def_var is inherited

    @classmethod
    def from_yaml(cls, data: YamlData, is_lsp_parse: bool = False) -> 'CodeStep': # Added is_lsp_parse
        line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
        node_text = str(data)[:70]

        for required_key in ['lang', 'script']:
            if required_key not in data:
                key_line, key_col = (data.lc.key(required_key)[0], data.lc.key(required_key)[1]) if is_lsp_parse and hasattr(data, 'lc') and required_key in data else (line, col)
                raise PILParsingError(f"CodeStep missing required '{required_key}' field.", line=key_line or line, column=key_col or col, node_text=node_text)
            if not isinstance(data[required_key], str):
                val_line, val_col = (data.lc.value(required_key)[0], data.lc.value(required_key)[1]) if is_lsp_parse and hasattr(data, 'lc') and required_key in data else (line,col)
                raise PILParsingError(f"'{required_key}' field in CodeStep must be a string.", line=val_line, column=val_col, node_text=str(data[required_key])[:50])

        # Specific check for lang == 'python'
        lang_val = data['lang']
        if lang_val.lower() != 'python':
            lang_line, lang_col = (data.lc.value('lang')[0],data.lc.value('lang')[1]) if is_lsp_parse and hasattr(data,'lc') and 'lang' in data else (line,col)
            raise PILParsingError(f"Unsupported language '{lang_val}' in CodeStep. Only 'python' is supported.", line=lang_line, column=lang_col, node_text=f"lang: {lang_val}")

        return cls(
            lang=lang_val,
            script=data['script'],
            def_var=data.get('def')
        )

@dataclass
class IfStep(BaseStep): # BaseStep might not be fully applicable here if 'def' is not typical for 'if'
    condition: str # An expression to be evaluated
    then_steps: List[StepType] = field(default_factory=list) # List of Step objects
    else_steps: List[StepType] = field(default_factory=list) # List of Step objects

    @classmethod
    def from_yaml(cls, data: YamlData, step_parser_func: callable, is_lsp_parse: bool = False) -> 'IfStep': # Added is_lsp_parse
        line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
        node_text = str(data)[:70]

        if 'if' not in data:
            # Error location will be the start of the 'if' step map itself
            raise PILParsingError("IfStep missing required 'if' (condition) field.", line=line, column=col, node_text=node_text)
        if not isinstance(data['if'], str):
            cond_line, cond_col = (data.lc.value('if')[0], data.lc.value('if')[1]) if is_lsp_parse and hasattr(data,'lc') and 'if' in data else (line,col)
            raise PILParsingError("'if' (condition) field in IfStep must be a string.", line=cond_line, column=cond_col, node_text=str(data['if'])[:50])

        then_steps_data = data.get('then', [])
        if not isinstance(then_steps_data, list):
            then_line, then_col = (data.lc.key('then')[0], data.lc.key('then')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'then' in data else (line,col)
            raise PILParsingError("'then' block in IfStep must be a list of steps.", line=then_line, column=then_col, node_text=str(then_steps_data)[:50])

        else_steps_data = data.get('else', [])
        if not isinstance(else_steps_data, list):
            else_line, else_col = (data.lc.key('else')[0], data.lc.key('else')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'else' in data else (line,col)
            raise PILParsingError("'else' block in IfStep must be a list of steps.", line=else_line, column=else_col, node_text=str(else_steps_data)[:50])

        # Pass is_lsp_parse to the recursive calls to step_parser_func
        parsed_then_steps = [step_parser_func(step_data, is_lsp_parse) for step_data in then_steps_data]
        parsed_else_steps = [step_parser_func(step_data, is_lsp_parse) for step_data in else_steps_data]

        return cls(
            condition=data['if'],
            then_steps=parsed_then_steps,
            else_steps=parsed_else_steps,
            def_var=data.get('def')
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
    condition_expr: Optional[str] = None  # e.g., "{{count}} < 10"

    # Regex patterns for parsing loop expressions
    # Updated to use {{variable}} for consistency with general templating
    _FOR_EACH_PATTERN = re.compile(r"^\s*(\w+)\s+in\s+\{\{([\w.]+)\}\}\s*$") # "item in {{collection}}" or "item in {{obj.attr}}"
    _FOR_RANGE_PATTERN = re.compile(r"^\s*(\w+)\s+in\s+range\s*\((.+)\)\s*$") # "i in range(...)"
    _WHILE_PATTERN = re.compile(r"^\s*while\s+(.+)\s*$") # "while condition"

    @classmethod
    def from_yaml(cls, data: YamlData, step_parser_func: callable, is_lsp_parse: bool = False) -> 'LoopStep': # Added is_lsp_parse
        line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
        node_text = str(data)[:70]

        loop_type_key = None
        expression_str = None
        expr_line, expr_col = line, col # Location of the expression string itself

        if 'for' in data:
            loop_type_key = 'for'
            expression_str = data['for']
            if is_lsp_parse and hasattr(data, 'lc'): expr_line, expr_col = data.lc.value('for')[0], data.lc.value('for')[1]
        elif 'while' in data:
            loop_type_key = 'while'
            expression_str = data['while']
            if is_lsp_parse and hasattr(data, 'lc'): expr_line, expr_col = data.lc.value('while')[0], data.lc.value('while')[1]
        elif 'loop' in data:
            loop_type_key = 'loop'
            expression_str = data['loop']
            if is_lsp_parse and hasattr(data, 'lc'): expr_line, expr_col = data.lc.value('loop')[0], data.lc.value('loop')[1]
        else:
            raise PILParsingError("LoopStep must contain 'for', 'while', or 'loop' key.", line=line, column=col, node_text=node_text)

        if not isinstance(expression_str, str):
            raise PILParsingError(f"Loop expression for '{loop_type_key}' must be a string.", line=expr_line, column=expr_col, node_text=str(expression_str))

        steps_data = data.get('steps', [])
        if not isinstance(steps_data, list):
            s_line, s_col = (data.lc.key('steps')[0], data.lc.key('steps')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'steps' in data else (line,col)
            raise PILParsingError("'steps' in LoopStep must be a list.", line=s_line, column=s_col, node_text=str(steps_data)[:50])

        parsed_steps = [step_parser_func(step_item, is_lsp_parse) for step_item in steps_data]

        instance = cls(
            expression=expression_str,
            steps=parsed_steps,
            def_var=data.get('def')
        )

        # Parse the expression string
        if loop_type_key == 'for':
            match_range = cls._FOR_RANGE_PATTERN.match(expression_str)
            if match_range:
                instance.loop_type = LoopType.FOR_RANGE
                instance.loop_var_name = match_range.group(1)
                instance.range_args_str = [arg.strip() for arg in match_range.group(2).split(',')]
                if not instance.range_args_str or not all(instance.range_args_str):
                    raise PILParsingError(f"Invalid range arguments in 'for' loop.", line=expr_line, column=expr_col, node_text=expression_str)
                return instance

            match_each = cls._FOR_EACH_PATTERN.match(expression_str)
            if match_each:
                instance.loop_type = LoopType.FOR_EACH
                instance.loop_var_name = match_each.group(1)
                instance.iterable_var_name = match_each.group(2)
                return instance

            instance.loop_type = LoopType.INVALID
            raise PILParsingError(f"Invalid 'for' loop expression. Expected 'item in {{{{collection}}}}' or 'i in range(...)'.", line=expr_line, column=expr_col, node_text=expression_str)

        elif loop_type_key == 'while' or loop_type_key == 'loop':
            condition_candidate = expression_str
            if expression_str.lower().startswith("while "):
                match_while = cls._WHILE_PATTERN.match(expression_str)
                if match_while:
                    condition_candidate = match_while.group(1).strip()
                else:
                    instance.loop_type = LoopType.INVALID
                    raise PILParsingError(f"Malformed 'while' expression.", line=expr_line, column=expr_col, node_text=expression_str)

            if not condition_candidate:
                 instance.loop_type = LoopType.INVALID
                 raise PILParsingError(f"Empty condition in '{loop_type_key}' loop.", line=expr_line, column=expr_col, node_text=expression_str)

            instance.loop_type = LoopType.WHILE
            instance.condition_expr = condition_candidate
            return instance

        instance.loop_type = LoopType.INVALID # Should be unreachable
        raise PILParsingError(f"Could not determine loop type or parse expression.", line=expr_line, column=expr_col, node_text=expression_str)


@dataclass
class Constraints: # As per Table 2, this is a top-level component for output.
                  # PromptStep also has a 'constraints' field, which might be different.
    type: Optional[str] = None
    regex: Optional[str] = None
    choices: Optional[List[str]] = None
    custom_validator: Optional[str] = None # e.g. "my_validators.py:my_func"

    @classmethod
    def from_yaml(cls, data: Optional[YamlData], is_lsp_parse: bool = False) -> 'Constraints': # Added is_lsp_parse
        if not data:
            return cls()

        # Example for choices: ensure it's a list if provided
        choices_val = data.get('choices')
        if choices_val is not None and not isinstance(choices_val, list):
            line, col = (data.lc.key('choices')[0], data.lc.key('choices')[1]) if is_lsp_parse and hasattr(data, 'lc') and 'choices' in data else (None, None)
            raise PILParsingError("'choices' must be a list of strings.", line=line, column=col, node_text=f"choices: {str(choices_val)[:50]}")

        return cls(
            type=data.get('type'),
            regex=data.get('regex'),
            choices=choices_val,
            custom_validator=data.get('custom_validator')
        )

@dataclass
class Workflow:
    steps: List[StepType] = field(default_factory=list) # Type hint will be resolved later

    @classmethod
    def from_yaml(cls, data: Optional[YamlData], step_parser_func: callable, is_lsp_parse: bool = False) -> 'Workflow':
        if not data or 'steps' not in data:
            # If 'steps' is missing but 'data' (workflow node) exists, error should point to 'data'
            line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
            if data and 'steps' not in data : # Check if data itself is non-empty but 'steps' is missing
                 raise PILParsingError("Workflow block must contain 'steps' key.", line=line, column=col, node_text=str(data)[:50])
            return cls() # Empty workflow if data is None or empty

        parsed_steps = []
        steps_node = data['steps'] # This could be a CommentedSeq

        # Ensure steps_node is a list for iteration
        if not isinstance(steps_node, list): # ruamel.yaml.comments.CommentedSeq is a list subclass
            line, col = (steps_node.lc.line, steps_node.lc.col) if is_lsp_parse and hasattr(steps_node, 'lc') else (None, None)
            raise PILParsingError(f"'steps' must be a list of step definitions.", line=line, column=col, node_text=str(steps_node)[:50])

        for i, step_data_item in enumerate(steps_node):
            try:
                # Pass is_lsp_parse to the step_parser_func
                parsed_steps.append(step_parser_func(step_data_item, is_lsp_parse))
            except PILParsingError: # Let specific errors with location pass through
                raise
            except Exception as e: # Catch generic errors during individual step parsing
                line, col = (step_data_item.lc.line, step_data_item.lc.col) if is_lsp_parse and hasattr(step_data_item, 'lc') else (None, None)
                node_text_preview = str(step_data_item)[:70] if step_data_item else "None"
                raise PILParsingError(f"Error parsing step #{i+1}: {e}", line=line, column=col, node_text=node_text_preview) from e
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
    def from_yaml(cls, data: YamlData, step_parser_func: callable, is_lsp_parse: bool = False) -> 'PilProgram':
        # The 'data' here can be a ruamel.yaml.comments.CommentedMap if is_lsp_parse is True
        # Helper to get value and its location if available
        def get_val_and_loc(key: str):
            val = data.get(key)
            if is_lsp_parse and hasattr(data, 'lc') and key in data:
                # .lc.key() should give (line, col, end_line, end_col) for a key
                # For simplicity, we'll often use the start of the value node or containing node.
                # If data.get_key_comment_eol_bl(key) exists, it can provide more details too.
                # For now, if a key is missing, the error is on the parent 'data' node.
                # If a key is present, its value node location would be data[key].lc if data[key] is also a node.
                # This needs careful handling in each sub-parser.
                pass # Placeholder for more precise sub-node location logic
            return val

        try:
            config_data = get_val_and_loc('config')
            persona_data = get_val_and_loc('persona')
            input_data = get_val_and_loc('input')
            output_schema_data = get_val_and_loc('outputSchema')
            workflow_data = get_val_and_loc('workflow')
            constraints_data = get_val_and_loc('constraints')

            return cls(
                config=Config.from_yaml(config_data), # Pass is_lsp_parse down if Config needs it
                persona=Persona.from_yaml(persona_data),
                input=Input.from_yaml(input_data),
                output_schema=OutputSchema.from_yaml(output_schema_data),
                workflow=Workflow.from_yaml(workflow_data, step_parser_func, is_lsp_parse), # Pass it down
                constraints=Constraints.from_yaml(constraints_data)
            )
        except KeyError as e: # Example: A required sub-key is missing inside a component's from_yaml
            line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
            raise PILParsingError(f"Missing required key: {e}", line=line, column=col, node_text=str(data)[:100]) from e
        except (ValueError, TypeError) as e: # Catch other parsing errors from components
            line, col = (data.lc.line, data.lc.col) if is_lsp_parse and hasattr(data, 'lc') else (None, None)
            # This is a generic catch; ideally, errors from deeper parsing should already be PILParsingError
            if isinstance(e, PILParsingError): raise # Re-raise if already specific
            raise PILParsingError(f"Error parsing PIL program structure: {e}", line=line, column=col, node_text=str(data)[:100]) from e


def parse_step(step_data: Dict[str, Any], is_lsp_parse: bool = False) -> StepType:
    """
    Parses a dictionary representing a single step from YAML into its specific Step object.
    This function acts as a factory for step objects based on unique keys in the step data.
    It's passed to from_yaml methods of PilProgram, Workflow, IfStep, LoopStep for recursive parsing.
    If is_lsp_parse is True, step_data is expected to be a ruamel.yaml CommentedMap.
    """
    line, col, node_text = None, None, str(step_data)[:70]
    if is_lsp_parse and hasattr(step_data, 'lc'):
        line, col = step_data.lc.line, step_data.lc.col

    if not isinstance(step_data, dict):
        raise PILParsingError(f"Step data must be a dictionary, got {type(step_data)}", line=line, column=col, node_text=node_text)

    # Helper to call from_yaml with location awareness
    def _call_from_yaml(component_cls, data_node_key, *args):
        # data_node_key is the key within step_data that holds the actual step definition dict
        # e.g. for "- prompt: {text: ...}", step_data is the outer dict, data_node_key is "prompt"
        # and data_node is step_data["prompt"]
        data_node = step_data.get(data_node_key)
        if not isinstance(data_node, dict):
            node_loc_line, node_loc_col = (step_data.lc.key(data_node_key)[0], step_data.lc.key(data_node_key)[1]) if is_lsp_parse and hasattr(step_data, 'lc') and data_node_key in step_data else (line, col)
            raise PILParsingError(f"Definition for step '{data_node_key}' must be a dictionary.", line=node_loc_line, column=node_loc_col, node_text=str(step_data.get(data_node_key))[:70])

        # For component from_yaml methods, pass the inner node (data_node) and is_lsp_parse
        # The component's from_yaml will be responsible for extracting locations from its keys/values.
        # The *args will typically be step_parser_func for composite steps like IfStep/LoopStep.
        return component_cls.from_yaml(data_node, *args, is_lsp_parse=is_lsp_parse)


    # Determine step type by unique key presence
    if 'prompt' in step_data:
        return _call_from_yaml(PromptStep, 'prompt')
    elif 'retrieve' in step_data:
        return _call_from_yaml(RetrieveStep, 'retrieve')
    elif 'tool' in step_data:
        return _call_from_yaml(ToolStep, 'tool')
    elif 'code' in step_data:
        return _call_from_yaml(CodeStep, 'code')
    elif 'if' in step_data: # 'if' itself is the condition, 'then'/'else' contain steps
        # IfStep.from_yaml needs the whole step_data and the step_parser_func
        return IfStep.from_yaml(step_data, parse_step, is_lsp_parse=is_lsp_parse)
    elif any(key in step_data for key in ['for', 'while', 'loop']):
        # LoopStep.from_yaml also needs the whole step_data and step_parser_func
        return LoopStep.from_yaml(step_data, parse_step, is_lsp_parse=is_lsp_parse)

    raise PILParsingError(f"Unknown or malformed step type", line=line, column=col, node_text=node_text + ". Ensure step key (prompt, retrieve, etc.) is correct.")

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
