# Prompt Instruction Language (PIL) - Formal Specification

This document will contain the formal specification for PIL, derived from the initial design report.
It will include:

*   Detailed grammar (e.g., in EBNF or similar notation).
*   Semantic rules for each language construct.
*   Execution model details.
*   Built-in functions and variables.
*   Type system (if applicable).

*(This is a placeholder and will be populated as the language design is finalized and implemented.)*

## Core Components (from Table 2 of the design document)

### `config`
*   **Purpose**: Global settings for the program.
*   **Key Attributes**: `model`, `api_key`, `parameters` (e.g., `temperature`).
*   **Example**: `config: { model: 'openai/gpt-4o-mini', temperature: 0.0 }`

### `persona`
*   **Purpose**: Defines the role the LLM should adopt.
*   **Key Attributes**: `role`, `style`, `tone`, `audience`.
*   **Example**: `persona: { role: '资深法律分析师', tone: '正式' }`

### `input`
*   **Purpose**: Declares input variables and their types.
*   **Key Attributes**: `vars: { name: type, ... }`.
*   **Example**: `input: { vars: { user_query: string, document_id: int } }`

### `outputSchema`
*   **Purpose**: Defines the structure of the final output.
*   **Key Attributes**: `schema: { ... }` (JSON Schema).
*   **Example**: `outputSchema: { schema: { type: 'object', properties: {...} } }`

### `workflow`
*   **Purpose**: The main block containing a sequence of steps.
*   **Key Attributes**: `steps: [ ... ]`.
*   **Example**: `workflow: { steps: [ ... ] }`

### `Step (prompt)`
*   **Purpose**: A single call to the LLM.
*   **Key Attributes**: `text`, `examples`, `def` (variable name for output).
*   **Example**: `- prompt: { text: "总结: ${doc}", def: "summary" }`

### `Step (retrieve)`
*   **Purpose**: RAG retrieval step.
*   **Key Attributes**: `from`, `query`, `k`, `def`.
*   **Example**: `- retrieve: { from: "vector_db", query: "${user_query}", k: 3, def: "context" }`

### `Step (tool)`
*   **Purpose**: Calls a predefined external tool.
*   **Key Attributes**: `name`, `args`, `def`.
*   **Example**: `- tool: { name: "weather_api", args: { city: "London" }, def: "forecast" }`

### `Step (code)`
*   **Purpose**: Executes embedded Python script.
*   **Key Attributes**: `lang`, `script`, `def`.
*   **Example**: `- code: { lang: 'python', script: 'result = x * 2', def: "doubled_x" }`

### `Step (control)`
*   **Purpose**: Control flow structures.
*   **Key Attributes**: `if`, `for`, `loop`.
*   **Example**: `- if: "${condition}" ...`

### `constraints`
*   **Purpose**: Rules applied to the generated output.
*   **Key Attributes**: `type`, `regex`, `choices`, `custom_validator`.
*   **Example**: `constraints: { choices: ["是", "否"] }`
