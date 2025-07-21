# Prompt Instruction Language (PIL)

PIL is a domain-specific language (DSL) designed for programming Large Language Models (LLMs).
It aims to provide a robust, scalable, and maintainable framework for developing complex LLM applications,
moving beyond fragile, manual prompt crafting.

PIL uses a YAML-based declarative syntax for defining LLM interactions, combined with the ability
to embed imperative Python code for custom logic and tool integration.

## Core Concepts

*   **Workflow & Steps**: PIL programs define a `workflow` composed of a sequence of `steps`. Each step performs a specific action.
*   **Context**: A dictionary-like `context` is maintained throughout the workflow, allowing steps to pass data to subsequent steps. Variables are typically defined using the `def` key in a step.
*   **Templating**: Most string parameters within steps (like prompt text or tool arguments) support Jinja2-style templating (e.g., `{{ my_variable }}`) to access context variables.
*   **Persona**: Defines the role, style, and tone the LLM should adopt, influencing system prompts.
*   **Constraints & OutputSchema**: PIL allows defining constraints on step outputs and a JSON Schema for the final program output, enabling validation and self-correction loops.

## Key Features Implemented

*   **PIL Interpreter**: A Python-based runtime that executes PIL programs.
*   **Asynchronous Execution**: The interpreter core is asynchronous, allowing for non-blocking I/O operations (e.g., LLM calls, tool execution).
*   **Step Types**:
    *   `PromptStep`: Interacts with an LLM (currently OpenAI's API via `openai.AsyncOpenAI`). Supports templating, few-shot examples, persona integration, constraints on LLM output, and self-correction retries.
    *   `CodeStep`: Executes a sandboxed Python script using `asteval`. Useful for data manipulation and custom logic.
    *   `RetrieveStep`: Performs basic Retrieval Augmented Generation (RAG) by searching a local JSON file knowledge base based on keyword matching.
    *   `ToolStep`: Executes registered Python functions (tools) with templated arguments. Supports both synchronous and asynchronous tools.
    *   `IfStep`: Provides conditional execution of `then` and `else` branches based on an evaluated expression.
    *   `LoopStep`: Supports various loop constructs:
        *   `for item in {{collection}}`: Iterates over items in a context variable.
        *   `for i in range(...)`: Iterates over a numerical range (static or dynamic arguments).
        *   `while {{condition}}`: Executes steps as long as a condition is true.
        *   Loop variable scoping and optional result aggregation are supported.
*   **Context Management**: Variables defined by steps (using `def: var_name`) are added to the execution context.
*   **Constraints System**:
    *   Apply constraints (type, regex, choices, custom Python validators) to `PromptStep` outputs and the final program output.
    *   Supports type coercion for common types.
*   **Output Schema Validation**: Final program output can be validated against a user-defined JSON Schema specified in `outputSchema`.
*   **Self-Correction Loops**:
    *   `PromptStep`: Can retry LLM calls if its output fails defined constraints (`max_retries`).
    *   Program-Level: The entire workflow can be retried if the final output fails schema validation or top-level program constraints (`config.max_program_retries`). Error information is injected as `pil_last_error_info` for the retry.
*   **Language Server Protocol (LSP) Support (`pil_langserver/`)**:
    *   TextMate grammar (`pil.tmLanguage.yaml`) for syntax highlighting.
    *   Diagnostics for YAML syntax errors and PIL structural/validation errors (with improved location precision using `ruamel.yaml`).
    *   Autocompletion for top-level keys, step types, contextual step parameters, enum-like values (e.g., `lang: python`), and basic input variable suggestions in templates.
    *   Hover information providing documentation for PIL keywords, step types, and parameters.
*   **Security**:
    *   **CodeStep Sandboxing**: `asteval` is configured to restrict available Python features, disabling `import`, function definitions, `with`, `assert`, and `raise` statements in user scripts. `try..except` is allowed.
    *   **Prompt Injection Mitigation**: Basic sanitization for templated inputs in `PromptStep` and defensive augmentation of system prompts.
    *   See [SECURITY.md](SECURITY.md) for more details.

## Project Structure

*   `pil_engine/`: Source code for the PIL interpreter, core components, parser, and validator.
*   `pil_langserver/`: Source code for the Language Server Protocol implementation.
*   `examples/`: Example PIL programs (to be added).
*   `docs/`: Detailed documentation for features (to be added/expanded).
*   `tests/`: Unit and integration tests.
*   `SECURITY.md`: Security considerations and implemented mitigations.
*   `AGENTS.md`: Notes for developers contributing to the PIL engine.

## Basic Usage Example

Below is a conceptual example of a PIL program:

```yaml
# my_program.pil
config:
  model: "gpt-4o-mini" # Or your preferred model
  max_program_retries: 1

persona:
  role: "Concise Summarizer"
  tone: "formal"

input:
  vars:
    user_document: string

workflow:
  steps:
    - prompt:
        text: |
          Summarize the following document in one sentence:
          ---
          {{ user_document }}
          ---
          Summary:
        def: summary
        constraints:
          type: string
          # Could add a custom validator for conciseness

    - code:
        lang: python
        script: |
          # Example: Further process or log the summary
          print(f"LLM Summary: {summary}")
          result = {"final_summary": summary, "char_count": len(summary)}
        def: final_output_obj

outputSchema:
  schema:
    type: object
    properties:
      final_summary: {type: string}
      char_count: {type: integer}
    required: [final_summary, char_count]

constraints:
  # Example top-level constraint on the final output
  custom_validator: "my_validators:check_summary_length"
  # (assuming my_validators.py with check_summary_length(value, context) exists)
```

**Running a PIL Program (Python)**:

```python
from pil_engine.interpreter import PilParser, Interpreter
from pil_engine.utils import sanitize_for_llm_prompt # If manually constructing parts of prompts

# Load and parse the PIL program
parser = PilParser()
pil_program = parser.parse_yaml_file("my_program.pil")

# Initialize the interpreter
# OPENAI_API_KEY environment variable should be set for actual LLM calls
interpreter = Interpreter(pil_program, debug_mode=True)

# Define inputs
inputs = {
    "user_document": "The quick brown fox jumps over the lazy dog. It was a sunny day."
    # "pil_last_error_info": "..." # This is injected by the interpreter on retries
}

# Run the program (asynchronously)
# import asyncio
# final_result = asyncio.run(interpreter.run(inputs=inputs))

# Or run synchronously
final_result = interpreter.run_sync(inputs=inputs)

print(f"Final Program Output: {final_result}")
```

## Further Documentation

For more detailed information on specific features, please refer to the following:
*   **Core Concepts & Steps**:
    *   [PromptStep Guide](docs/steps/PromptStep.md)
    *   [LoopStep Guide](docs/steps/LoopStep.md)
    *   (Guides for CodeStep, RetrieveStep, ToolStep, IfStep to be added)
*   **Validation Features**:
    *   [Constraints System](docs/Constraints.md)
    *   [OutputSchema Validation](docs/OutputSchema.md)
*   **Security**:
    *   [Security Considerations](SECURITY.md)
*   **Development**:
    *   [Agent/Developer Notes](AGENTS.md)
*   (Full Language Specification in `docs/PIL_SPECIFICATION.md` - to be continuously updated)

This project is based on the design document: "构建提示指令语言（PIL）：一个用于大型语言模型编程的框架" (Building the Prompt Instruction Language (PIL): A Framework for Programming Large Language Models).
```
