import jsonschema # Allow jsonschema to be an optional import if not strictly needed by all exceptions

class PilEngineError(Exception):
    """Base class for exceptions in the PIL Engine."""
    pass

class ConfigurationError(PilEngineError):
    """Exception for configuration-related errors."""
    pass

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
