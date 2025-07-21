# AGENTS.md - Notes for PIL Engine Developers

This document provides notes, conventions, and guidance for developers (human or AI agents like Jules) working on the PIL (Prompt-centric Imperative Language) engine codebase.

## Core Principles

1.  **Adhere to Design and Evolving Specifications**: While the initial design document ("构建提示指令语言（PIL）...") provides the foundation, the `docs/PIL_SPECIFICATION.md` (if present, or inline documentation/READMEs for features) will serve as the evolving formal specification. Development should align with this.
2.  **Follow the Plan**: Ensure all actions are part of an approved plan. If the plan needs adjustment, use the `set_plan` tool.
3.  **Incremental Development**: Implement features and create files incrementally. Prefer smaller, focused changes.
4.  **Test-Driven Development (TDD)**: Write tests before or alongside new functionality. Strive for good test coverage using the `unittest` framework. All new code paths should have corresponding tests.
5.  **Code Clarity and Maintainability**: Write clear, well-commented Python code following PEP 8 guidelines. PIL examples should be illustrative. Docstrings are essential for public APIs and complex internal functions.
6.  **Modularity**: Design components (steps, core logic, utilities) to be as modular and decoupled as possible.
7.  **Error Handling**: Implement robust error handling. Define and use custom exceptions from `pil_engine/exceptions.py`. For parsing errors intended for LSP diagnostics, use `PILParsingError` with location information.
8.  **Commit Messages**: Use conventional commit message formats (e.g., `feat: ...`, `fix: ...`, `docs: ...`, `test: ...`).
9.  **Security First**: Always consider the security implications of new features or changes, especially for steps that execute code (`CodeStep`) or interact with external systems/data (`PromptStep`, `RetrieveStep`, `ToolStep`). Refer to `SECURITY.md`.

## Working with PIL Files (`.pil`)

*   When creating or modifying PIL example files (`examples/*.pil`), ensure they conform to the current syntax and features of the engine.
*   Use examples to showcase new features and common usage patterns.

## Engine Development (`pil_engine/`)

*   **Parser (`pil_engine/interpreter.py:PilParser`, `pil_engine/core/components.py:parse_step` and `from_yaml` methods)**:
    *   Responsible for parsing YAML input into `PilProgram` objects and their constituent components.
    *   For LSP diagnostics, parsing logic (especially in `components.py`) needs to be location-aware if `is_lsp_parse=True` is passed, utilizing `ruamel.yaml` node attributes (`.lc`) and raising `PILParsingError` with line/column details.
*   **Interpreter (`pil_engine/interpreter.py:Interpreter`)**:
    *   Traverses the `PilProgram` AST (workflow steps).
    *   Manages the `ExecutionContext` (`pil_engine/core/context.py`).
    *   Executes step logic (e.g., LLM calls, code execution, tool calls).
*   **Components (`pil_engine/core/components.py`)**: Defines the structure of PIL programs and their steps (`PromptStep`, `CodeStep`, etc.).
*   **Context (`pil_engine/core/context.py`)**: Manages the state (variables) during a PIL program's execution.
*   **Utilities (`pil_engine/utils.py`)**: Contains helper functions like `render_template_string` (Jinja2-based) and `safe_eval_code_string` (`asteval`-based for conditions), and `sanitize_for_llm_prompt`.
*   **Validator (`pil_engine/validator.py`)**: Handles the application of `constraints`.

