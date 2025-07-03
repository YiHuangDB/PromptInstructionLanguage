# Prompt Instruction Language (PIL) - Formal Specification

This document provides the formal specification for the Prompt Instruction Language (PIL).
PIL is a YAML-based language for programming Large Language Models (LLMs) and orchestrating complex workflows.

## 1. Program Structure

A PIL program is a YAML document consisting of several top-level keys that define its configuration, behavior, and execution flow.

```yaml
# Optional: Global configuration for the PIL program
config:
  # ... see section 2.1

# Optional: Defines the persona the LLM should adopt
persona:
  # ... see section 2.2

# Optional: Declares input variables for the program
input:
  # ... see section 2.3

# Optional: Defines the JSON schema for the final program output
outputSchema:
  # ... see section 2.4

# Optional: Defines constraints to apply to the final program output
constraints:
  # ... see section 2.5

# Required: Defines the main sequence of steps to execute
workflow:
  # ... see section 3
```

## 2. Top-Level Components

### 2.1. `config`

*   **Purpose**: Specifies global settings for the PIL program, primarily related to LLM interactions.
*   **Syntax (YAML)**:
    ```yaml
    config:
      model: <string>
      api_key: <string>  # Optional, environment variable is preferred
      parameters:
        <parameter_name>: <value>
        # ...
    ```
*   **Attributes/Parameters**:
    *   `model`: (string) - Optional. The identifier of the LLM to be used (e.g., `"gpt-3.5-turbo"`, `"gpt-4o-mini"`). If not provided, steps requiring an LLM (like `prompt`) will raise a `ConfigurationError` unless an LLM client is already configured in the environment the interpreter is running in.
    *   `api_key`: (string) - Optional. The API key for the LLM service. **It is strongly recommended to set the API key via an environment variable (e.g., `OPENAI_API_KEY`) instead of directly in the PIL file.** If provided here, it will be used. If not provided here or in the environment, and a model is specified, a `ConfigurationError` will be raised.
    *   `parameters`: (object) - Optional. A dictionary of parameters to pass to the LLM API for every call (e.g., `temperature`, `max_tokens`). These can be overridden by step-specific parameters if the step type supports it (not currently implemented for `PromptStep`).
        *   Example: `parameters: { temperature: 0.7, max_tokens: 500 }`
*   **Behavior**:
    *   The `config` settings are used by the interpreter to initialize and configure the LLM client (currently `openai.AsyncOpenAI`).
    *   If `model` is specified but an `api_key` cannot be found (neither in `config` nor as `OPENAI_API_KEY` environment variable), the interpreter will raise a `ConfigurationError` upon initialization.
*   **Example**:
    ```yaml
    config:
      model: "gpt-4o-mini"
      parameters:
        temperature: 0.0
    ```

### 2.2. `persona`

*   **Purpose**: Defines the role, style, tone, and intended audience for the LLM, influencing its responses. This is typically sent as a system message to the LLM.
*   **Syntax (YAML)**:
    ```yaml
    persona:
      role: <string>
      style: <string>       # Optional
      tone: <string>        # Optional
      audience: <string>    # Optional
    ```
*   **Attributes/Parameters**:
    *   `role`: (string) - Optional. The primary role the LLM should adopt (e.g., `"Helpful AI Assistant"`, `"Sarcastic Commentator"`).
    *   `style`: (string) - Optional. The writing or communication style (e.g., `"concise"`, `"academic"`, `"narrative"`).
    *   `tone`: (string) - Optional. The emotional tone of the responses (e.g., `"formal"`, `"humorous"`, `"empathetic"`).
    *   `audience`: (string) - Optional. The intended audience for the LLM's responses (e.g., `"general public"`, `"software developers"`, `"children"`).
*   **Behavior**:
    *   If a `persona` is defined, the interpreter makes its attributes available in the context (under a special variable like `__persona__`, though this is an internal detail).
    *   `PromptStep` uses these attributes to construct a system message for the LLM API call.
