import re
import json
import importlib
from typing import Any, Callable

from .core.components import Constraints # Assuming Constraints is in components
from .core.context import Context # Assuming Context is in context
from .exceptions import ConstraintViolationError, PilEngineError

def _dynamic_import(module_path: str, function_name: str) -> Callable:
    """Dynamically imports a function from a module."""
    try:
        module = importlib.import_module(module_path)
        return getattr(module, function_name)
    except ImportError:
        raise PilEngineError(f"Custom validator module '{module_path}' not found.")
    except AttributeError:
        raise PilEngineError(f"Custom validator function '{function_name}' not found in module '{module_path}'.")
    except Exception as e:
        raise PilEngineError(f"Error importing custom validator '{function_name}' from '{module_path}': {e}")


def apply_constraints(
    value: Any,
    constraints: Constraints,
    context: Context,
    step_name: str = "current step" # For more informative error messages
) -> Any:
    """
    Applies defined constraints to a given value.
    The value is typically the string output from an LLM.
    Returns the (potentially type-converted) value if all constraints pass.
    Raises ConstraintViolationError if any constraint fails.
    """
    original_value = value # Keep original for some checks if type conversion happens

    # 1. Type Constraint
    if constraints.type:
        constraint_type_str = constraints.type.lower()
        violation = False
        error_detail = ""

        if constraint_type_str == "string":
            if not isinstance(value, str):
                violation = True
                error_detail = f"Expected type 'string', got {type(value).__name__}."
            # Value remains as is (string)
        elif constraint_type_str == "integer":
            try:
                value = int(value)
            except (ValueError, TypeError):
                violation = True
                error_detail = f"Cannot convert value to 'integer'."
        elif constraint_type_str == "number": # Should be float in Python
            try:
                value = float(value)
            except (ValueError, TypeError):
                violation = True
                error_detail = f"Cannot convert value to 'number' (float)."
        elif constraint_type_str == "boolean":
            if isinstance(value, str):
                if value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                else:
                    violation = True
                    error_detail = f"Cannot convert string value to 'boolean'. Expected 'true' or 'false'."
            elif not isinstance(value, bool): # If it's already a bool, it's fine
                violation = True
                error_detail = f"Expected type 'boolean', got {type(value).__name__}."
        elif constraint_type_str == "list" or constraint_type_str == "array":
            if isinstance(value, str): # Expect JSON string from LLM
                try:
                    parsed_value = json.loads(value)
                    if not isinstance(parsed_value, list):
                        violation = True
                        error_detail = f"Value parsed from JSON string is not a list (got {type(parsed_value).__name__})."
                    else:
                        value = parsed_value
                except json.JSONDecodeError:
                    violation = True
                    error_detail = f"Value is not a valid JSON string for type 'list/array'."
            elif not isinstance(value, list): # If it's already a list (e.g. from CodeStep), it's fine.
                violation = True
                error_detail = f"Expected type 'list/array' or JSON string representing one, got {type(value).__name__}."
        elif constraint_type_str == "object":
            if isinstance(value, str): # Expect JSON string from LLM
                try:
                    parsed_value = json.loads(value)
                    if not isinstance(parsed_value, dict):
                        violation = True
                        error_detail = f"Value parsed from JSON string is not an object/dict (got {type(parsed_value).__name__})."
                    else:
                        value = parsed_value
                except json.JSONDecodeError:
                    violation = True
                    error_detail = f"Value is not a valid JSON string for type 'object'."
            elif not isinstance(value, dict): # If it's already a dict
                violation = True
                error_detail = f"Expected type 'object' or JSON string representing one, got {type(value).__name__}."
        else:
            # Unknown type constraint, could warn or error. For now, let's be strict.
            raise PilEngineError(f"Unknown constraint type '{constraints.type}' specified in step '{step_name}'.")

        if violation:
            raise ConstraintViolationError(
                message=f"Type constraint violated for step '{step_name}'. {error_detail}",
                constraint_type="type",
                constrained_value=original_value, # Show original value that failed
                constraint_details=f"Expected: {constraints.type}"
            )

    # Value might have been type-converted (e.g., string "123" to int 123).
    # Subsequent constraints (regex, choices) typically apply to the string form if the type was string,
    # or the converted form if the type implies conversion.
    # For LLM output, it's usually a string initially. If type conversion happens,
    # regex/choices might need to apply to the original string or this needs clarification.
    # Current assumption: regex/choices apply to the value *after* type conversion if it's still a string,
    # or to the original_value if the type constraint was not string.
    # This is tricky. Let's assume for now:
    # - If type constraint was specified and resulted in non-string, regex/choices might not be applicable or well-defined.
    # - If type constraint was 'string' or not specified, regex/choices apply to `value` (which is a string).

    value_for_string_ops = original_value if isinstance(original_value, str) else str(value)

    # 2. Regex Constraint
    if constraints.regex:
        if not isinstance(value_for_string_ops, str): # Should ideally be a string for regex
             raise ConstraintViolationError(
                message=f"Regex constraint for step '{step_name}' can only be applied to string values after type conversion (got {type(value).__name__}).",
                constraint_type="regex",
                constrained_value=value,
                constraint_details=f"Pattern: {constraints.regex}"
            )
        if not re.fullmatch(constraints.regex, value_for_string_ops): # Use fullmatch for stricter validation
            raise ConstraintViolationError(
                message=f"Regex constraint violated for step '{step_name}'. Value does not match pattern.",
                constraint_type="regex",
                constrained_value=value_for_string_ops,
                constraint_details=f"Pattern: {constraints.regex}"
            )

    # 3. Choices Constraint
    if constraints.choices:
        # Choices usually apply to strings, but could apply to other exact matches if type conversion happened.
        # For simplicity, let's assume choices are typically strings and compare against value_for_string_ops if value was string.
        # If value was converted to int/float/bool, choices should be of that type.
        # This part needs careful thought on how choices interact with prior type conversion.
        # For now: if value is string, choices are strings. If value is number, choices are numbers, etc.

        # Simple approach: if original_value was string, compare as string. Otherwise, compare with converted value.
        target_value_for_choices = original_value if isinstance(original_value, str) and constraints.type is None or constraints.type.lower() == "string" else value

        if target_value_for_choices not in constraints.choices:
            raise ConstraintViolationError(
                message=f"Value for step '{step_name}' is not one of the allowed choices.",
                constraint_type="choices",
                constrained_value=target_value_for_choices,
                constraint_details=f"Allowed choices: {constraints.choices}"
            )

    # 4. Custom Validator
    if constraints.custom_validator:
        if ':' not in constraints.custom_validator:
            raise PilEngineError(f"Invalid custom_validator format for step '{step_name}': '{constraints.custom_validator}'. Expected 'module.path:function_name'.")

        module_str, func_str = constraints.custom_validator.rsplit(':', 1)
        validator_func = _dynamic_import(module_str, func_str)

        try:
            # The validator function receives the current value (potentially type-converted) and the full context
            is_valid = validator_func(value, context)
            if not is_valid: # Validator should return True for valid, False for invalid
                raise ConstraintViolationError(
                    message=f"Custom validator '{constraints.custom_validator}' failed for step '{step_name}'.",
                    constraint_type="custom_validator",
                    constrained_value=value,
                    constraint_details=f"Validator: {constraints.custom_validator}"
                )
        except Exception as e: # Catch exceptions from the validator function itself
             raise ConstraintViolationError(
                message=f"Custom validator '{constraints.custom_validator}' for step '{step_name}' raised an exception: {e}",
                constraint_type="custom_validator",
                constrained_value=value,
                constraint_details=f"Validator: {constraints.custom_validator}, Exception: {type(e).__name__}"
            ) from e

    return value # Return the (potentially type-converted and validated) value
