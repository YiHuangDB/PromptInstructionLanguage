# Placeholder for the PIL execution context.
# This module will manage the state (variables, etc.) during PIL program execution.

class ExecutionContext:
    def __init__(self):
        self.variables = {}
        # Potentially store conversation history, persona details, etc.

    def set_variable(self, name, value):
        self.variables[name] = value

    def get_variable(self, name):
        return self.variables.get(name)

    def __str__(self):
        return f"ExecutionContext(variables={self.variables})"
