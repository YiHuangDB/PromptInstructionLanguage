# Prompt Instruction Language (PIL)

PIL is a domain-specific language (DSL) designed for programming Large Language Models (LLMs).
It aims to provide a robust, scalable, and maintainable framework for developing complex LLM applications,
moving beyond fragile, manual prompt crafting.

PIL uses a YAML-based declarative syntax for defining LLM interactions, combined with the ability
to embed imperative Python code for custom logic and tool integration.

## Core Features (Planned)

*   **Declarative Syntax**: Human-readable YAML for defining prompts, personas, and workflows.
*   **Imperative Logic**: Support for embedded Python blocks for complex data manipulation and custom tooling.
*   **First-class LLM Patterns**: Native support for RAG, Chain-of-Thought, ReAct-style agents, etc.
*   **Structured Output**: Define expected output schemas and enforce them.
*   **Developer Ecosystem**:
    *   Interpreter/Runtime
    *   IDE support (syntax highlighting, LSP for autocompletion, diagnostics)
    *   Debugging tools
*   **Advanced Capabilities**:
    *   Self-optimization (PIL Compiler)
    *   Security features (e.g., prompt injection mitigation)
    *   Observability integrations

## Project Structure

*   `pil_interpreter/`: Source code for the PIL interpreter.
*   `examples/`: Example PIL programs.
*   `docs/`: Documentation, including the PIL language specification.
*   `tests/`: Unit and integration tests.

## Getting Started (Future)

*(Instructions on how to install and use the PIL interpreter will be added here once it's functional.)*

This project is based on the design document: "构建提示指令语言（PIL）：一个用于大型语言模型编程的框架" (Building the Prompt Instruction Language (PIL): A Framework for Programming Large Language Models).
