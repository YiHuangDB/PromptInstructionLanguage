## Agent Collaboration Guidelines for PIL Development

This document provides guidelines for AI agents collaborating on the Prompt Instruction Language (PIL) project.

### General Principles

1.  **Adhere to the Design Document**: The primary source of truth for PIL's architecture, features, and philosophy is the "构建提示指令语言（PIL）：一个用于大型语言模型编程的框架" document. All development should align with this vision. The `docs/PIL_SPECIFICATION.md` will serve as the evolving formal specification.
2.  **Follow the Plan**: Ensure all actions are part of an approved plan. If the plan needs adjustment, use the `set_plan` tool.
3.  **Incremental Development**: Implement features and create files incrementally. Prefer smaller, focused changes.
4.  **Test-Driven Development (TDD)**: Where practical, write tests before or alongside new functionality. Strive for good test coverage.
5.  **Code Clarity and Maintainability**: Write clear, well-commented code. Python code should follow PEP 8 guidelines. PIL examples should be illustrative and easy to understand.
6.  **Modularity**: Design components of the interpreter (lexer, parser, evaluator) to be as modular and decoupled as possible.
7.  **Error Handling**: Implement robust error handling. Define and use custom exceptions from `pil_interpreter/exceptions.py` where appropriate.
8.  **Commit Messages**: Use conventional commit message formats (e.g., `feat: implement parser for config block`, `fix: resolve issue with variable substitution`).

### Working with PIL Files (`.pil`)

*   When creating or modifying PIL example files (`examples/*.pil`), ensure they conform to the syntax defined in `docs/PIL_SPECIFICATION.md` as it evolves.
*   Initially, focus on the core syntax. Advanced features (like complex Jinja filters or automatic self-correction loops) will be added progressively.

### Interpreter Development (`pil_interpreter/`)

*   **Lexer (`lexer.py`)**: Will be responsible for tokenizing the input YAML. Consider using `PyYAML`'s events or a custom regex-based approach if `PyYAML`'s direct parsing isn't suitable for AST construction.
*   **Parser (`parser.py`)**: Will construct an Abstract Syntax Tree (AST) from the token stream or YAML structure.
*   **Evaluator (`evaluator.py` or `interpreter.py`)**: Will traverse the AST, manage the `ExecutionContext`, and execute PIL program logic (e.g., make LLM calls, run code blocks).
*   **Context (`context.py`)**: Manages the state of a PIL program's execution, including variables.
*   **Main (`main.py`)**: The command-line interface for the interpreter.

### Dependencies

*   Use `requirements.txt` to manage Python dependencies.
*   Initially, `PyYAML` is the primary dependency. Add others as needed (e.g., `openai` for LLM API calls).

### Communication

*   Use `message_user` to provide updates, ask questions, or signal completion of tasks.
*   Use `request_user_input` if blocked or requiring clarification critical to proceeding.

By following these guidelines, we can ensure a smooth and efficient development process for PIL.
