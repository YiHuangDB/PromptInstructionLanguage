import yaml
from .exceptions import PILSyntaxError

# Define expected top-level keys for basic validation.
# This can be expanded as the language spec becomes more concrete.
REQUIRED_TOP_LEVEL_KEYS = {"workflow"} # 'config' is often good, but a simple workflow might exist alone.
                                      # 'input', 'outputSchema', 'persona' are optional.

def load_pil_file(filepath: str) -> dict:
    """
    Loads a PIL file, parses it as YAML, and performs basic validation.

    Args:
        filepath: The path to the PIL file.

    Returns:
        A dictionary representing the parsed PIL program.

    Raises:
        FileNotFoundError: If the PIL file does not exist.
        PILSyntaxError: If the file is not valid YAML or misses essential structure.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            pil_data = yaml.safe_load(f)
    except FileNotFoundError:
        raise
    except yaml.YAMLError as e:
        raise PILSyntaxError(f"Invalid YAML syntax in {filepath}: {e}")
    except Exception as e: # Catch other potential I/O errors
        raise PILSyntaxError(f"Could not read file {filepath}: {e}")

    if not isinstance(pil_data, dict):
        raise PILSyntaxError(f"PIL file {filepath} content must be a YAML mapping (dictionary).")

    # Basic structural validation
    missing_keys = REQUIRED_TOP_LEVEL_KEYS - set(pil_data.keys())
    if missing_keys:
        raise PILSyntaxError(
            f"PIL file {filepath} is missing required top-level keys: {', '.join(missing_keys)}"
        )

    # Further validation can be added here, e.g., checking types of top-level keys.
    # For example, 'workflow' should typically be a dictionary containing 'steps'.
    if "workflow" in pil_data and not isinstance(pil_data["workflow"], dict):
        raise PILSyntaxError("The 'workflow' block must be a YAML mapping (dictionary).")

    if "workflow" in pil_data and "steps" not in pil_data["workflow"]:
        raise PILSyntaxError("The 'workflow' block must contain a 'steps' list.")

    if "workflow" in pil_data and \
       "steps" in pil_data["workflow"] and \
       not isinstance(pil_data["workflow"]["steps"], list):
        raise PILSyntaxError("The 'steps' in a 'workflow' block must be a list.")

    return pil_data
