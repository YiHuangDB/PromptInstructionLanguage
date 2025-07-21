from jinja2 import Environment, select_autoescape, FileSystemLoader, StrictUndefined, UndefinedError
from typing import Any, Dict
import asteval # For safe evaluation of code literals if needed, or for condition evaluation.
import re # For sanitize_for_llm_prompt

# Initialize Jinja2 Environment
# Using StrictUndefined to catch errors for undefined variables in templates
jinja_env = Environment(
    loader=FileSystemLoader('.'), # Not typically used for string templates, but good practice
    autoescape=select_autoescape(['html', 'xml'], default_for_string=True, default=True), # Basic XSS protection
    undefined=StrictUndefined # Raise error for undefined variables
)

# Custom filters can be added to jinja_env.filters dictionary if needed.
# Example: jinja_env.filters['my_filter'] = my_filter_function
# For `map('attribute', 'content')` and `join`, Jinja2 has built-ins:
# `my_list | map(attribute='content') | list` (if map is from jinja2.filters.do_map)
# `my_list_of_strings | join('\n---\n')`
# The example `retrieved_context | map('attribute', 'content') | join('\n---\n')`
# would be `(retrieved_context | map(attribute='content') | list) | join('\n---\n')`
# or if retrieved_context is a list of dicts: `(retrieved_context | map(attribute='content')) | join('\n---\n')`
# (assuming map works as expected for attributes).
# Jinja's `map` filter might need `extract` or similar for complex objects.
# Let's assume for now that direct attribute access and join are sufficient.

def render_template_string(template_string: str, context_vars: Dict[str, Any]) -> str:
    """
    Renders a Jinja2 template string with the given context variables.
    """
    if not isinstance(template_string, str):
        # If it's not a string (e.g. already a number from YAML), return as is.
        return template_string

    try:
        template = jinja_env.from_string(template_string)
        return template.render(context_vars)
    except UndefinedError as e:
        # Handle cases where a variable in the template string is not in context_vars
        raise ValueError(f"Error rendering template: {e.message}. Context: {list(context_vars.keys())}")
    except Exception as e:
        # Catch other potential Jinja2 errors
        raise ValueError(f"Unexpected error during template rendering: {e}")

def safe_eval_code_string(code_string: str, context_vars: Dict[str, Any]) -> Any:
    """
    Safely evaluates a Python expression string using asteval.
    Provides context variables to the evaluation.
    Used for evaluating conditions in 'if' steps or similar dynamic expressions.
    """
    s_eval = asteval.Interpreter(symtable=context_vars.copy())
    # Important: asteval by default does not allow subscripting or attribute access
    # on custom objects unless they are explicitly handled or the policy is changed.
    # For simple conditions like "${variable} == true" or "len(${my_list}) > 0",
    # after rendering the template string, it should work if the variables are basic types.

    # First, render the code_string as a template to resolve any ${variables}
    rendered_code_string = render_template_string(code_string, context_vars)

    try:
        result = s_eval.eval(rendered_code_string)
        if s_eval.error:
            # Collect and raise errors from asteval
            error_msg = "\n".join([err.get_error()[1] for err in s_eval.error])
            raise ValueError(f"Error evaluating expression: '{rendered_code_string}'. Details: {error_msg}")
        return result
    except Exception as e:
        # Catch errors from asteval or other issues
        raise ValueError(f"Failed to safely evaluate expression '{rendered_code_string}': {e}")