### `CodeStep` Specifics
*   **Sandboxing**: `CodeStep` scripts are executed within an `asteval` sandbox.
*   **Configuration**: The `asteval.Interpreter` is initialized with `minimal=False` but uses a custom `config` dictionary to enhance security.
    *   **Disabled by `asteval` default**: `import`, `importfrom`.
    *   **Explicitly Disabled by PIL Engine's `config` for `asteval`**: `functiondef` (no user-defined functions in script), `with`, `assert`, `raise` (no explicit `raise` statements by user script).
    *   **Allowed**: Common control flow (`if`, `for`, `while`), `try..except` blocks, expressions (including ternary `ifexp`), list/dict/set comprehensions, augmented assignments (`augassign`), f-strings (`formattedvalue`), and `print` (to `asteval`'s writer).
*   **Output**: To return a value from a `CodeStep`, assign it to a variable named `result` within the script.
*   **Context Access**: Scripts have read access to variables from the current PIL execution context. Modifications to mutable objects (like lists or dicts) from the context *will* persist.

### Retry Mechanisms & `pil_last_error_info`
*   **Program-Level Retries**: The `Interpreter.run()` method can retry the entire workflow if the final output fails `OutputSchema` validation or top-level `PilProgram.constraints`. This is controlled by `config.max_program_retries`.
*   **`PromptStep` Retries**: `PromptStep` can retry LLM calls if its output fails its own defined `constraints`. This is controlled by `step.max_retries`.
*   **`pil_last_error_info`**: When a retry occurs (either program-level or `PromptStep`), a string variable named `pil_last_error_info` is injected into the context for the *next* attempt. This variable contains details about the error that triggered the retry.
    *   Scripts (in `CodeStep` or templates in `PromptStep`) can check for this variable to adapt their behavior.
    *   Example check in a `CodeStep` script:
        ```python
        error_details = None
        is_retry = False
        try:
            if pil_last_error_info and isinstance(pil_last_error_info, str) and pil_last_error_info:
                error_details = pil_last_error_info
                is_retry = True
        except NameError:
            # pil_last_error_info is not defined (this is the first attempt)
            pass

        if is_retry:
            # Logic for retry, possibly using error_details
            result = "corrected_value based on: " + error_details[:50] # Example
        else:
            result = "initial_value_that_might_fail_validation"
        ```

## LSP Development (`pil_langserver/`)

*   The LSP server is built using `pygls`. Key file: `pil_langserver/server.py`.
*   **Diagnostics**:
    *   Uses `ruamel.yaml` (via `PilLanguageServer.yaml_parser`) for initial YAML loading to get precise line/column information.
    *   The `PilParser.parse_dict` method and component `from_yaml` methods are called with `is_lsp_parse=True` to enable location-aware error reporting.
    *   PIL-specific parsing errors should be raised as `PILParsingError` (from `pil_engine.exceptions`) containing `line`, `column`, and `node_text` attributes.
    *   The LSP's `_validate_document` function uses this information for precise diagnostics.
*   **Autocompletion**:
    *   Logic is in the `completions` handler in `server.py`.
    *   Relies on data structures like `TOP_LEVEL_KEYWORDS_DOC`, `STEP_TYPE_KEYWORDS_DOC`, `PARAM_DETAILS` for providing contextual suggestions with documentation.
    *   Context is determined by analyzing text around the cursor and using `_get_parent_key_info`.
*   **Hover**:
    *   Uses the `HOVER_DOCUMENTATION` dictionary in `server.py`. Keep this updated.
*   **Extending LSP**:
    *   To add new completions/hovers, update the respective data dictionaries.
    *   For more complex contextual logic, modify the `completions` or `hover` handlers.
    *   For new diagnostic capabilities related to PIL structure, ensure the core parser components raise `PILParsingError` appropriately.

## Adding New Step Types or Core Features

1.  **Define Components**: Add/modify data classes in `pil_engine/core/components.py`.
    *   Implement/update `from_yaml(cls, data, ..., is_lsp_parse=False)` methods. If `is_lsp_parse` is true, these methods *must* attempt to extract line/column info from `data` (expected to be a `ruamel.yaml` node) and raise `PILParsingError` for structure/type issues.
2.  **Update `parse_step`**: Modify the factory function in `pil_engine/core/components.py` to recognize and instantiate the new step, passing `is_lsp_parse` along.
3.  **Implement Interpreter Logic**: Add execution logic in `pil_engine/interpreter.py` (e.g., a new `_execute_new_step_type` method).
4.  **Update Type Hints**: Add new step to `StepType` Union in `components.py`.
5.  **LSP Support**:
    *   Add keywords, parameters, and documentation to relevant dictionaries in `pil_langserver/server.py`.
    *   Update autocompletion and hover logic if new contextual rules are needed.
6.  **Write Tests**: Add comprehensive tests in the `tests/` directory covering parsing, execution, error conditions, and LSP interactions if applicable.
7.  **Documentation**: Update `README.md`, `AGENTS.md`, `SECURITY.md`, and any detailed docs in the `docs/` folder.

## Testing Conventions

*   Use Python's `unittest` framework. Place tests in the `tests/` directory.
*   Test file names should start with `test_`.
*   Use `IsolatedAsyncioTestCase` for tests involving `async` interpreter methods.
*   Mock external dependencies (like `openai` client) where appropriate.
*   Cover valid cases, error conditions, edge cases.
*   Run all tests via `python -m unittest discover tests`.

By following these guidelines, we can ensure a smooth and efficient development process for PIL.
```
