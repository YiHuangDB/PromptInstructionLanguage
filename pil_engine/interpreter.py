import yaml
import asteval # For CodeStep execution sandbox
from typing import Dict, Any, Optional, List, Callable # Added Callable

from .core.components import (
    PilProgram, parse_step, BaseStep, PromptStep, RetrieveStep, ToolStep, CodeStep, IfStep, LoopStep, StepType, LoopType
)
from .core.context import Context
from .utils import render_template_string, safe_eval_code_string
from .exceptions import ( # Import custom exceptions
    ToolNotFoundException, ToolExecutionError, OutputValidationError,
    InvalidSchemaError, ConfigurationError, ConstraintViolationError # Added ConstraintViolationError
)
from .validator import apply_constraints # Import the new function

import os
import openai
import re
import jsonschema

# --- Conceptual Debugging Strategy Notes for Interpreter ---
# (Already detailed in previous step, summarized here for context)
# 1. Trace-Based Debugging: Implemented with `debug_mode` and `trace_log`.
# 2. Domain-Specific Breakpoints: Conceptual, would require syntax and interpreter changes.
# 3. Unit Testing: Best practice, to be implemented with pytest and test PIL files.
# --- End Conceptual Debugging Notes ---

# It's good practice to load dotenv at the earliest point possible if used.
# from dotenv import load_dotenv
# load_dotenv() # This would typically be in the main entry point of an application using this library.
# For the library itself, we assume environment variables are already loaded or set.