*   **Example**:
    ```yaml
    persona:
      role: "资深法律分析师"
      style: "严谨"
      tone: "正式"
      audience: "法律专业人士"
    ```

### 2.3. `input`

*   **Purpose**: Declares the expected input variables for the PIL program, their names, and their expected types (for documentation and potential future type checking at program entry).
*   **Syntax (YAML)**:
    ```yaml
    input:
      vars:
        <variable_name_1>: <type_string> # Simple form
        <variable_name_2>:
          type: <type_string>
          description: <string>        # Optional
        # ... or as a list of objects:
      # vars:
      #   - name: <variable_name_3>
      #     type: <type_string>
      #     description: <string>        # Optional
    ```
*   **Attributes/Parameters**:
    *   `vars`: (object|list) - Required if `input` section is present. Defines the input variables.
        *   **As an object (dictionary)**: Keys are variable names, values are either a string representing the type (e.g., `"string"`, `"integer"`, `"boolean"`, `"list"`, `"object"`) or an object specifying `type` and optionally `description`.
        *   **As a list**: Each item is an object with `name` (string, required), `type` (string, required), and `description` (string, optional).
*   **Behavior**:
    *   When the interpreter's `run()` or `run_sync()` method is called with an `inputs` dictionary, it validates that all declared input variables are provided and that no unexpected variables are present.
    *   Missing required inputs will raise a `ValueError`.
    *   The types specified are currently for documentation; strict type checking and coercion of initial inputs based on these declarations are not yet implemented but may be in the future. Input variables are placed into the initial context.
*   **Example**:
    ```yaml
    input:
      vars:
        user_query: string
        max_items:
          type: integer
          description: "Maximum number of items to process."
        user_preferences: object
    ```

### 2.4. `outputSchema`

*   **Purpose**: Defines the expected JSON Schema structure for the final output of the PIL program's main workflow.
*   **Syntax (YAML)**:
    ```yaml
    outputSchema:
      schema:
        # Standard JSON Schema definition
        type: <string> # e.g., "object", "string", "array"
        properties:
          # ... if type is "object"
        required:
          # ... if type is "object"
        items:
          # ... if type is "array"
        # ... other JSON Schema keywords
    ```
*   **Attributes/Parameters**:
    *   `schema`: (object) - Required if `outputSchema` section is present. A valid JSON Schema object.
*   **Behavior**:
    *   After the main workflow completes, if `outputSchema.schema` is defined, the interpreter validates the final output against this schema using the `jsonschema` library.
    *   If validation fails, an `OutputValidationError` is raised.
    *   If the schema itself is malformed, an `InvalidSchemaError` is raised.
    *   The schema applies to the value determined as the final output (typically from the `def` of the last step, or as specified by a future `program.output.from` directive).
*   **Example**:
    ```yaml
    outputSchema:
      schema:
        type: object
        properties:
          summary:
            type: string
            description: "A concise summary of the result."
          details:
            type: array
            items:
              type: string
        required:
          - summary
    ```

### 2.5. Top-Level `constraints`

*   **Purpose**: Defines additional validation rules to apply to the final program output, *after* it has been validated against the `outputSchema` (if one is provided).
*   **Syntax (YAML)**:
    ```yaml
    constraints:
      type: <string>         # Optional (e.g., "string", "integer", "boolean", "list", "object")
      regex: <string>        # Optional, a Python regex pattern
      choices: <list>        # Optional, a list of allowed values
      custom_validator: <string> # Optional, e.g., "my_module:my_func"
    ```
*   **Attributes/Parameters**: See Section 4.1.6 (`Constraints Object`) for details on `type`, `regex`, `choices`, and `custom_validator`.
*   **Behavior**:
    *   These constraints are applied to the final output of the workflow. If an `outputSchema` was also applied, these constraints operate on the (potentially schema-validated) result.
    *   The `type` constraint here can perform type conversion (e.g., a string output `"123"` can be converted to an integer `123` if `type: integer` is specified).
    *   If any constraint fails, a `ConstraintViolationError` is raised.
