import jsonschema # Allow jsonschema to be an optional import if not strictly needed by all exceptions
from typing import Any # Import Any

class PilEngineError(Exception):
    """Base class for exceptions in the PIL Engine."""
    pass

class ConfigurationError(PilEngineError):
    """Exception for configuration-related errors."""
    pass

class PILParsingError(PilEngineError):
    """Custom exception for errors during PIL program parsing, with location info."""
    def __init__(self, message: str, line: int = None, column: int = None, node_text: str = None):
        super().__init__(message)
        self.line = line
        self.column = column
        self.node_text = node_text # The text of the problematic YAML node

    def __str__(self):
        location = ""
        if self.line is not None and self.column is not None:
            location = f" (at L{self.line+1}:C{self.column+1})" # User-friendly 1-based indexing
        elif self.line is not None:
            location = f" (at L{self.line+1})"

        node_info = f" near '{self.node_text}'" if self.node_text else ""
        return f"{self.args[0]}{location}{node_info}"

class ToolNotFoundException(PilEngineError, KeyError):
    """Exception raised when a tool is not found in the registry."""
    def __init__(self, message: str, tool_name: str = None, available_tools: list = None):
        super().__init__(message)
        self.tool_name = tool_name
        self.available_tools = available_tools if available_tools is not None else []

class ToolExecutionError(PilEngineError):
    """Exception raised when a tool fails during execution."""
    def __init__(self, message: str, tool_name: str = None, original_exception: Exception = None):
        super().__init__(message)
        self.tool_name = tool_name
        self.original_exception = original_exception

class OutputValidationError(PilEngineError):
    """Exception raised when output schema validation fails."""
    def __init__(self, message: str, validation_error: jsonschema.ValidationError = None):
        super().__init__(message)
        self.validation_error = validation_error
        if validation_error:
            self.path = list(validation_error.path)
            self.schema_path = list(validation_error.schema_path)
            self.validator = validation_error.validator
            self.validator_value = validation_error.validator_value
            self.instance = validation_error.instance
            self.schema = validation_error.schema
        else:
            self.path = []
            self.schema_path = []
            self.validator = None
            self.validator_value = None
            self.instance = None
            self.schema = None

    def __str__(self):
        # Enhance the error message if the original validation error is present
        if self.validation_error:
            return f"{super().__str__()} - Details: {self.validation_error.message} at path '{'/'.join(map(str,self.path))}'"
        return super().__str__()


class InvalidSchemaError(PilEngineError): # Renamed from SchemaError to avoid conflict if jsonschema.SchemaError is directly used
    """Exception raised when a provided schema (e.g. OutputSchema) is invalid."""
    def __init__(self, message: str, schema_error: jsonschema.SchemaError = None):
        super().__init__(message)
        self.schema_error = schema_error

    def __str__(self):
        if self.schema_error:
            return f"{super().__str__()} - Details: {self.schema_error.message}"
        return super().__str__()

# It might be good to also have a more generic PilSyntaxError or ParsingError
class PilParsingError(PilEngineError):
    """Exception for errors during the parsing of a PIL program string/file."""
    pass

class ConstraintViolationError(PilEngineError):
    """Exception raised when a value violates a defined constraint."""
    def __init__(self, message: str, constraint_type: str = None, constrained_value: Any = None, constraint_details: Any = None):
        super().__init__(message)
        self.constraint_type = constraint_type
        self.constrained_value = constrained_value
        self.constraint_details = constraint_details

    def __str__(self):
        details = f"{super().__str__()}"
        if self.constraint_type:
            details += f" [Constraint Type: {self.constraint_type}]"
        if self.constrained_value is not None:
            # Truncate if too long
            val_str = str(self.constrained_value)
            if len(val_str) > 100: val_str = val_str[:97] + "..."
            details += f" [Value: {val_str}]"
        if self.constraint_details is not None:
            details += f" [Details: {self.constraint_details}]"
        return details

class CodeExecutionError(PilEngineError):
    """Exception raised when a CodeStep fails during execution."""
    def __init__(self, message: str = "Error during CodeStep script execution.",
                 script_text: str = None,
                 original_error_type: str = None,
                 original_error_message: str = None):
        super().__init__(message)
        self.script_text = script_text
        self.original_error_type = original_error_type
        self.original_error_message = original_error_message

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.original_error_type:
            details.append(f"Type: {self.original_error_type}")
        if self.original_error_message:
            # Truncate if too long
            msg_str = str(self.original_error_message)
            if len(msg_str) > 200: msg_str = msg_str[:197] + "..."
            details.append(f"Message: {msg_str}")
        # if self.script_text: # Script text can be very long, maybe not in default str
        #     details.append(f"Script (first 100 chars): {self.script_text[:100]}")
        if details:
            return f"{base_msg} - Details: {'; '.join(details)}"
        return base_msg
