from typing import Any, Dict, Optional

class Context:
    """
    Manages the state (variables) during the execution of a PIL program.
    """
    def __init__(self, initial_vars: Optional[Dict[str, Any]] = None):
        self._variables: Dict[str, Any] = {}
        if initial_vars:
            self._variables.update(initial_vars)

    def set_variable(self, name: str, value: Any) -> None:
        """Sets or updates a variable in the context."""
        if not name:
            raise ValueError("Variable name cannot be empty.")
        self._variables[name] = value

    def get_variable(self, name: str, default: Optional[Any] = None) -> Any:
        """
        Gets a variable from the context.
        Returns the specified default value (which is None if not provided by caller)
        if the variable is not found.
        """
        return self._variables.get(name, default)

    def get_variable_strict(self, name: str) -> Any:
        """Gets a variable from the context. Raises KeyError if not found."""
        if name not in self._variables:
            raise KeyError(f"Variable '{name}' not found in context.")
        return self._variables[name]

    def has_variable(self, name: str) -> bool:
        """Checks if a variable exists in the context."""
        return name in self._variables

    def get_all_variables(self) -> Dict[str, Any]:
        """Returns a copy of all variables in the context."""
        return self._variables.copy()

    def update_variables(self, new_vars: Dict[str, Any]) -> None:
        """Updates the context with a dictionary of new variables."""
        if not isinstance(new_vars, dict):
            raise TypeError("new_vars must be a dictionary.")
        self._variables.update(new_vars)

    def __str__(self) -> str:
        return f"Context({self._variables})"

    def __repr__(self) -> str:
        return f"Context(variables={list(self._variables.keys())})"