*   **Example**:
    ```yaml
    # Assuming outputSchema might have ensured the output is a string
    constraints:
      regex: "^Final Answer: .+"
      # Ensures the final string output starts with "Final Answer: "
    ```

## 3. `workflow`

*   **Purpose**: Defines the sequence of operations (steps) to be executed by the PIL interpreter. This is the main logic block of a PIL program.
*   **Syntax (YAML)**:
    ```yaml
    workflow:
      steps:
        - <step_type_1>:
            # ... parameters for step_type_1
        - <step_type_2>:
            # ... parameters for step_type_2
        # ... more steps
    ```
*   **Attributes/Parameters**:
    *   `steps`: (list) - Required. A list of step definitions. Each item in the list represents a single step to be executed in order.
*   **Behavior**:
    *   The interpreter executes the steps in the `steps` list sequentially.
    *   The output of a step (if its `def` attribute is used) is placed into the context and can be used by subsequent steps for templating or as input values.
    *   The interpreter is asynchronous. Steps that involve I/O (like LLM calls or certain tools) are executed without blocking the main execution thread.
    *   The final output of the workflow is typically the result of the last step executed, or the result of the last step that defined a variable if no subsequent steps defined one. (This behavior might be further refined by a future `program.output.from` directive).

## 4. Steps

Steps are the individual units of execution within a `workflow`. Each step has a type (e.g., `prompt`, `code`, `tool`) and specific parameters.

### 4.1. Common Step Attributes

Most step types share some common attributes:

*   `def`: (string) - Optional.
    *   **Purpose**: Defines the name of a variable in the execution context where the output of this step will be stored.
    *   **Behavior**: If provided, the result of the step's execution is assigned to a context variable with this name. This variable can then be accessed by subsequent steps for templating (e.g., `{{ my_variable }}`) or as input to other operations. If omitted, the step executes for its side effects, but its direct output is not explicitly stored in a named context variable (though it might still be the implicit output of the workflow if it's the last step).
    *   **Example**: `def: "summary_text"`

### 4.1.6. Constraints Object (`constraints`)

The `constraints` object can be applied at the top level of the PIL program (see Section 2.5) or within specific steps (e.g., `PromptStep`).

*   **Purpose**: To validate and sometimes coerce the output of a step or the final program output.
*   **Syntax (YAML)**:
    ```yaml
    constraints:
      type: <string>         # Optional
      regex: <string>        # Optional
      choices: <list>        # Optional
      custom_validator: <string> # Optional, format "module_path:function_name"
    ```
*   **Attributes/Parameters**:
    *   `type`: (string) - Optional. Specifies the expected data type. If the value does not match, a `ConstraintViolationError` is raised. For some types, conversion is attempted:
        *   `"string"`: Converts the value to a string.
        *   `"integer"`: Attempts to convert the value to an integer (e.g., `"123"` -> `123`). Fails if conversion is not possible (e.g., `"abc"` or `"1.5"`).
        *   `"number"`: Attempts to convert the value to a float (e.g., `"123"` -> `123.0`, `"1.5"` -> `1.5`). Fails if conversion is not possible.
        *   `"boolean"`: Converts string values `"true"`, `"True"`, `"false"`, `"False"` to their boolean equivalents. Other strings or types will cause an error.
        *   `"list"`: Expects a JSON string that can be parsed into a list, or an actual list.
        *   `"object"`: Expects a JSON string that can be parsed into a dictionary (object), or an actual dictionary.
        *   If the specified `type` is unknown to the validator, a `PilEngineError` is raised.
    *   `regex`: (string) - Optional. A Python regular expression pattern. The value (converted to a string if not already) must match this pattern. If not, a `ConstraintViolationError` is raised.
    *   `choices`: (list) - Optional. A list of allowed values. The input value (after potential type conversion by the `type` constraint) must be one of the values in this list. If not, a `ConstraintViolationError` is raised. Comparison is direct equality.
    *   `custom_validator`: (string) - Optional. Specifies a custom Python validator function in the format `"path.to.module:function_name"`.
        *   The referenced function will be dynamically imported.
        *   It must be a callable that accepts two arguments: `(value: Any, context: Context)`.
        *   It should return `True` if validation passes.
        *   If it returns `False` or raises an exception, a `ConstraintViolationError` is raised by `apply_constraints`.
        *   Errors during import (module not found, function not found) will raise a `PilEngineError`.