class PilParser:
    """
    Parses PIL programs from YAML files or Python dictionaries into PilProgram objects.
    Uses PyYAML for YAML parsing and delegates to PilProgram.from_yaml for object construction.
    """
    def __init__(self):
        pass

    def parse_yaml_file(self, file_path: str) -> PilProgram:
        """
        Loads a PIL program from a specified YAML file path.

        Args:
            file_path: Path to the .pil YAML file.

        Returns:
            A PilProgram object.

        Raises:
            FileNotFoundError: If the PIL file is not found.
            ValueError: If there's an error parsing YAML or constructing the PilProgram.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f)
            if not isinstance(raw_data, dict): # PIL program root must be a YAML mapping
                raise ValueError("PIL program YAML root must be a dictionary (YAML mapping).")
            return PilProgram.from_yaml(raw_data, parse_step)
        except FileNotFoundError:
            # Re-raise specific error for clarity
            raise FileNotFoundError(f"PIL file not found: {file_path}")
        except yaml.YAMLError as e:
            # Wrap YAML parsing errors
            raise ValueError(f"Error parsing PIL YAML file '{file_path}': {e}")
        except Exception as e:
            # Catch-all for other errors during PilProgram construction
            raise ValueError(f"Unexpected error creating PilProgram from YAML in '{file_path}': {e}")

    def parse_dict(self, data: Dict[str, Any]) -> PilProgram:
        """
        Parses a PIL program from an existing Python dictionary.

        Args:
            data: A Python dictionary representing the PIL program structure.

        Returns:
            A PilProgram object.

        Raises:
            ValueError: If data is not a dictionary or if there's an error constructing PilProgram.
        """
        if not isinstance(data, dict):
            raise ValueError("PIL program data must be a dictionary.")
        try:
            # parse_step is passed to handle recursive parsing of steps within workflow/if/loop
            return PilProgram.from_yaml(data, parse_step)
        except Exception as e:
            # Catch-all for errors during PilProgram construction from dict
            raise ValueError(f"Unexpected error creating PilProgram from dictionary: {e}")


class Interpreter:
    """
    Interprets and executes a parsed PilProgram.

    The Interpreter manages the execution context, handles step dispatching,
    simulates LLM calls, tool usage, and retrieval, and supports basic
    trace logging for debugging.
    """
    def __init__(self, pil_program: PilProgram,
                 initial_vars: Optional[Dict[str, Any]] = None,
                 debug_mode: bool = False):
        """
        Initializes the Interpreter.

        Args:
            pil_program: The PilProgram object to execute.
            initial_vars: An optional dictionary of initial variables for the context.
            debug_mode: If True, enables trace logging during execution.
        """
        if not isinstance(pil_program, PilProgram):
            raise TypeError("pil_program must be an instance of PilProgram.")
        self.pil_program: PilProgram = pil_program
        self.context: Context = Context(initial_vars=initial_vars)
        self.llm_client: Any = None
        self.debug_mode: bool = debug_mode
        self.trace_log: List[Dict[str, Any]] = [] if self.debug_mode else None
        self.knowledge_bases: Dict[str, List[Dict[str, Any]]] = {}
        self.tool_registry: Dict[str, Callable] = {} # Added tool registry

        self._initialize_llm_client()
        self._load_all_knowledge_bases()

    def register_tool(self, name: str, tool_callable: Callable):
        """Registers a tool (Python callable) with the interpreter."""
        if not isinstance(name, str) or not name:
            raise ValueError("Tool name must be a non-empty string.")
        if not callable(tool_callable):
            raise TypeError(f"Tool '{name}' must be a callable Python function or method.")
        if name in self.tool_registry:
            print(f"Interpreter Warning: Tool '{name}' is being re-registered. Overwriting previous definition.")
        self.tool_registry[name] = tool_callable
        self._add_trace_log("TOOL_REGISTERED", tool_name=name, callable_info=str(tool_callable))
        print(f"Interpreter: Tool '{name}' registered.")


    def _add_trace_log(self, event_type: str, **kwargs):
        """Adds a structured entry to the trace log if debug_mode is enabled."""
        if self.debug_mode:
            log_entry = {"event": event_type, **kwargs}
            self.trace_log.append(log_entry)
            # For immediate feedback during development, also print the trace.
            # In a production tool, this might be written to a file or handled by a logger.
            print(f"    TRACE: {log_entry}")


    def _initialize_llm_client(self):
        """
        Initializes the LLM client based on the PIL program's config and environment variables.
        Prioritizes API key from `config.api_key`, then environment variable `OPENAI_API_KEY`.
        """
        config = self.pil_program.config
        model_name = config.model if config else None
        api_key_from_config = config.api_key if config else None

        if not model_name:
            self._add_trace_log("LLM_CLIENT_INIT_SKIPPED", reason="No model specified in PIL config.")
            print("Interpreter: LLM client not initialized: No model specified in PIL program config.")
            self.llm_client = None
            return

        # For now, assuming all models are OpenAI compatible if a model is specified.
        # Future: Add logic to determine client type based on model_name or a provider field.

        api_key = api_key_from_config or os.environ.get("OPENAI_API_KEY")

        if not api_key:
            error_msg = f"API key not found in config or environment (OPENAI_API_KEY) for model '{model_name}'."
            self._add_trace_log("LLM_CLIENT_INIT_FAILED", model=model_name, reason=error_msg)
            # Raise ConfigurationError here if strict initialization is desired,
            # otherwise _execute_prompt_step will handle it if self.llm_client is None.
            # Let's make it strict: if a model is specified, a key must be found for client init.
            self.llm_client = None
            raise ConfigurationError(error_msg)

        try:
            self.llm_client = openai.OpenAI(api_key=api_key)
            # We might want to add a check here to see if the client is functional,
            # e.g., by listing models, but that's an actual API call.
            # For now, instantiation is enough for this step.
            self._add_trace_log("LLM_CLIENT_INIT_SUCCESS", model=model_name, client_type="OpenAI")
            print(f"Interpreter: OpenAI LLM Client Initialized for model '{model_name}'.")
        except Exception as e:
            self.llm_client = None
            self._add_trace_log("LLM_CLIENT_INIT_ERROR", model=model_name, error=str(e))
            print(f"Interpreter: Error initializing OpenAI client for model '{model_name}': {e}")

    def _load_knowledge_base(self, file_path: str) -> List[Dict[str, Any]]:
        """Loads a single JSON knowledge base file."""
        try:
            # Consider security implications if file_path can be arbitrary.
            # For now, assume it's a trusted path from the PIL program.
            # Resolve relative paths if necessary, e.g., relative to PIL program location or CWD.
            # Current CWD is default for open().
            with open(file_path, 'r', encoding='utf-8') as f:
                kb_data = yaml.safe_load(f) # Using yaml.safe_load for consistency, works for JSON too
            if not isinstance(kb_data, list):
                raise ValueError(f"Knowledge base file '{file_path}' must contain a JSON list of documents.")
            for doc in kb_data:
                if not isinstance(doc, dict) or "id" not in doc or "content" not in doc:
                    raise ValueError(f"Invalid document structure in '{file_path}'. Each doc needs 'id' and 'content'. Document: {doc}")
            self._add_trace_log("KB_LOAD_SUCCESS", source=file_path, num_docs=len(kb_data))
            print(f"Interpreter: Knowledge Base '{file_path}' loaded with {len(kb_data)} documents.")
            return kb_data
        except FileNotFoundError:
            self._add_trace_log("KB_LOAD_ERROR", source=file_path, error="File not found")
            raise FileNotFoundError(f"Knowledge base file not found: {file_path}")
        except (yaml.YAMLError, ValueError) as e: # Catch JSON parsing errors or our ValueErrors
            self._add_trace_log("KB_LOAD_ERROR", source=file_path, error=str(e))
            raise ValueError(f"Error loading or parsing knowledge base '{file_path}': {e}")
        except Exception as e:
            self._add_trace_log("KB_LOAD_ERROR", source=file_path, error=f"Unexpected error: {str(e)}")
            raise RuntimeError(f"Unexpected error loading knowledge base '{file_path}': {e}")

    def _collect_kb_sources_from_steps(self, steps: List[StepType]) -> set[str]:
        """Recursively collects all unique 'from_source' paths from RetrieveSteps."""
        sources = set()
        for step in steps:
            if isinstance(step, RetrieveStep):
                sources.add(step.from_source)
            elif isinstance(step, IfStep):
                sources.update(self._collect_kb_sources_from_steps(step.then_steps))
                sources.update(self._collect_kb_sources_from_steps(step.else_steps))
            elif isinstance(step, LoopStep):
                sources.update(self._collect_kb_sources_from_steps(step.steps))
        return sources

    def _load_all_knowledge_bases(self):
        """Loads all knowledge bases specified in RetrieveSteps within the program."""
        if not self.pil_program.workflow or not self.pil_program.workflow.steps:
            return

        kb_sources = self._collect_kb_sources_from_steps(self.pil_program.workflow.steps)

        for source_path in kb_sources:
            if source_path not in self.knowledge_bases: # Avoid reloading if already loaded (e.g. by a previous call or manual setup)
                try:
                    self.knowledge_bases[source_path] = self._load_knowledge_base(source_path)
                except Exception as e:
                    # Decide on error handling: warn, or raise immediately?
                    # Raising immediately makes misconfiguration obvious.
                    print(f"Interpreter Warning: Failed to load knowledge base '{source_path}': {e}. Retrieval from this source will fail.")
                    # Optionally, re-raise to halt if a KB is critical: raise
                    # For now, let it proceed and fail at RetrieveStep if source is missing.
                    self.knowledge_bases[source_path] = None # Mark as failed to load

    def _validate_inputs(self, provided_inputs: Dict[str, Any]):
        """
        Validates provided inputs against the PIL program's input schema.
        Populates the context with valid inputs.

        Args:
            provided_inputs: A dictionary of input names to values.

        Raises:
            ValueError: If validation fails (e.g., unexpected or missing inputs).
        """
        if not self.pil_program.input or not self.pil_program.input.vars:
            if provided_inputs:
                self._add_trace_log("INPUT_VALIDATION", status="No inputs defined in PIL, but inputs provided.", provided=list(provided_inputs.keys()))
                print("Interpreter Warning: PIL program does not define any inputs, but inputs were provided.")
            return

        defined_input_vars = {var.name: var for var in self.pil_program.input.vars}
        for name, value in provided_inputs.items():
            if name not in defined_input_vars:
                err_msg = f"Unexpected input variable '{name}' provided. Defined inputs: {list(defined_input_vars.keys())}"
                self._add_trace_log("INPUT_VALIDATION_ERROR", error=err_msg)
                raise ValueError(err_msg)
            self.context.set_variable(name, value)
            self._add_trace_log("INPUT_SET", variable=name, value=value)


        for name, var_def in defined_input_vars.items():
            if not self.context.has_variable(name):
                err_msg = f"Missing required input variable '{name}'."
                self._add_trace_log("INPUT_VALIDATION_ERROR", error=err_msg)
                raise ValueError(err_msg)
        self._add_trace_log("INPUT_VALIDATION", status="Inputs validated successfully.", inputs_in_context=list(provided_inputs.keys()))


    def _execute_step(self, step_obj: BaseStep, step_index: int, total_steps: int) -> Any:
        """Dispatcher for different step types."""
        step_type_name = step_obj.__class__.__name__

        self._add_trace_log("PRE_STEP_EXECUTION", step_number=f"{step_index+1}/{total_steps}", type=step_type_name, definition=str(step_obj),
                            current_context_keys=list(self.context.get_all_variables().keys()))
        print(f"  Executing {step_type_name}: {step_obj}")

        # Conceptual: Check for debug breakpoint
        # if hasattr(step_obj, 'debug') and step_obj.debug:
        #     self._handle_breakpoint(step_obj)

        output = None
        if isinstance(step_obj, PromptStep):
            output = self._execute_prompt_step(step_obj)
        elif isinstance(step_obj, RetrieveStep):
            output = self._execute_retrieve_step(step_obj)
        elif isinstance(step_obj, ToolStep):
            output = self._execute_tool_step(step_obj)
        elif isinstance(step_obj, CodeStep):
            output = self._execute_code_step(step_obj)
        elif isinstance(step_obj, IfStep):
            self._execute_if_step(step_obj)
        elif isinstance(step_obj, LoopStep):
            output = self._execute_loop_step(step_obj)
        else:
            raise TypeError(f"Unknown step type: {step_type_name}")

        self._add_trace_log("POST_STEP_EXECUTION", step_number=f"{step_index+1}/{total_steps}", type=step_type_name, raw_output=str(output))

        if step_obj.def_var:
            self.context.set_variable(step_obj.def_var, output)
            self._add_trace_log("CONTEXT_SET", variable=step_obj.def_var, value=str(output))
            print(f"    - Defined variable: {step_obj.def_var} = {output}")
        return output

    def _execute_prompt_step(self, step: PromptStep) -> str:
        template_text = step.text
        context_vars = self.context.get_all_variables()

        persona_info = self.context.get_variable("__persona__", None)
        full_prompt_parts = []
        if persona_info:
            full_prompt_parts.append(f"Persona: {persona_info.role} ({persona_info.style}, {persona_info.tone})")

        if step.examples:
            example_texts = [f"Example Input: {ex.get('input', '')}\nExample Output: {ex.get('output', '')}" for ex in step.examples]
            if example_texts:
                 full_prompt_parts.append("Examples:\n" + "\n---\n".join(example_texts))

        rendered_text = render_template_string(template_text, context_vars)
        self._add_trace_log("TEMPLATE_RENDERED", step_type="PromptStep", original_text=template_text, rendered_text=rendered_text)
        full_prompt_parts.append(f"Prompt: {rendered_text}")

        final_prompt_for_llm = "\n\n".join(full_prompt_parts)
        print(f"    - Rendered Prompt for LLM: \n\"{final_prompt_for_llm}\"")

        if self.llm_client is None:
            # This will now typically not be hit if _initialize_llm_client raises ConfigurationError first.
            # However, it's a good safeguard if client somehow becomes None later or init logic changes.
            error_message = "LLM client is not available for PromptStep. Check API key and model configuration."
            self._add_trace_log("LLM_CALL_FAILED", reason=error_message)
            raise ConfigurationError(error_message)

        # Construct messages for OpenAI API
        messages = []
        persona_obj = self.context.get_variable("__persona__", None) # Already fetched earlier for constructing final_prompt_for_llm
        if persona_obj and persona_obj.role: # Assuming persona.role maps to system message content
            # A more complex persona might need specific formatting. For now, use role, style, tone.
            system_content = f"Role: {persona_obj.role}"
            if persona_obj.style: system_content += f", Style: {persona_obj.style}"
            if persona_obj.tone: system_content += f", Tone: {persona_obj.tone}"
            if persona_obj.audience: system_content += f", Audience: {persona_obj.audience}"
            messages.append({"role": "system", "content": system_content})

        for example in step.examples:
            if "input" in example and "output" in example:
                messages.append({"role": "user", "content": example["input"]})
                messages.append({"role": "assistant", "content": example["output"]})

        messages.append({"role": "user", "content": rendered_text}) # The main prompt

        try:
            self._add_trace_log("LLM_API_CALL_START", model=self.pil_program.config.model, messages=messages, parameters=self.pil_program.config.parameters)
            print(f"    - Making API call to OpenAI model: {self.pil_program.config.model} with params: {self.pil_program.config.parameters}")

            completion = self.llm_client.chat.completions.create(
                model=self.pil_program.config.model,
                messages=messages,
                **self.pil_program.config.parameters # Pass parameters like temperature, max_tokens
            )

            llm_response_content = completion.choices[0].message.content
            self._add_trace_log("LLM_API_CALL_SUCCESS", response_id=completion.id, finish_reason=completion.choices[0].finish_reason, usage=completion.usage)
            print(f"    - LLM Response received. Finish reason: {completion.choices[0].finish_reason}")

        except openai.APIConnectionError as e:
            err_msg = f"OpenAI API request failed to connect: {e}"
            self._add_trace_log("LLM_API_CALL_ERROR", error_type="APIConnectionError", error_message=str(e))
            raise ConnectionError(err_msg) from e
        except openai.RateLimitError as e:
            err_msg = f"OpenAI API request exceeded rate limit: {e}"
            self._add_trace_log("LLM_API_CALL_ERROR", error_type="RateLimitError", error_message=str(e))
            raise PermissionError(err_msg) from e # Or a custom RateLimitError
        except openai.AuthenticationError as e:
            err_msg = f"OpenAI API authentication failed: {e}. Check your API key."
            self._add_trace_log("LLM_API_CALL_ERROR", error_type="AuthenticationError", error_message=str(e))
            raise PermissionError(err_msg) from e
        except openai.APIStatusError as e: # Catch other API errors
            err_msg = f"OpenAI API returned an error status {e.status_code}: {e.response}"
            self._add_trace_log("LLM_API_CALL_ERROR", error_type="APIStatusError", status_code=e.status_code, error_message=str(e.response))
            raise RuntimeError(err_msg) from e
        except Exception as e: # Catch any other unexpected errors during API call
            err_msg = f"An unexpected error occurred during OpenAI API call: {e}"
            self._add_trace_log("LLM_API_CALL_ERROR", error_type="UnexpectedError", error_message=str(e))
            raise RuntimeError(err_msg) from e

        if step.constraints:
            self._add_trace_log("CONSTRAINT_VALIDATION_START", step_type="PromptStep", constraints=step.constraints, value_to_validate=llm_response_content)
            print(f"    - Applying constraints to LLM output: {step.constraints}")
            try:
                validated_output = apply_constraints(
                    value=llm_response_content,
                    constraints=step.constraints, # This is a Constraints object
                    context=self.context,
                    step_name=f"PromptStep (def: {step.def_var or 'N/A'})" # More context for error
                )
                self._add_trace_log("CONSTRAINT_VALIDATION_SUCCESS", validated_output=str(validated_output))
                print("    - Constraint validation successful.")
                return validated_output # Return potentially type-converted and validated output
            except ConstraintViolationError as e:
                self._add_trace_log("CONSTRAINT_VALIDATION_FAILED", error=str(e))
                # Re-raise, or handle for self-correction loop in future
                raise e

        return llm_response_content

    def _execute_retrieve_step(self, step: RetrieveStep) -> List[Dict[str, Any]]:
        context_vars = self.context.get_all_variables()
        rendered_query = render_template_string(step.query, context_vars)
        self._add_trace_log("TEMPLATE_RENDERED", step_type="RetrieveStep", original_query=step.query, rendered_query=rendered_query)
        print(f"    - Retrieval: from='{step.from_source}', query='{rendered_query}', k={step.k}")

        knowledge_base = self.knowledge_bases.get(step.from_source)
        if knowledge_base is None:
            # This means KB failed to load or wasn't specified correctly.
            # _load_all_knowledge_bases would have printed a warning.
            self._add_trace_log("RETRIEVAL_FAILED", source=step.from_source, query=rendered_query, reason="Knowledge base not loaded or unavailable.")
            print(f"    - WARNING: Knowledge base '{step.from_source}' not loaded. Returning empty list for retrieval.")
            return []

        if not knowledge_base: # Empty KB
            self._add_trace_log("RETRIEVAL_EMPTY_KB", source=step.from_source, query=rendered_query)
            return []
        # Simple keyword matching
        # Ensure tokenize is indented correctly within _execute_retrieve_step
        def tokenize(text: str) -> set[str]:
            if not isinstance(text, str): # Handle non-string input to tokenize gracefully
                text = str(text)
            text = re.sub(r'[^\w\s]', '', text) # Remove punctuation
            return set(word for word in text.lower().split() if word) # Filter out empty strings from multiple spaces

        query_tokens = tokenize(rendered_query)

        scored_documents = []
        for doc in knowledge_base:
            doc_content = doc.get("content", "")
            # Tokenization will handle non-string conversion if needed, but good to ensure content is primarily string
            # if not isinstance(doc_content, str):
            #     doc_content = str(doc_content)

            doc_tokens = tokenize(doc_content)
            common_tokens = query_tokens.intersection(doc_tokens)
            score = len(common_tokens) # Simple count of common unique keywords

            if score > 0:
                # Return a copy of the doc to avoid modifying the cached KB, add score
                retrieved_doc_item = doc.copy()
                retrieved_doc_item["score"] = float(score)
                scored_documents.append(retrieved_doc_item)

        # Sort by score descending
        scored_documents.sort(key=lambda x: x["score"], reverse=True)

        results = scored_documents[:step.k]

        self._add_trace_log("RETRIEVAL_EXECUTED", source=step.from_source, query=rendered_query, k=step.k, result_count=len(results), total_matches_before_k=len(scored_documents))
        return results

    def _execute_tool_step(self, step: ToolStep) -> Any:
        context_vars = self.context.get_all_variables()

        # Render argument values from context
        rendered_args = {}
        for arg_name, val_template in step.args.items():
            if isinstance(val_template, str):
                rendered_args[arg_name] = render_template_string(val_template, context_vars)
            else: # Pass non-string args (like numbers, booleans from YAML) as is
                rendered_args[arg_name] = val_template

        self._add_trace_log("TOOL_ARGS_RENDERED", step_type="ToolStep", tool_name=step.name, original_args=step.args, rendered_args=rendered_args)
        print(f"    - Tool Call: name='{step.name}', args={rendered_args}")

        if step.name not in self.tool_registry:
            error_msg = f"Tool '{step.name}' not found in registry. Available tools: {list(self.tool_registry.keys())}"
            self._add_trace_log("TOOL_CALL_ERROR", tool_name=step.name, reason="Tool not found")
            raise ToolNotFoundException(error_msg, tool_name=step.name, available_tools=list(self.tool_registry.keys()))

        tool_callable = self.tool_registry[step.name]

        try:
            self._add_trace_log("TOOL_EXECUTION_START", tool_name=step.name, args_passed=rendered_args)
            tool_output = tool_callable(**rendered_args)
            self._add_trace_log("TOOL_EXECUTION_SUCCESS", tool_name=step.name, output=str(tool_output))
            print(f"    - Tool '{step.name}' executed successfully.")
            return tool_output
        except TypeError as e:
            error_msg = f"Type error while calling tool '{step.name}' with args {rendered_args}: {e}"
            self._add_trace_log("TOOL_EXECUTION_ERROR", tool_name=step.name, error_type="TypeError", error_message=str(e))
            raise ToolExecutionError(error_msg, tool_name=step.name, original_exception=e) from e
        except Exception as e:
            error_msg = f"Tool '{step.name}' raised an exception: {e}"
            self._add_trace_log("TOOL_EXECUTION_ERROR", tool_name=step.name, error_type=type(e).__name__, error_message=str(e))
            raise ToolExecutionError(error_msg, tool_name=step.name, original_exception=e) from e


    def _execute_code_step(self, step: CodeStep) -> Any:
        if step.lang.lower() != 'python':
            raise NotImplementedError(f"Code execution for language '{step.lang}' is not supported. Only Python is allowed.")

        context_vars = self.context.get_all_variables()
        rendered_script = render_template_string(step.script, context_vars) # Script itself could be a template
        self._add_trace_log("TEMPLATE_RENDERED", step_type="CodeStep", original_script=step.script, rendered_script=rendered_script)
        print(f"    - Executing Python Code (in asteval sandbox):\n{rendered_script}")

        local_sandbox_context = context_vars.copy()
        aeval = asteval.Interpreter(symtable=local_sandbox_context, minimal=False)
        aeval.eval(rendered_script)

        if aeval.error:
            error_msg = "\n".join([err.get_error()[1] for err in aeval.error])
            self._add_trace_log("CODE_EXECUTION_ERROR", script=rendered_script, error=error_msg)
            raise ValueError(f"Error executing Python code step: {error_msg}\nScript:\n{rendered_script}")

        result_val = aeval.symtable.get('result', None)
        self._add_trace_log("CODE_EXECUTION_SUCCESS", script=rendered_script, result=str(result_val), sandbox_keys=list(aeval.symtable.keys()))
        if 'result' not in aeval.symtable:
            print("    - CodeStep Warning: No 'result' variable found in script output. Returning None.")
        return result_val

    def _execute_if_step(self, step: IfStep):
        context_vars = self.context.get_all_variables()
        condition_result = safe_eval_code_string(step.condition, context_vars) # safe_eval also renders template
        self._add_trace_log("IF_CONDITION_EVAL", condition_str=step.condition, outcome=condition_result, context_used_keys=list(context_vars.keys()))
        print(f"    - If Condition: '{step.condition}' evaluated to: {condition_result}")

        if condition_result:
            print(f"    - Executing 'then' branch...")
            self._execute_workflow_steps(step.then_steps, branch_name="if_then")
        elif step.else_steps:
            print(f"    - Executing 'else' branch...")
            self._execute_workflow_steps(step.else_steps, branch_name="if_else")
        else:
            print(f"    - Condition is false, no 'else' branch to execute.")

    def _execute_workflow_steps(self, steps: List[StepType], branch_name: str = "main_workflow") -> Any:
        """Executes a list of steps, typically a workflow or a branch of an IfStep."""
        self._add_trace_log("WORKFLOW_BRANCH_START", branch=branch_name, num_steps=len(steps))
        last_output = None
        for i, step_obj in enumerate(steps):
            if not isinstance(step_obj, BaseStep):
                raise TypeError(f"Step {i} in branch '{branch_name}' is not a valid BaseStep instance: {step_obj}")
            last_output = self._execute_step(step_obj, i, len(steps))
        self._add_trace_log("WORKFLOW_BRANCH_END", branch=branch_name, last_output=str(last_output))
        return last_output

    def _execute_loop_step(self, step: LoopStep) -> Optional[List[Any]]:
        """Executes a LoopStep based on its parsed type and parameters."""
        self._add_trace_log("LOOP_STEP_START", loop_type=str(step.loop_type), expression=step.expression)

        iteration_results = []
        original_context = self.context # Stash the original context

        if step.loop_type == LoopType.FOR_EACH:
            if not step.iterable_var_name or not step.loop_var_name:
                raise ValueError("LoopStep FOR_EACH is missing iterable_var_name or loop_var_name.")

            iterable_collection = original_context.get_variable(step.iterable_var_name, None)
            if iterable_collection is None:
                raise ValueError(f"Iterable '{step.iterable_var_name}' not found in context for FOR_EACH loop.")
            if not hasattr(iterable_collection, '__iter__') or isinstance(iterable_collection, str): # strings are iterable but usually not what's intended for item-wise iteration here
                raise TypeError(f"Variable '{step.iterable_var_name}' is not an iterable collection for FOR_EACH loop.")

            for item_index, item_value in enumerate(iterable_collection):
                iteration_context = Context(initial_vars=original_context.get_all_variables())
                iteration_context.set_variable(step.loop_var_name, item_value)
                # Potentially add index variable, e.g., f"{step.loop_var_name}_index"
                # iteration_context.set_variable(f"{step.loop_var_name}_index", item_index)

                self.context = iteration_context # Temporarily swap context for inner steps
                self._add_trace_log("LOOP_ITERATION_START", loop_type="FOR_EACH", iteration=item_index, loop_var=step.loop_var_name, value=item_value)
                last_iteration_output = self._execute_workflow_steps(step.steps, branch_name=f"loop_for_each_iter_{item_index}")
                iteration_results.append(last_iteration_output)
                self._add_trace_log("LOOP_ITERATION_END", loop_type="FOR_EACH", iteration=item_index, output=last_iteration_output)

            self.context = original_context # Restore original context

        elif step.loop_type == LoopType.FOR_RANGE:
            if not step.loop_var_name or not step.range_args_str:
                raise ValueError("LoopStep FOR_RANGE is missing loop_var_name or range_args_str.")

            # Evaluate range arguments. They can be numbers or context variable expressions.
            eval_args = []
            for arg_str in step.range_args_str:
                val = safe_eval_code_string(arg_str, original_context.get_all_variables())
                if not isinstance(val, int):
                    raise TypeError(f"Range argument '{arg_str}' (rendered: {val}) must evaluate to an integer.")
                eval_args.append(val)

            if not 1 <= len(eval_args) <= 3:
                raise ValueError(f"Invalid number of arguments for range: {len(eval_args)}. Expected 1, 2, or 3.")

            for i_val in range(*eval_args):
                iteration_context = Context(initial_vars=original_context.get_all_variables())
                iteration_context.set_variable(step.loop_var_name, i_val)

                self.context = iteration_context # Temporarily swap context
                self._add_trace_log("LOOP_ITERATION_START", loop_type="FOR_RANGE", iteration_value=i_val, loop_var=step.loop_var_name)
                last_iteration_output = self._execute_workflow_steps(step.steps, branch_name=f"loop_for_range_iter_{i_val}")
                iteration_results.append(last_iteration_output)
                self._add_trace_log("LOOP_ITERATION_END", loop_type="FOR_RANGE", iteration_value=i_val, output=last_iteration_output)

            self.context = original_context # Restore

        elif step.loop_type == LoopType.WHILE:
            if not step.condition_expr:
                raise ValueError("LoopStep WHILE is missing condition_expr.")

            iteration_count = 0
            # WHILE loop steps operate directly on the original_context (self.context)
            # so that changes within the loop body can affect the condition.
            while True:
                condition_result = safe_eval_code_string(step.condition_expr, self.context.get_all_variables())
                if not isinstance(condition_result, bool):
                    raise TypeError(f"While loop condition '{step.condition_expr}' must evaluate to a boolean. Got: {condition_result}")

                self._add_trace_log("LOOP_CONDITION_EVAL", loop_type="WHILE", condition=step.condition_expr, result=condition_result)
                if not condition_result:
                    break

                self._add_trace_log("LOOP_ITERATION_START", loop_type="WHILE", iteration=iteration_count)
                # For WHILE, steps are executed in the current context (original_context)
                last_iteration_output = self._execute_workflow_steps(step.steps, branch_name=f"loop_while_iter_{iteration_count}")
                iteration_results.append(last_iteration_output)
                self._add_trace_log("LOOP_ITERATION_END", loop_type="WHILE", iteration=iteration_count, output=last_iteration_output)
                iteration_count += 1
                if iteration_count > 1000: # Safety break for runaway loops
                    self._add_trace_log("LOOP_SAFETY_BREAK", loop_type="WHILE", iterations=iteration_count)
                    print("WARNING: While loop exceeded 1000 iterations, breaking for safety.")
                    break
            # No context restoration needed as we used self.context directly

        else: # LoopType.INVALID or unhandled
            self.context = original_context # Ensure context is restored if error occurs early
            raise NotImplementedError(f"Loop type '{step.loop_type}' is not implemented or LoopStep was not parsed correctly.")

        self._add_trace_log("LOOP_STEP_END", loop_type=str(step.loop_type), num_iterations=len(iteration_results), aggregated_results_count=len(iteration_results))

        if step.def_var: # If the loop itself is meant to define a variable (e.g. list of results)
            return iteration_results
        return None # Loop executed for side effects, no specific aggregated output defined by loop itself


    def run(self, inputs: Optional[Dict[str, Any]] = None) -> Any:
        self._add_trace_log("INTERPRETER_RUN_START", pil_program_config_model=self.pil_program.config.model if self.pil_program.config else "N/A")
        print(f"Interpreter: Running PIL program...")

        if inputs: # If run() is called with an inputs dict
            self._validate_inputs(inputs) # This will add them to context and validate against program.input

        # After processing explicit 'inputs' (if any), or if none were passed to run(),
        # check if all required inputs (defined in program.input.vars) are now in the context.
        if self.pil_program.input and self.pil_program.input.vars:
            required_program_inputs = [var.name for var in self.pil_program.input.vars]
            missing_vars_in_context = [req_var for req_var in required_program_inputs if not self.context.has_variable(req_var)]
            if missing_vars_in_context:
                err_msg = (f"Missing required input variables in context: {', '.join(missing_vars_in_context)}. "
                           f"Defined inputs in program: {required_program_inputs}. Ensure they are provided either via "
                           f"Interpreter's initial_vars or the 'inputs' argument to run().")
                self._add_trace_log("INPUT_VALIDATION_ERROR", error=err_msg, missing_variables=missing_vars_in_context)
                raise ValueError(err_msg)

        if self.pil_program.persona and self.pil_program.persona.role:
            self.context.set_variable("__persona__", self.pil_program.persona)
            self._add_trace_log("PERSONA_SET", persona_role=self.pil_program.persona.role)
            print(f"Interpreter: Persona set: {self.pil_program.persona.role}")

        if not self.pil_program.workflow or not self.pil_program.workflow.steps:
            self._add_trace_log("WORKFLOW_EMPTY", status="Workflow has no steps.")
            print("Interpreter: Workflow has no steps to execute.")
            return None

        final_output = self._execute_workflow_steps(self.pil_program.workflow.steps)

        if self.pil_program.output_schema and self.pil_program.output_schema.schema:
            self._add_trace_log("OUTPUT_SCHEMA_TODO", schema=self.pil_program.output_schema.schema)
            print(f"Interpreter: Program defines an output schema. TODO: Validate final output against schema.")

        self._add_trace_log("INTERPRETER_RUN_END", final_output_from_workflow=str(final_output))

        # Output Schema Validation
        if self.pil_program.output_schema and self.pil_program.output_schema.schema:
            self._add_trace_log("OUTPUT_SCHEMA_VALIDATION_START", schema=self.pil_program.output_schema.schema, output_to_validate=str(final_output))
            print(f"Interpreter: Validating final output against outputSchema...")
            try:
                jsonschema.validate(instance=final_output, schema=self.pil_program.output_schema.schema)
                self._add_trace_log("OUTPUT_SCHEMA_VALIDATION_SUCCESS")
                print("Interpreter: Output schema validation successful.")
            except jsonschema.ValidationError as e:
                # Potentially wrap this in a custom OutputValidationError
                error_msg = f"Output validation failed: {e.message} (Path: {'/'.join(map(str, e.path)) if e.path else 'N/A'})"
                self._add_trace_log("OUTPUT_SCHEMA_VALIDATION_FAILED", error=e.message, details=str(e))
                raise OutputValidationError(f"Output validation failed for instance: {str(final_output)[:100]}...", validation_error=e) from e
            except jsonschema.SchemaError as e: # If the schema itself is invalid
                error_msg = f"Invalid OutputSchema provided in PIL program: {e.message}"
                self._add_trace_log("OUTPUT_SCHEMA_INVALID", error=error_msg, details=str(e))
                raise InvalidSchemaError(error_msg, schema_error=e) from e

        print("Interpreter: PIL program execution finished.")

        if self.debug_mode:
            print("\n--- DEBUG TRACE LOG ---")
            for entry in self.trace_log:
                print(yaml.dump(entry, indent=2, default_flow_style=False, sort_keys=False))
            print("--- END DEBUG TRACE LOG ---")

        return final_output


if __name__ == '__main__':
    print("PIL Interpreter with Step Execution Logic and Debug Tracing Concepts")

    test_pil_yaml_content = """
