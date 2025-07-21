# OutputSchema in PIL

The `outputSchema` component in a PIL program allows you to define a JSON Schema against which the final output of the program will be validated. This ensures that your PIL program produces data in the expected structure and format before it's passed to downstream systems or users.

## Defining `outputSchema`

The `outputSchema` is defined at the top level of your PIL program YAML file. It contains a single key, `schema`, whose value is a standard JSON Schema object (represented as a YAML dictionary).

**Syntax:**

```yaml
outputSchema:
  schema:
    type: <json_schema_type> # e.g., object, array, string, number, integer, boolean
    properties: # if type is object
      <property_name_1>:
        type: <json_schema_type>
        description: <string_description>
      <property_name_2>:
        # ... other property definitions
    required: [<required_property_1>, <required_property_2>] # if type is object
    items: # if type is array
      type: <json_schema_type_for_array_items>
    # ... any other valid JSON Schema keywords (e.g., minLength, pattern, enum, minimum, maximum, etc.)
```

## How it Works

1.  **Final Output Determination**: The PIL interpreter first determines the final output of the program.
    *   If an `output: {from: <variable_name>}` directive is present at the top level of the PIL program, the value of `<variable_name>` from the final context is considered the program's output.
    *   If no `output.from` directive is specified, the result of the very last step in the main workflow is considered the program's output.
    *   If the program has no workflow or the workflow produces no output, the output might be `None`.

2.  **Validation**:
    *   Once the final output value is determined, it is validated against the JSON Schema provided in `outputSchema.schema`.
    *   The validation is performed using the `jsonschema` Python library.

3.  **Error Handling**:
    *   **Schema Malformed**: If the schema defined under `outputSchema.schema` is itself not a valid JSON Schema document, the PIL interpreter will raise an `InvalidSchemaError` (which wraps the underlying `jsonschema.exceptions.SchemaError`) when it attempts to load/use the schema. This usually happens early in the program execution.
    *   **Output Validation Failure**: If the final program output fails to validate against a *valid* schema, a `jsonschema.exceptions.ValidationError` is raised by the interpreter.
    *   **Retries**: If `config.max_program_retries` is set to a value greater than 0, a `jsonschema.exceptions.ValidationError` will trigger a program-level retry. The error information (including details about the schema validation failure) will be injected into the context as `pil_last_error_info` for the next execution attempt. If all retries are exhausted, the final `jsonschema.exceptions.ValidationError` is re-raised.

## Example

Consider a PIL program that is expected to output a user's profile:

```yaml
config:
  model: "gpt-4o-mini"
  max_program_retries: 0 # No retries for this example

input:
  vars:
    user_id: string

workflow:
  steps:
    # ... steps to fetch or generate user_profile_data ...
    # For this example, let's assume a CodeStep produces it:
    - code:
        lang: python
        script: |
          if user_id == "123":
            result = {"name": "Alice", "age": 30, "is_active": True, "tags": ["dev", "python"]}
          else:
            result = {"name": "Unknown", "age": None, "is_active": False, "tags": []}
        def: user_profile_data

output:
  from: user_profile_data # Specifies what variable constitutes the final output

outputSchema:
  schema:
    type: object
    properties:
      name:
        type: string
        description: "User's full name"
      age:
        type: ["integer", "null"] # Age can be an integer or null
        minimum: 0
      is_active:
        type: boolean
      tags:
        type: array
        items:
          type: string
    required:
      - name
      - is_active
      # 'age' is not strictly required here due to "null" type,
      # but if present, must be integer or null.
```

**Behavior:**

*   If `user_id` is "123", `user_profile_data` will be `{"name": "Alice", "age": 30, "is_active": True, "tags": ["dev", "python"]}`. This will pass validation against the `outputSchema`.
*   If `user_id` is something else, `user_profile_data` will be `{"name": "Unknown", "age": None, "is_active": False, "tags": []}`. This will also pass (as `age` can be `null`, and it's not in `required` if we assume `null` means "not applicable/provided" which is different from missing a required field).
*   If the `CodeStep` produced `result = {"name": "Bob"}` (missing `is_active`), it would fail schema validation because `is_active` is in the `required` list. A `jsonschema.exceptions.ValidationError` would be raised.
*   If the `CodeStep` produced `result = {"name": "Eve", "age": "twenty", "is_active": True}`, it would fail because `age` ("twenty") is not an integer or null. A `jsonschema.exceptions.ValidationError` would be raised.

## Relationship with Top-Level `constraints`

If a PIL program defines both `outputSchema` and top-level `constraints`:
1.  The `outputSchema` validation is performed first on the final program output.
2.  If schema validation passes, the (potentially type-coerced by schema, though JSON schema validation itself doesn't coerce in Python's `jsonschema` library by default - PIL's `type` constraint does coercion) output is then validated against the top-level `constraints`.

This allows for a two-layered validation approach: structural validation with `outputSchema`, followed by more semantic or specific value constraints.
```