*   **Behavior**:
    *   Constraints are applied in a specific order: `type` conversion/validation first, then `regex` (on the string representation if the original value wasn't a string or if type constraint converted it to one), then `choices` (on the potentially type-converted value), and finally `custom_validator`.
    *   The `apply_constraints` function in `pil_engine.validator` handles this logic.
    *   When applied to a `PromptStep`, if validation fails and `max_retries` is configured, a self-correction attempt is made.
*   **Example**:
    ```yaml
    constraints:
      type: "integer"
      choices: [1, 2, 3, 4, 5]
      # custom_validator: "my_validators:is_odd_or_zero" # Assumes my_validators.py exists
    ```

### 4.2. `PromptStep`

*   **Purpose**: Sends a constructed prompt to a Large Language Model (LLM) and retrieves its response. Supports templating, examples, persona integration, and output constraints with a self-correction mechanism.
*   **Syntax (YAML)**:
    ```yaml
    - prompt:
        text: <string_template>
        examples: # Optional
          - input: <string_template>
            output: <string_template>
          # ... more examples
        constraints: # Optional
          # ... see Constraints Object (Section 4.1.6)
        max_retries: <integer>  # Optional, default: 0
        def: <string_output_variable_name> # Optional
    ```
*   **Attributes/Parameters**:
    *   `text`: (string) - Required. The main prompt text to be sent to the LLM. Supports `{{variable}}` templating using values from the current context.
    *   `examples`: (list of objects) - Optional. A list of example interactions to provide few-shot learning context to the LLM. Each example object should have:
        *   `input`: (string) - The user part of the example. Supports templating.
        *   `output`: (string) - The assistant/LLM part of the example. Supports templating.
    *   `constraints`: (object) - Optional. A `Constraints` object (see Section 4.1.6) to validate and potentially coerce the LLM's string response.
    *   `max_retries`: (integer) - Optional. Default: `0`. The maximum number of times the step will attempt to re-prompt the LLM if the `constraints` validation fails. For each retry, a system message detailing the validation error is appended to the prompt.
    *   `def`: (string) - Optional. Common step attribute (see Section 4.1). Stores the validated (and potentially type-converted by constraints) LLM response.
*   **Behavior**:
    *   The `text`, example `input`s, and example `output`s are rendered using the current context.
    *   A system message is constructed if a `persona` is defined in the program.
    *   The rendered prompt, examples, and system message are sent to the configured LLM (currently via `openai.AsyncOpenAI().chat.completions.create`). This is an asynchronous, non-blocking call.
    *   If `constraints` are defined, the LLM's string response is validated against them.
        *   If validation passes, the (potentially type-converted) value is returned and stored if `def` is used.
        *   If validation fails:
            *   If `max_retries` > 0, a corrective message (including the validation error) is appended to the original user prompt, and the LLM call is retried. This counts as one retry attempt.
            *   If `max_retries` is reached and validation still fails, a `ConstraintViolationError` (from the last attempt) is raised.
    *   If an LLM API call fails due to connection issues, rate limits, authentication, or other API errors, it may be retried by the underlying HTTP client library (`openai` library's default retry mechanism) or may raise specific exceptions like `ConnectionError`, `PermissionError`, or `RuntimeError` that are wrapped from `openai` exceptions. If all LLM call attempts (including internal retries by the `openai` library and the step's `max_retries` for constraint validation) fail, the relevant error is propagated.
*   **Example**:
    ```yaml
    - prompt:
        text: "Summarize the following text: {{document_text}}"
        persona: # This would typically be a global persona
          role: "Concise Summarizer"
        examples:
          - input: "The quick brown fox jumps over the lazy dog."
            output: "A fox jumps over a dog."
        constraints:
          type: "string"
          custom_validator: "my_validators:is_under_100_chars"
        max_retries: 1
        def: "summary"
    ```

### 4.3. `RetrieveStep`

*   **Purpose**: Retrieves relevant documents or data from a specified knowledge source based on a query. Currently supports retrieval from local JSON files using basic keyword matching.
*   **Syntax (YAML)**:
    ```yaml
    - retrieve:
        from: <string_filepath_or_source_identifier>
        query: <string_template>
        k: <integer>  # Optional, default: 3
        def: <string_output_variable_name> # Optional
    ```
*   **Attributes/Parameters**:
    *   `from` (or `from_source` in component): (string) - Required. Specifies the source of the knowledge base. Currently, this should be a file path to a JSON file. The JSON file is expected to be a list of objects, where each object has at least an `"id"` and a `"content"` field.
    *   `query`: (string) - Required. The query string used to find relevant documents. Supports `{{variable}}` templating.
    *   `k`: (integer) - Optional. Default: `3`. The maximum number of documents to retrieve.
    *   `def`: (string) - Optional. Common step attribute (see Section 4.1). Stores the list of retrieved documents. Each document in the list is a dictionary containing the original document fields plus a `"score"` field.
*   **Behavior**:
    *   The `query` string is rendered using the current context.
    *   Knowledge bases specified in `from` are loaded by the interpreter during its initialization. If a KB fails to load, a warning is printed, and retrieval from that source will yield an empty list.
    *   The current retrieval mechanism performs basic keyword matching:
        *   Both the rendered query and the `"content"` field of each document in the specified knowledge base are tokenized (split into words, lowercased, punctuation removed).
        *   A score is calculated based on the number of common unique tokens between the query and the document content.
        *   Documents are sorted by this score in descending order.
    *   The top `k` documents are returned as a list of dictionaries. Each dictionary includes all original fields from the document in the JSON file, plus an added `"score"` field indicating the relevance score.
    *   If no documents match or the knowledge base is empty/unavailable, an empty list is returned.
    *   The execution of the retrieval logic itself (after KBs are loaded) is currently synchronous but is part of the overall `async` interpreter flow. If KBs were fetched from remote sources or involved heavy I/O per query, this step would need to be fully async or use `asyncio.to_thread`.
*   **Example**:
    ```yaml
    # Assumes 'my_documents.json' exists and is structured as:
    # [
    #   {"id": "doc1", "content": "Information about apples and oranges."},
    #   {"id": "doc2", "content": "Details about bananas and grapes."}
    # ]
    - retrieve:
        from: "./data/my_documents.json"
        query: "Details about {{fruit_type}}" # e.g., fruit_type = "bananas"
        k: 1
        def: "relevant_docs"
    ```

### 4.4. `ToolStep`

*   **Purpose**: Executes a predefined Python callable (tool) registered with the interpreter. Allows extending PIL capabilities with custom Python logic.
*   **Syntax (YAML)**:
    ```yaml
    - tool:
        name: <string_tool_name>
        args: # Optional
          <arg_name_1>: <value_or_string_template>
          <arg_name_2>: <value_or_string_template>
          # ...
        def: <string_output_variable_name> # Optional
    ```
*   **Attributes/Parameters**:
    *   `name`: (string) - Required. The name under which the tool was registered with the `Interpreter` instance (via `interpreter.register_tool()`).
    *   `args`: (object) - Optional. A dictionary of arguments to pass to the tool. Values can be literals (strings, numbers, booleans, lists, dicts) or string templates `{{variable}}` that will be rendered using the current context.
    *   `def`: (string) - Optional. Common step attribute (see Section 4.1). Stores the return value of the tool execution.
*   **Behavior**:
    *   Argument values in `args` that are strings are processed for `{{variable}}` templating. Non-string literal values (numbers, booleans, lists, dicts) are passed as is.
    *   The interpreter looks up `name` in its internal tool registry. If not found, a `ToolNotFoundException` is raised.
    *   The registered Python callable is executed with the (rendered) arguments.
        *   If the tool is a standard synchronous Python function (`def`), it is run in a separate thread pool executor (`asyncio.get_event_loop().run_in_executor(None, ...)`) to avoid blocking the asyncio event loop.
        *   If the tool is an asynchronous Python function (`async def`), it is `await`ed directly.
    *   If the tool execution raises a `TypeError` (e.g., due to mismatched arguments) or any other `Exception`, it is caught and re-raised as a `ToolExecutionError`, which includes the original exception.
    *   The return value of the tool callable is captured. If `def` is specified, this value is stored in the context.
*   **Example**:
    ```yaml
    # Assuming a Python tool 'calculate_sum' is registered with the interpreter:
    # def calculate_sum(val1: int, val2: int) -> int:
    #     return val1 + val2
    # interpreter.register_tool("calculate_sum", calculate_sum)

    - tool:
        name: "calculate_sum"
        args:
          val1: "{{previous_step_output}}" # Templated
          val2: 100                       # Literal
        def: "current_sum"
    ```

### 4.5. `CodeStep`

*   **Purpose**: Executes a block of arbitrary Python code within a sandboxed environment. Allows for custom data manipulation, logic, and interaction with context variables.
*   **Syntax (YAML)**:
    ```yaml
    - code:
        lang: python
        script: |
          # Your Python script here
          # To return a value, assign it to a variable named 'result'.
          # Example:
          # new_data = {{some_input_var}} * 2
          # result = {"transformed_data": new_data, "status": "processed"}
        def: <string_output_variable_name> # Optional
    ```
*   **Attributes/Parameters**:
    *   `lang`: (string) - Required. Specifies the scripting language. Currently, only `"python"` is supported. Other values will raise a `NotImplementedError`.
    *   `script`: (string) - Required. A string containing the Python code to execute. This is often a multi-line YAML string. Supports `{{variable}}` templating, which is resolved before the script is executed.
    *   `def`: (string) - Optional. Common step attribute (see Section 4.1). If provided, the value of the variable named `result` from the script's execution scope will be stored in the context under this name. If `result` is not defined in the script, `None` is stored.
*   **Behavior**:
    *   The `script` content is first rendered using the current context to resolve any `{{variable}}` templates.
    *   The rendered Python script is executed using `asteval`, which provides a sandboxed environment.
    *   All current context variables are available as global variables within the script's execution scope.
    *   The script can modify these context variables (if they are mutable types like lists or dicts, the changes will reflect in the main context due to `asteval`'s behavior with symbol tables passed by reference). However, direct reassignment of top-level context variables from within the script does not affect the outer context unless explicitly returned via the `result` variable and `def`.
    *   To pass a value out of the `CodeStep` and into the context via `def`, the script must assign the desired output to a variable named `result`.
    *   If the script execution raises an unhandled Python exception, it's caught, and a `ValueError` (wrapping the original error details) is raised by the interpreter.
    *   The execution of the `asteval.eval()` call (which is synchronous) is run in a separate thread pool executor (`asyncio.get_event_loop().run_in_executor(None, ...)`) to prevent blocking the main asyncio event loop if the script is long-running.
*   **Example**:
    ```yaml
    - code:
        lang: python
        script: |
          # Access context variables
          processed_items = []
          if isinstance({{items_list}}, list):
            for item in {{items_list}}:
              processed_items.append(str(item).upper() + "!")

          # Set the output for 'def'
          result = processed_items
        def: "uppercased_items"
    ```

### 4.6. `IfStep`

*   **Purpose**: Allows for conditional execution of a block of steps based on the evaluation of an expression.
*   **Syntax (YAML)**:
    ```yaml
    - if: <string_condition_expression>
      then:
        - <step_type_1>:
            # ...
        # ... more steps in 'then' branch
      else: # Optional
        - <step_type_2>:
            # ...
        # ... more steps in 'else' branch
      # 'def' is generally not used for IfStep itself, as its "output" is through the execution of its branches.
    ```
*   **Attributes/Parameters**:
    *   `if`: (string) - Required. A Python expression string that will be evaluated to determine the execution path. Supports `{{variable}}` templating, which is resolved before evaluation. The expression should evaluate to a boolean (`True` or `False`).
    *   `then`: (list) - Required. A list of steps to execute if the condition evaluates to `True`.
    *   `else`: (list) - Optional. A list of steps to execute if the condition evaluates to `False`.
    *   `def`: (string) - Optional. Common step attribute (see Section 4.1). While syntactically allowed, `IfStep` itself doesn't produce a direct output value to be stored. Its effect is through the execution of its branches. Any `def` on an `IfStep` will likely result in `None` being stored or the output of the last executed step within the chosen branch if that step had a `def` (this latter behavior is implicit and depends on how `_execute_workflow_steps` returns values). It's generally more useful to use `def` on steps *within* the `then` or `else` branches.
*   **Behavior**:
    *   The `if` condition string is rendered using the current context.
    *   The rendered expression is evaluated using a safe Python expression evaluator (`asteval.eval`). The evaluation context includes all current PIL context variables.
    *   The expression must evaluate to a boolean value (`True` or `False`). Non-boolean results will lead to a `TypeError`.
    *   If the condition is `True`, the steps in the `then` block are executed sequentially.
    *   If the condition is `False` and an `else` block is present, the steps in the `else` block are executed sequentially.
    *   If the condition is `False` and no `else` block is present, the `IfStep` completes without executing any further steps from its own definition.
    *   Steps within the `then` and `else` branches are executed asynchronously if they are I/O bound and handled as such (e.g., `PromptStep`, `ToolStep` calling a sync tool).
*   **Example**:
    ```yaml
    - if: "{{user_role}} == 'admin'"
      then:
        - prompt:
            text: "Admin action: {{admin_task_description}}"
            def: "admin_action_result"
      else:
        - prompt:
            text: "User action: {{user_task_description}}"
            def: "user_action_result"
    ```

### 4.7. `LoopStep`

*   **Purpose**: Provides iterative execution capabilities, allowing a block of steps to be run multiple times based on a collection, a range, or a condition.
*   **Syntax (YAML)**:
    *   **For-each loop**:
        ```yaml
        - for: <loop_var> in {{<collection_var>}} # e.g., "item in {{my_list}}"
          steps:
            - <step_type_1>:
                # ... steps to execute for each item
          def: <string_output_list_variable_name> # Optional
        ```
    *   **For-range loop**:
        ```yaml
        - for: <loop_var> in range(<start_or_stop_expr> [, <stop_expr> [, <step_expr>]]) # e.g., "i in range(5)" or "idx in range({{start}}, {{end}})"
          steps:
            - <step_type_1>:
                # ... steps to execute for each number in range
          def: <string_output_list_variable_name> # Optional
        ```
    *   **While loop**:
        ```yaml
        - while: <string_condition_expression> # e.g., "{{count}} < 10"
          steps:
            - <step_type_1>:
                # ... steps to execute while condition is true
          def: <string_output_list_variable_name> # Optional
        ```
    *   **Generic `loop` (parsed as `while`)**:
        ```yaml
        - loop: <string_condition_expression> # Parsed like 'while'
          steps:
            # ...
          def: <string_output_list_variable_name> # Optional
        ```

*   **Attributes/Parameters**:
    *   `for` (string): Used for for-each and for-range loops. Contains the loop expression.
        *   For-each: `"<loop_variable> in {{<collection_context_variable>}}"` (e.g., `"item in {{user_list}}"`)
        *   For-range: `"<loop_variable> in range(<args>)"` (e.g., `"i in range(5)"`, `"i in range(1, 10)"`, `"i in range(0, 10, 2)"`). Range arguments support `{{variable}}` templating.
    *   `while` (string): Used for while loops. Contains the conditional expression (e.g., `"{{items_processed}} < {{total_items}}"`). Supports `{{variable}}` templating. The expression should evaluate to a boolean.
    *   `loop` (string): An alternative way to define a `while` loop. The provided string is treated as the condition.
    *   `steps`: (list) - Required. A list of steps to be executed in each iteration of the loop.
    *   `def`: (string) - Optional. Common step attribute (see Section 4.1). If provided, the `LoopStep` will collect the output of the *last executed step within each iteration's `steps` block*. These collected outputs form a list, which is then stored in the context under the specified `def` variable name. If an iteration produces no explicit output from its last step (e.g., the last step has no `def`), `None` might be collected for that iteration.
*   **Behavior**:
    *   **General**:
        *   Steps within the loop are executed asynchronously if they are I/O bound and handled as such.
    *   **For-each (`for ... in {{collection}}`)**:
        *   The `collection_context_variable` is retrieved from the current context. It must be an iterable (e.g., list, tuple).
        *   For each item in the collection, a new, isolated context is created for the iteration, inheriting from the loop's entry context. The current item is available in this iteration context under the specified `<loop_var>` name.
        *   The `steps` block is executed within this iteration-specific context.
        *   Variables defined within one iteration (using `def` on steps inside the loop) are not directly visible to subsequent iterations or outside the loop, unless they modify shared mutable objects from the outer context (which is generally discouraged for clarity).
    *   **For-range (`for ... in range(...)`)**:
        *   Range arguments are rendered using context variables if templated, then evaluated. They must result in integers.
        *   Similar to for-each, each iteration gets an isolated context with the current range value available as `<loop_var>`.
    *   **While (`while condition` or `loop condition`)**:
        *   The condition expression is rendered and evaluated using the *current main context* (not an isolated one for the condition check itself) before each potential iteration.
        *   If `True`, the `steps` block is executed within the current main context. Variables defined or modified by steps within a `while` loop iteration directly affect the main context and are visible to subsequent iterations' condition checks and step executions.
        *   A safety break occurs if a `while` loop exceeds 1000 iterations.
    *   **Output Collection (`def`)**: If `def` is specified for the `LoopStep`, a list is accumulated. Each element in this list is the output of the *last step* executed within an iteration's `steps` block.
*   **Examples**:
    *   **For-each**:
        ```yaml
        - for: "user_item in {{user_data_list}}"
          steps:
            - prompt: { text: "Process {{user_item.name}}", def: "item_result" }
          def: "all_item_results"
        ```
    *   **For-range**:
        ```yaml
        - for: "i in range(1, {{max_iterations}} + 1)"
          steps:
            - code:
                lang: python
                script: "result = i * i"
                def: "squared_value"
          def: "all_squared_values"
        ```
    *   **While**:
        ```yaml
        # Initial context: counter = 0, max_count = 3
        - while: "{{counter}} < {{max_count}}"
          steps:
            - code: { lang: python, script: "print(f'Counter is {counter}'); result = counter + 1", def: "counter" } # counter is updated in main context
            - prompt: { text: "Iteration {{counter}} done. Next?", def: "iter_ack"} # iter_ack collected by loop
          def: "acknowledgements"
        ```
