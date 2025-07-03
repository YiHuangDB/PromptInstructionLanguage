# Manages the state (variables, history, persona, parameters)
# during PIL program execution.

class ExecutionContext:
    def __init__(self):
        self.variables = {}
        self.conversation_history = [] # Stores dicts like {"role": "...", "content": "..."}
        self.persona_details = {}
        self.global_parameters = {} # e.g., temperature, model from config

    def set_variable(self, name: str, value: any):
        """Stores or updates a variable in the context."""
        self.variables[name] = value

    def get_variable(self, name: str, default: any = None) -> any:
        """
        Retrieves a variable from the context.
        Returns the default value if the variable is not found.
        """
        return self.variables.get(name, default)

    def add_history_entry(self, role: str, content: str):
        """Adds an entry to the conversation history."""
        if not isinstance(role, str) or not isinstance(content, str):
            # Basic type check, can be made more robust
            raise TypeError("Role and content for history entries must be strings.")
        self.conversation_history.append({"role": role, "content": content})

    def get_history(self) -> list[dict]:
        """Returns the entire conversation history."""
        return list(self.conversation_history) # Return a copy

    def set_persona(self, persona_data: dict):
        """Sets the persona details for the LLM."""
        if not isinstance(persona_data, dict):
            raise TypeError("Persona data must be a dictionary.")
        self.persona_details = persona_data.copy() # Store a copy

    def get_persona(self) -> dict:
        """Returns the persona details."""
        return self.persona_details.copy() # Return a copy

    def set_global_parameters(self, params_data: dict):
        """Sets global parameters, typically from the 'config' block."""
        if not isinstance(params_data, dict):
            raise TypeError("Global parameters data must be a dictionary.")
        self.global_parameters = params_data.copy() # Store a copy

    def get_global_parameters(self) -> dict:
        """Returns the global parameters."""
        return self.global_parameters.copy() # Return a copy

    def __str__(self):
        return (
            f"ExecutionContext(\n"
            f"  variables={self.variables},\n"
            f"  conversation_history={self.conversation_history},\n"
            f"  persona_details={self.persona_details},\n"
            f"  global_parameters={self.global_parameters}\n)"
        )