config:
  model: test-model-002
  parameters: {temperature: 0.2}
persona: {role: Advanced Test Assistant}
input: {vars: {user_command: string, user_data: object, max_items: int}}
outputSchema:
  schema: {type: object, properties: {final_result: {type: string}, items_processed: {type: array}}}
workflow:
  steps:
    - retrieve: {from: internal_docs, query: "{{ user_command }}", k: 2, def: retrieved_docs}
    - prompt:
        text: |
          User command: {{ user_command }}
          User data: {{ user_data }}
          Retrieved docs: {{ retrieved_docs | map(attribute='content') | join('\\n- ') }}
        def: initial_analysis
    - code:
        lang: python
        script: |
          processed_items = []
          if user_data.get("items"):
              for i, item in enumerate(user_data["items"]):
                  if i < max_items:
                      processed_items.append(f"Processed item {item} from user_data")
          for doc in retrieved_docs:
              processed_items.append(f"Considered doc: {doc['id']}")
          result = {"summary": f"Analyzed {len(processed_items)} items based on '{initial_analysis[:20]}...'", "details": processed_items}
        def: code_output
    - if:
        if: "user_command == 'summarize'"
        then:
          - prompt: {text: "Summarize this analysis: {{ code_output.summary }}. Docs considered: {{ code_output.details | join(', ') }}", def: summary_result}
        else:
          - tool: {name: custom_processing_tool, args: {data: "{{ code_output }}", command_type: "{{ user_command }}"}, def: tool_result}
    - prompt: {text: "Final decision. Summarize: {{ summary_result | default('N/A') }}. Tool: {{ tool_result | default('N/A') }}", def: final_result_var}
