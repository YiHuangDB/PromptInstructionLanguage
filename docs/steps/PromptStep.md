# PromptStep

The `PromptStep` is a core component in PIL for interacting with Large Language Models (LLMs). It allows you to define a prompt, provide few-shot examples, specify a persona for the LLM, set constraints on the output, and handle retries if the LLM's response doesn't meet the constraints.

## Syntax

```yaml
- prompt:
    text: <string_template>                  # Required
    def: <output_variable_name>            # Optional: Stores LLM response
    examples:                              # Optional: List of few-shot examples
      - input: <example_user_prompt_1>
        output: <example_assistant_response_1>
      - input: <example_user_prompt_2>
        output: <example_assistant_response_2>
    constraints:                           # Optional: Rules to validate LLM output
      type: <string|integer|number|boolean|list|object>
      regex: <python_regex_pattern>
      choices: [<value1>, <value2>]
      custom_validator: <module:function_name>
    max_retries: <integer>                 # Optional: Max retries if constraints fail (default: 0)
```

## Parameters

*   **`text: <string_template>` (Required)**
    *   The main prompt text to be sent to the LLM.
    *   Supports Jinja2-style templating (e.g., `{{ my_variable }}`) to insert values from the current PIL execution context.
    *   **Security Note**: String values from the context that are templated into the `text` field are automatically sanitized to mitigate common prompt injection risks. See [SECURITY.md](../../SECURITY.md) for details.

*   **`def: <output_variable_name>` (Optional)**
    *   If provided, the string response from the LLM (after passing any defined `constraints`) will be stored in the PIL context under this variable name.

*   **`examples: List[Dict[str, str]]` (Optional)**
    *   A list of dictionaries, each representing a few-shot example to guide the LLM.
    *   Each dictionary should have an `input` key (representing a user turn) and an `output` key (representing an assistant turn).
    *   These examples are typically prepended to the main prompt when communicating with the LLM.

*   **`constraints: Dict` (Optional)**
    *   Defines rules that the LLM's string output must satisfy. If constraints are violated, and `max_retries` is greater than 0, the `PromptStep` will attempt to re-prompt the LLM with information about the validation failure.
    *   Supported constraint keys:
        *   `type: <string>`: Specifies the expected data type of the LLM's response. Supported types:
            *   `string`: No conversion, value is used as is.
            *   `integer`: Attempts to convert the LLM string output to an integer.
            *   `number`: Attempts to convert the LLM string output to a float.
            *   `boolean`: Attempts to convert (case-insensitive) "true", "yes", "1" to `True`, and "false", "no", "0" to `False`.
            *   `list`: Attempts to `json.loads()` the LLM string output, expecting a JSON list.
            *   `object`: Attempts to `json.loads()` the LLM string output, expecting a JSON object (dictionary).
            If conversion fails, a `ConstraintViolationError` is raised. If successful, the defined variable (via `def`) will store the value in its converted type.
        *   `regex: <python_regex_pattern>`: A string containing a Python regular expression. The LLM output must match this pattern.
        *   `choices: List[str]`: A list of allowed string values. The LLM output must be one of these values.
        *   `custom_validator: <module:function_name>`: A string specifying a Python module and function to call for custom validation (e.g., `"my_validators:is_valid_email"`). The function signature should be `my_validator(value: Any, context: Context) -> bool`. It receives the (potentially type-coerced) value and the current PIL context. It should return `True` if valid, `False` otherwise.
    *   See [Constraints Documentation](../Constraints.md) for more details.

*   **`max_retries: <integer>` (Optional, Default: 0)**
    *   The maximum number of times the `PromptStep` should retry the LLM call if the response fails to meet the defined `constraints`.
    *   On each retry, the system attempts to provide feedback to the LLM about the nature of the constraint violation, encouraging it to produce a valid response.
    *   If all retries are exhausted and the output still fails validation, a `ConstraintViolationError` is raised.

## LLM Interaction

*   **Client**: Currently uses `openai.AsyncOpenAI`. Requires `OPENAI_API_KEY` environment variable or `api_key` in `config`.
*   **Model and Parameters**: Uses `model` and `parameters` (e.g., `temperature`) defined in the global `config` block of the PIL program.
*   **Message Construction**:
    1.  **System Prompt**: If a `Persona` is defined in the PIL program, its attributes (role, style, tone, audience) are used to construct a system message. This system message is augmented with a [defensive instruction](#defensive-system-prompt-augmentation) to mitigate prompt injection.
    2.  **Few-Shot Examples**: If `examples` are provided in the `PromptStep`, they are added to the message history as alternating user/assistant turns.
    3.  **User Prompt**: The rendered and sanitized `text` of the `PromptStep` is added as the final user message.
    4.  **Retry Feedback**: If a retry occurs due to a constraint violation, a system message detailing the error is added to the prompt for the subsequent LLM call to guide self-correction.

## Security

*   **Prompt Injection Mitigation**: As mentioned, string values from the context used in the `text` template are sanitized. The system prompt (if a `Persona` is used) is also augmented with defensive instructions. Please refer to [SECURITY.md](../../SECURITY.md) for comprehensive details and best practices for writing secure PIL prompts.

## Example

```yaml
config:
  model: "gpt-4o-mini"
  api_key: # Assumes OPENAI_API_KEY is in environment

persona:
  role: "Helpful Recipe Assistant"
  style: "friendly"
  tone: "encouraging"

input:
  vars:
    main_ingredient: string

workflow:
  steps:
    - prompt:
        text: "Suggest a simple recipe using {{main_ingredient}} as the main ingredient. The recipe name should be short."
        def: recipe_suggestion
        examples:
          - input: "Suggest a simple recipe using chicken."
            output: "Recipe Name: Lemon Herb Roasted Chicken\nInstructions: Season chicken with lemon, herbs, salt, pepper. Roast at 400F until cooked."
        constraints:
          type: string
          regex: "^Recipe Name: .+" # Ensure it starts with "Recipe Name: "
          custom_validator: "my_custom_validators:contains_ingredient"
          # (my_custom_validators.py would need contains_ingredient(value, context) that checks if main_ingredient is in value)
        max_retries: 1

    - code:
        lang: python
        script: |
          print(f"Suggested Recipe: {recipe_suggestion}")
          result = recipe_suggestion # Pass it on
        def: final_recipe
```

This example demonstrates templating, few-shot examples, constraints for the LLM output, and retries. The `custom_validator` would be a user-defined Python function.
```
