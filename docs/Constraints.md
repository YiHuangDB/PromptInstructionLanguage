# Constraints in PIL

PIL provides a `constraints` mechanism to validate data, typically the output of `PromptStep` or the final output of the entire PIL program. This allows you to ensure that data conforms to expected formats, types, or specific rules.

If constraints are violated:
*   For a `PromptStep` with `max_retries > 0`, the step will attempt to re-prompt the LLM, providing feedback about the constraint failure.
*   For final program output (top-level `constraints`), if `config.max_program_retries > 0`, the entire workflow may be re-executed with error information provided as `pil_last_error_info`.
*   If retries are exhausted or not configured, a `ConstraintViolationError` is raised.

## Defining Constraints

Constraints are defined as a YAML dictionary. They can be applied in two main places:

1.  **`PromptStep` Constraints**: Applied to the string output received from the LLM.
    ```yaml
    - prompt:
        text: "Generate a JSON object with a 'name' (string) and 'age' (integer)."
        def: user_data
        constraints:
          type: object # Expecting a JSON string that can be parsed to an object
          # Further schema for the object can be implied or handled by custom validator
        max_retries: 1
    ```

2.  **Top-Level Program Constraints**: Applied to the final output of the PIL program (the value of the variable specified in the program's `output.from` field, or the result of the last step if `output.from` is not specified).
    ```yaml
    # At the root of the PIL file
    constraints:
      type: string
      regex: "^ReportGenerated: .+"

    output:
      from: final_report_string
    ```

## Supported Constraint Keys

The following keys can be used within a `constraints` dictionary:

*   **`type: <string>`**
    *   Specifies the expected data type of the value being validated.
    *   The validation logic will attempt to **coerce** the input value (which is often a string, especially from LLMs) into the specified type.
    *   Supported types and their coercion behavior:
        *   `string`: No coercion if already a string. Other types converted via `str()`.
        *   `integer`: Attempts `int()`.
        *   `number`: Attempts `float()`.
        *   `boolean`: Converts (case-insensitive) "true", "yes", "1", `True`, `1` to `True`. Converts "false", "no", "0", `False`, `0` to `False`. Other values raise a `ConstraintViolationError`.
        *   `list`: Expects a string that is valid JSON and represents a list. Uses `json.loads()`.
        *   `object`: Expects a string that is valid JSON and represents an object (dictionary). Uses `json.loads()`.
    *   If coercion is successful, the validated value (now potentially of a different type) is what proceeds. If coercion fails (e.g., trying to convert "abc" to `integer`), a `ConstraintViolationError` is raised.
    *   **Example**:
        ```yaml
        constraints:
          type: integer # LLM output "42" will become the integer 42
        ```

*   **`regex: <python_regex_pattern>`**
    *   A string containing a Python regular expression.
    *   The input value (after any type coercion, typically applied to strings) must match this pattern (using `re.match`, so it matches from the beginning of the string).
    *   **Example**:
        ```yaml
        constraints:
          type: string
          regex: "^ERROR_CODE_[0-9]{3}$" # Must be a string like "ERROR_CODE_123"
        ```

*   **`choices: List[str | int | float | bool]`** (Primarily tested with strings)
    *   A list of allowed literal values.
    *   The input value (after any type coercion) must be one of the values in this list.
    *   Comparison is direct equality. For strings, it's case-sensitive.
    *   **Example**:
        ```yaml
        constraints:
          type: string
          choices: ["red", "green", "blue"]
        ```

*   **`custom_validator: <module_path>:<function_name>`**
    *   A string specifying the Python module path and the name of a custom validation function to call.
    *   The module must be importable in the Python environment where the PIL engine is running.
    *   **Function Signature**: The custom validator function must have the following signature:
        `def my_validator_function(value: Any, context: Context) -> bool:`
        *   `value`: The value to validate (this will be after any `type` coercion defined in the same `constraints` block).
        *   `context`: The current PIL `Context` object, allowing the validator to access other context variables if needed for more complex validation logic.
        *   Return `True` if the value is valid, `False` otherwise.
    *   **Example**:
        *   PIL file:
            ```yaml
            constraints:
              type: integer
              custom_validator: "my_app.pil_validators:is_positive_even"
            ```
        *   `my_app/pil_validators.py`:
            ```python
            from pil_engine.core.context import Context # Assuming Context is accessible

            def is_positive_even(value: int, context: Context) -> bool:
                # 'value' will already be an int due to "type: integer" constraint
                return isinstance(value, int) and value > 0 and value % 2 == 0
            ```

## Order of Evaluation

When multiple constraint keys are present, they are typically evaluated in a fixed order (though this is an implementation detail and might evolve):
1.  `type` (coercion)
2.  `regex` (if value is string)
3.  `choices`
4.  `custom_validator`

If any constraint fails, the validation stops, and an error is raised or a retry is triggered.

## Combining with `OutputSchema`

*   Top-level program `constraints` are applied *after* `OutputSchema` validation.
*   This means `OutputSchema` first validates the structure and basic JSON types of the final output.
*   Then, the top-level `constraints` can apply further semantic rules (like regex, choices, or custom logic) to the already schema-validated output.
```