"""
    parser = PilParser()
    try:
        pil_program_data = yaml.safe_load(test_pil_yaml_content)
        pil_program_instance = parser.parse_dict(pil_program_data)

        print("\n--- Parsed PIL Program ---")
        # interpreter_no_debug = Interpreter(pil_program_instance, debug_mode=False) # Test without debug
        interpreter_debug = Interpreter(pil_program_instance, debug_mode=True) # Test with debug

        print("\n--- Running Interpreter (Summarize command, DEBUG MODE) ---")
        inputs_summarize = {"user_command": "summarize", "user_data": {"items": ["apple", "banana", "cherry"], "source": "web"}, "max_items": 2}
        output_summarize = interpreter_debug.run(inputs=inputs_summarize)
        print(f"\nInterpreter output (summarize): {output_summarize}")
        # print(f"Final context (summarize): {interpreter_debug.context.get_all_variables()}")


        print("\n\n--- Running Interpreter (Process command, new instance, DEBUG MODE) ---")
        interpreter_process_debug = Interpreter(parser.parse_dict(pil_program_data), debug_mode=True)
        inputs_process = {"user_command": "process_detailed", "user_data": {"items": ["orange", "grape"], "source": "db"}, "max_items": 5}
        output_process = interpreter_process_debug.run(inputs=inputs_process)
        print(f"\nInterpreter output (process): {output_process}")
        # print(f"Final context (process): {interpreter_process_debug.context.get_all_variables()}")

    except Exception as e:
        print(f"\n!!!!!! An error occurred during the test: {e} !!!!!!!")
        import traceback
        traceback.print_exc()

    print("\n--- End of Interpreter Step Execution Logic Test (with Debug Tracing Concepts) ---")
