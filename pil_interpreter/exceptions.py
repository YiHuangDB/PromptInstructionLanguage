# Placeholder for PIL-specific exceptions.

class PILError(Exception):
    """Base class for exceptions in the PIL interpreter."""
    pass

class PILSyntaxError(PILError):
    """Raised for syntax errors in PIL files."""
    pass

class PILSemanticError(PILError):
    """Raised for semantic errors during PIL execution."""
    pass

class PILConfigurationError(PILError):
    """Raised for errors in the config block."""
    pass