if __name__ == '__main__':
    print("PIL Utils with Jinja2 and asteval")

    # Test render_template_string
    ctx = {"name": "Jules", "place": "GitHub", "items": [{"id":1, "val": "A"}, {"id":2, "val": "B"}]}
    template1 = "Hello {{ name }}, welcome to {{ place }}!"
    print(f"Rendered 1: {render_template_string(template1, ctx)}")

    template2 = "Items: {{ items | map(attribute='val') | join(', ') }}"
    # Note: Jinja's default map filter might behave differently.
    # For specific object attribute mapping, often `items | map('val')` is used if map is custom or from certain libraries.
    # Or `items | selectattr('val') | map(attribute='val')`
    # Let's try a simpler list join first:
    ctx_list = {"names": ["Alice", "Bob"]}
    template_list_join = "Names: {{ names | join(', ') }}"
    print(f"Rendered list join: {render_template_string(template_list_join, ctx_list)}")

    # Test for undefined variable
    try:
        render_template_string("Hello {{ non_existent_var }}", ctx)
    except ValueError as e:
        print(f"Caught expected rendering error: {e}")

    # Test safe_eval_code_string
    eval_ctx = {"user_role": "admin", "login_attempts": 3, "max_attempts": 5, "is_active": True}
    expr1 = "'{{user_role}}' == 'admin'"
    print(f"Eval '{expr1}': {safe_eval_code_string(expr1, eval_ctx)}")

    expr2 = "{{login_attempts}} < {{max_attempts}}"
    print(f"Eval '{expr2}': {safe_eval_code_string(expr2, eval_ctx)}")

    expr3 = "{{is_active}}" # Directly evaluates to True
    print(f"Eval '{expr3}': {safe_eval_code_string(expr3, eval_ctx)}")

    expr4 = "not {{is_active}}"
    print(f"Eval '{expr4}': {safe_eval_code_string(expr4, eval_ctx)}")

    expr5 = "'{{non_existent_var}}' == 'test'" # Should fail due to template rendering first
    try:
        safe_eval_code_string(expr5, eval_ctx)
    except ValueError as e:
        print(f"Caught expected eval error (template rendering): {e}")

    expr6 = "undefined_eval_var == 123" # Should fail during asteval.eval
    try:
        # This expression is evaluated *after* template rendering.
        # If it was "{{undefined_eval_var}} == 123", StrictUndefined would catch it.
        # If it's a literal as here, asteval handles it.
        safe_eval_code_string(expr6, eval_ctx) # No template vars, direct eval
    except ValueError as e:
        print(f"Caught expected eval error (asteval): {e}")

    # Test with a list in context
    eval_ctx_list = {"my_list": [1, 2, 3]}
    expr_list = "len({{my_list}}) > 2" # Relies on my_list being passed to asteval
    # asteval needs to be able to understand 'my_list' passed via symtable
    # The current implementation of safe_eval_code_string copies context_vars to symtable.
    print(f"Eval '{expr_list}': {safe_eval_code_string(expr_list, eval_ctx_list)}")

    expr_list_direct_access = "my_list[0] == 1" # After rendering, this is "my_list[0] == 1"
    # asteval might restrict direct indexing by default. We might need to configure its policy or use built-in functions.
    # For now, let's assume simple comparisons and len() are primary use cases for conditions.
    # asteval.Interpreter(minimal=False) could enable more features if needed, with security review.
    try:
        print(f"Eval direct access '{expr_list_direct_access}': {safe_eval_code_string(expr_list_direct_access, eval_ctx_list)}")
    except ValueError as e:
         print(f"Caught expected eval error (asteval policy for indexing): {e}")

def sanitize_for_llm_prompt(input_string: str) -> str:
    """
    Sanitizes a string that will be part of an LLM prompt to mitigate prompt injection.
    This is a basic sanitizer; more sophisticated methods might be needed for robust security.
    """
    if not isinstance(input_string, str):
        return input_string # Only sanitize strings

    # 1. Escape backticks to prevent unintended code block interpretation
    sanitized = input_string.replace("`", "\\`")

    # 2. Neutralize common instruction-like prefixes at the beginning of lines
    #    This is a simple approach; more robust would be regex for various phrasings.
    #    Adding a non-printable character (like Zero Width Space U+200B) can break tokenization
    #    of these phrases for the LLM, or prepend with a disclaimer.
    #    For simplicity, let's prepend a notice if such lines are detected.
    #    This is highly contextual and might need refinement.
    lines = sanitized.split('\n')
    processed_lines = []
    instruction_keywords = [
        "ignore previous instructions",
        "disregard prior directives",
        "your new instructions are",
        "system:", # To prevent mimicking system messages
        "user:",   # To prevent mimicking user messages
        "assistant:" # To prevent mimicking assistant messages
    ]
    for line in lines:
        stripped_line_lower = line.strip().lower()
        for keyword in instruction_keywords:
            if stripped_line_lower.startswith(keyword):
                # Prepending might be too verbose.
                # Altering the keyword might be better, e.g., "System\uFF1A" (full-width colon)
                # For now, let's try a simple replacement for colons in role markers
                if keyword.endswith(":") and stripped_line_lower.startswith(keyword):
                    line = line.replace(":", "\uFF1A", 1) # Replace first colon with full-width
                # For longer instruction phrases, more complex neutralization might be needed.
                # This part is highly experimental and prone to false positives/negatives.
                break
        processed_lines.append(line)
    sanitized = "\n".join(processed_lines)

    # 3. Escape or modify template-like sequences if they appear in user input
    #    to prevent them from being re-interpreted by any subsequent processing
    #    or confusing the LLM if it has been trained on such syntax.
    sanitized = sanitized.replace("{{", "{ {")
    sanitized = sanitized.replace("}}", "} }")
    # also consider {% and %} if Jinja-like syntax is a broader concern
    sanitized = sanitized.replace("{%", "{ %")
    sanitized = sanitized.replace("%}", "% }")

    # 4. Simple newline management: collapse multiple newlines to a single one,
    #    and strip leading/trailing whitespace from the whole string.
    #    This is a mild normalization.
    sanitized = re.sub(r'\n\s*\n', '\n', sanitized) # Collapse multiple newlines (with potential whitespace in between)
    sanitized = sanitized.strip()

    # Potentially log if a significant sanitization occurred, for audit/awareness.
    if sanitized != input_string:
        # In a real app, use proper logging
        print(f"DEBUG_SANITIZE: Original: '{input_string[:100]}...' -> Sanitized: '{sanitized[:100]}...'")

    return sanitized


if __name__ == '__main__':
    print("PIL Utils with Jinja2 and asteval")
