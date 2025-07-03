import re
from string import Template # For basic variable substitution
from .context import ExecutionContext
from .exceptions import PILSemanticError, PILSyntaxError

class Evaluator:
    def __init__(self, pil_program_data: dict, context: ExecutionContext):
        if not isinstance(pil_program_data, dict):
            raise PILSyntaxError("PIL program data must be a dictionary.")
        if not isinstance(context, ExecutionContext):
            raise TypeError("Context must be an instance of ExecutionContext.")

        self.program_data = pil_program_data
        self.context = context

        # Populate context with initial data from PIL program
        if "config" in self.program_data and isinstance(self.program_data["config"], dict):
            self.context.set_global_parameters(self.program_data["config"].get("parameters", {}))

        if "persona" in self.program_data and isinstance(self.program_data["persona"], dict):
            self.context.set_persona(self.program_data["persona"])

        # Inputs are typically loaded into context by the CLI or calling environment
        # We could add validation here against an 'input' block in PIL if needed
        # e.g., ensure all declared inputs in PIL file are present in context.

    def _substitute_variables(self, text: str) -> str:
        """
        Substitutes ${variable} or $variable patterns in text with values from context.
        More complex templating (like Jinja2) would replace this.
        """
        if not isinstance(text, str):
            return text # Or raise error

        # Simple $variable or ${variable} substitution using string.Template
        # For more complex cases (attributes, filters), Jinja2 would be better.
        # This regex finds ${var} or $var patterns.
        # It's a bit more robust than plain Template for missing vars if we want to keep them.

        # First, create a mapping for Template, handling missing keys gracefully
        # by returning the original placeholder if a variable is not found.
        class SafeDict(dict):
            def __missing__(self, key):
                return '${' + key + '}' # or '$' + key if you prefer

        template_vars = SafeDict(self.context.variables)

        # Attempt substitution using string.Template
        # This handles ${var} and $var (if $var is not followed by another letter/number)
        try:
            # Replace ${var} with $var for Template compatibility if needed,
            # or use a regex to find all ${var} and $var.
            # For simplicity, let's assume Template handles ${var} correctly if var is simple.
            # A more robust approach involves regex:
            def replace_match(match):
                var_name = match.group(1) or match.group(2)
                return str(self.context.get_variable(var_name, match.group(0)))

            # Regex to find $variable or ${variable}
            # It captures the variable name without the $ or ${}
            text = re.sub(r'\$(?:([a-zA-Z_][a-zA-Z0-9_]*)|{([a-zA-Z_][a-zA-Z0-9_]*)})', replace_match, text)
            return text

        except Exception as e:
            # Fallback or error for complex cases not handled by simple substitution
            # print(f"Warning: Variable substitution failed for text: '{text[:50]}...'. Error: {e}", file=sys.stderr)
            return text # Return original text if substitution fails badly


    def _handle_prompt_step(self, step_config: dict):
        if not isinstance(step_config, dict):
            raise PILSemanticError("Prompt step configuration must be a dictionary.")

        prompt_text = step_config.get("text")
        if not prompt_text or not isinstance(prompt_text, str):
            raise PILSemanticError("Prompt step must have a 'text' field as a string.")

        output_var_name = step_config.get("def")
        # examples = step_config.get("examples") # Handle later

        # Substitute variables in the prompt text
        substituted_prompt_text = self._substitute_variables(prompt_text)

        print(f"    Substituted Prompt: \"{substituted_prompt_text[:100]}{'...' if len(substituted_prompt_text)>100 else ''}\"")

        # Simulate LLM call
        # TODO: Actual LLM call will be implemented here
        mocked_response = f"Mocked LLM Response to: \"{substituted_prompt_text[:50]}...\""
        print(f"    Mocked LLM Response: \"{mocked_response}\"")

        # Store response in context if 'def' is specified
        if output_var_name:
            if not isinstance(output_var_name, str):
                raise PILSemanticError("Prompt step 'def' field must be a string (variable name).")
            self.context.set_variable(output_var_name, mocked_response)
            print(f"    Stored response in context variable: '{output_var_name}'")

        # Add to conversation history
        self.context.add_history_entry(role="user", content=substituted_prompt_text)
        self.context.add_history_entry(role="assistant", content=mocked_response)
        print(f"    Added user prompt and assistant response to history.")


    def run_workflow(self):
        if "workflow" not in self.program_data:
            raise PILSyntaxError("No 'workflow' block found in the PIL program.")
        if not isinstance(self.program_data["workflow"], dict):
            raise PILSyntaxError("'workflow' block must be a dictionary.")

        steps = self.program_data["workflow"].get("steps")
        if not steps:
            print("Warning: Workflow has no steps.")
            return
        if not isinstance(steps, list):
            raise PILSyntaxError("'steps' in workflow must be a list.")

        print("Starting PIL workflow execution...")
        for i, step_data in enumerate(steps):
            if not isinstance(step_data, dict) or len(step_data) != 1:
                # Each step should be a dictionary with a single key defining its type
                raise PILSemanticError(f"Step {i+1} in workflow is not a valid dictionary with a single type key. Found: {step_data}")

            step_type = list(step_data.keys())[0]
            step_config = step_data[step_type] # This is the dictionary of parameters for the step

            print(f"\nProcessing Step {i+1} (Type: {step_type}):")

            if step_type == "prompt":
                self._handle_prompt_step(step_config)
            elif step_type == "tool":
                print(f"  Content: {step_config}") # Placeholder
                # self._handle_tool_step(step_config)
            elif step_type == "code":
                print(f"  Content: {step_config}") # Placeholder
                # self._handle_code_step(step_config)
            elif step_type == "retrieve":
                print(f"  Content: {step_config}") # Placeholder
                # self._handle_retrieve_step(step_config)
            else:
                print(f"  Warning: Unknown step type '{step_type}' at step {i+1}. Content: {step_config}")

        print("\nPIL workflow execution finished.")
