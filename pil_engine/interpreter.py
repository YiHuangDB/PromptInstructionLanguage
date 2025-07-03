import yaml
import asteval # For CodeStep execution sandbox
from typing import Dict, Any, Optional, List, Callable

from .core.components import (
    PilProgram, parse_step, BaseStep, PromptStep, RetrieveStep, ToolStep, CodeStep, IfStep, LoopStep, StepType, LoopType
)
from .core.context import Context
from .utils import render_template_string, safe_eval_code_string
from .exceptions import (
    ToolNotFoundException, ToolExecutionError, OutputValidationError,
    InvalidSchemaError, ConfigurationError, ConstraintViolationError
)
from .validator import apply_constraints

import os
import openai
import re
import jsonschema

class PilParser:
    def __init__(self):
        pass

    def parse_yaml_file(self, file_path: str) -> PilProgram:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f)
            if not isinstance(raw_data, dict):
                raise ValueError("PIL program YAML root must be a dictionary (YAML mapping).")
            return PilProgram.from_yaml(raw_data, parse_step)
        except FileNotFoundError:
            raise FileNotFoundError(f"PIL file not found: {file_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing PIL YAML file '{file_path}': {e}")
        except Exception as e:
            raise ValueError(f"Unexpected error creating PilProgram from YAML in '{file_path}': {e}")

    def parse_dict(self, data: Dict[str, Any]) -> PilProgram:
        if not isinstance(data, dict):
            raise ValueError("PIL program data must be a dictionary.")
        try:
            return PilProgram.from_yaml(data, parse_step)
        except Exception as e:
            raise ValueError(f"Unexpected error creating PilProgram from dictionary: {e}")

class Interpreter:
    def __init__(self, pil_program: PilProgram,
                 initial_vars: Optional[Dict[str, Any]] = None,
                 debug_mode: bool = False):
        if not isinstance(pil_program, PilProgram):
            raise TypeError("pil_program must be an instance of PilProgram.")
        self.pil_program: PilProgram = pil_program
        self.context: Context = Context(initial_vars=initial_vars)
        self.llm_client: Any = None
        self.debug_mode: bool = debug_mode
        self.trace_log: List[Dict[str, Any]] = [] if self.debug_mode else None
        self.knowledge_bases: Dict[str, List[Dict[str, Any]]] = {}
        self.tool_registry: Dict[str, Callable] = {}

        self._initialize_llm_client()
        self._load_all_knowledge_bases()

    def register_tool(self, name: str, tool_callable: Callable):
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
        if self.debug_mode:
            log_entry = {"event": event_type, **kwargs}
            self.trace_log.append(log_entry)
            print(f"    TRACE: {log_entry}")

    def _initialize_llm_client(self):
        config = self.pil_program.config
        model_name = config.model if config else None
        api_key_from_config = config.api_key if config else None

        if not model_name:
            self._add_trace_log("LLM_CLIENT_INIT_SKIPPED", reason="No model specified in PIL config.")
            print("Interpreter: LLM client not initialized: No model specified in PIL program config.")
            self.llm_client = None
            return

        api_key = api_key_from_config or os.environ.get("OPENAI_API_KEY")

        if not api_key:
            error_msg = f"API key not found in config or environment (OPENAI_API_KEY) for model '{model_name}'."
            self._add_trace_log("LLM_CLIENT_INIT_FAILED", model=model_name, reason=error_msg)
            self.llm_client = None
            raise ConfigurationError(error_msg)
        try:
            self.llm_client = openai.OpenAI(api_key=api_key)
            self._add_trace_log("LLM_CLIENT_INIT_SUCCESS", model=model_name, client_type="OpenAI")
            print(f"Interpreter: OpenAI LLM Client Initialized for model '{model_name}'.")
        except Exception as e:
            self.llm_client = None
            self._add_trace_log("LLM_CLIENT_INIT_ERROR", model=model_name, error=str(e))
            raise ConfigurationError(f"Error initializing OpenAI client for model '{model_name}': {e}") from e

    def _load_knowledge_base(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                kb_data = yaml.safe_load(f)
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
        except (yaml.YAMLError, ValueError) as e:
            self._add_trace_log("KB_LOAD_ERROR", source=file_path, error=str(e))
            raise ValueError(f"Error loading or parsing knowledge base '{file_path}': {e}")
        except Exception as e:
            self._add_trace_log("KB_LOAD_ERROR", source=file_path, error=f"Unexpected error: {str(e)}")
            raise RuntimeError(f"Unexpected error loading knowledge base '{file_path}': {e}")

    def _collect_kb_sources_from_steps(self, steps: List[StepType]) -> set[str]:
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
        if not self.pil_program.workflow or not self.pil_program.workflow.steps:
            return
        kb_sources = self._collect_kb_sources_from_steps(self.pil_program.workflow.steps)
        for source_path in kb_sources:
            if source_path not in self.knowledge_bases:
                try:
                    self.knowledge_bases[source_path] = self._load_knowledge_base(source_path)
                except Exception as e:
                    print(f"Interpreter Warning: Failed to load knowledge base '{source_path}': {e}. Retrieval from this source will fail.")
                    self.knowledge_bases[source_path] = None

    def _validate_inputs(self, provided_inputs: Dict[str, Any]):
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
        step_type_name = step_obj.__class__.__name__
        self._add_trace_log("PRE_STEP_EXECUTION", step_number=f"{step_index+1}/{total_steps}", type=step_type_name, definition=str(step_obj),
                            current_context_keys=list(self.context.get_all_variables().keys()))
        print(f"  Executing {step_type_name}: {step_obj}")
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
        rendered_text = render_template_string(template_text, context_vars)

        log_full_prompt_parts = []
        persona_info_log = self.context.get_variable("__persona__", None)
        if persona_info_log:
            log_full_prompt_parts.append(f"Persona: {persona_info_log.role} ({persona_info_log.style}, {persona_info_log.tone})")
        if step.examples:
            example_texts_log = [f"Example Input: {ex.get('input', '')}\nExample Output: {ex.get('output', '')}" for ex in step.examples]
            if example_texts_log:
                 log_full_prompt_parts.append("Examples:\n" + "\n---\n".join(example_texts_log))
        log_full_prompt_parts.append(f"Prompt: {rendered_text}")
        final_prompt_for_logging = "\n\n".join(log_full_prompt_parts)
        self._add_trace_log("PROMPT_TEXT_RENDERED", original_template=template_text, rendered_initial_prompt=rendered_text, conceptual_full_prompt=final_prompt_for_logging)
        print(f"    - Rendered Prompt for LLM (Conceptual Initial): \n\"{final_prompt_for_logging}\"")

        if self.llm_client is None:
            error_message = "LLM client is not available for PromptStep. Check API key and model configuration."
            self._add_trace_log("LLM_CALL_FAILED", reason=error_message)
            raise ConfigurationError(error_message)

        current_user_prompt_content = rendered_text
        last_error: Optional[Exception] = None

        for attempt in range(step.max_retries + 1):
            self._add_trace_log("PROMPT_ATTEMPT", attempt=attempt + 1, max_attempts=step.max_retries + 1, current_user_message=current_user_prompt_content)

            messages = []
            persona_obj = self.context.get_variable("__persona__", None)
            if persona_obj and persona_obj.role:
                system_content = f"Role: {persona_obj.role}"
                if persona_obj.style: system_content += f", Style: {persona_obj.style}"
                if persona_obj.tone: system_content += f", Tone: {persona_obj.tone}"
                if persona_obj.audience: system_content += f", Audience: {persona_obj.audience}"
                messages.append({"role": "system", "content": system_content})

            if attempt == 0:
                for example in step.examples:
                    if "input" in example and "output" in example:
                        messages.append({"role": "user", "content": example["input"]})
                        messages.append({"role": "assistant", "content": example["output"]})

            messages.append({"role": "user", "content": current_user_prompt_content})

            llm_response_content = None
            api_call_succeeded = False

            try:
                self._add_trace_log("LLM_API_CALL_START", attempt=attempt+1, model=self.pil_program.config.model, messages=messages, parameters=self.pil_program.config.parameters)
                print(f"    - Attempt {attempt+1}/{step.max_retries+1}: Making API call to OpenAI model: {self.pil_program.config.model}")
                if attempt > 0: print(f"    - Corrective user message being used.")

                completion = self.llm_client.chat.completions.create(
                    model=self.pil_program.config.model,
                    messages=messages,
                    **self.pil_program.config.parameters
                )
                llm_response_content = completion.choices[0].message.content
                api_call_succeeded = True
                self._add_trace_log("LLM_API_CALL_SUCCESS", attempt=attempt+1, response_id=completion.id, finish_reason=completion.choices[0].finish_reason, usage=str(completion.usage))
                print(f"    - LLM Response received (Attempt {attempt+1}). Finish reason: {completion.choices[0].finish_reason}")

            except openai.APIConnectionError as e_api:
                err_msg = f"OpenAI API request failed to connect (Attempt {attempt+1}): {e_api}"
                self._add_trace_log("LLM_API_CALL_ERROR", attempt=attempt+1, error_type="APIConnectionError", error_message=str(e_api))
                last_error = ConnectionError(err_msg)
                if attempt < step.max_retries: print(f"    - {err_msg}. Retrying API call..."); continue
                raise last_error from e_api
            except openai.RateLimitError as e_api:
                err_msg = f"OpenAI API request exceeded rate limit (Attempt {attempt+1}): {e_api}"
                self._add_trace_log("LLM_API_CALL_ERROR", attempt=attempt+1, error_type="RateLimitError", error_message=str(e_api))
                last_error = PermissionError(err_msg)
                if attempt < step.max_retries: print(f"    - {err_msg}. Retrying API call..."); continue
                raise last_error from e_api
            except openai.AuthenticationError as e_api:
                err_msg = f"OpenAI API authentication failed: {e_api}. Check your API key."
                self._add_trace_log("LLM_API_CALL_ERROR", attempt=attempt+1, error_type="AuthenticationError", error_message=str(e_api))
                raise PermissionError(err_msg) from e_api
            except openai.APIStatusError as e_api:
                err_msg = f"OpenAI API returned an error status {e_api.status_code} (Attempt {attempt+1}): {e_api.response}"
                self._add_trace_log("LLM_API_CALL_ERROR", attempt=attempt+1, error_type="APIStatusError", status_code=e_api.status_code, error_message=str(e_api.response))
                last_error = RuntimeError(err_msg)
                if attempt < step.max_retries: print(f"    - {err_msg}. Retrying API call..."); continue
                raise last_error from e_api

            if not api_call_succeeded:
                continue

            if step.constraints:
                self._add_trace_log("CONSTRAINT_VALIDATION_START", attempt=attempt+1, constraints=str(step.constraints), value_to_validate=llm_response_content)
                print(f"    - Applying constraints (Attempt {attempt+1}): {step.constraints}")
                try:
                    validated_output = apply_constraints(
                        value=llm_response_content,
                        constraints=step.constraints,
                        context=self.context,
                        step_name=f"PromptStep (def: {step.def_var or 'N/A'}, attempt {attempt+1})"
                    )
                    self._add_trace_log("CONSTRAINT_VALIDATION_SUCCESS", attempt=attempt+1, validated_output=str(validated_output))
                    print("    - Constraint validation successful.")
                    return validated_output
                except ConstraintViolationError as cve:
                    self._add_trace_log("CONSTRAINT_VALIDATION_FAILED", attempt=attempt+1, error=str(cve))
                    last_error = cve
                    print(f"    - Constraint validation failed (Attempt {attempt+1}): {cve}")
                    if attempt < step.max_retries:
                        correction_instruction = (
                            f"\n\n[System Correction]: Your previous response failed validation. "
                            f"Error: \"{str(cve)}\". Please try again, ensuring your output is valid."
                        )
                        current_user_prompt_content = rendered_text + correction_instruction
                        continue
                    else:
                        raise last_error
            else:
                return llm_response_content

        if last_error:
            raise last_error

        raise RuntimeError(f"PromptStep execution unexpectedly completed all retries ({step.max_retries + 1} attempts) without returning or raising a specific error.")

    def _execute_retrieve_step(self, step: RetrieveStep) -> List[Dict[str, Any]]:
        context_vars = self.context.get_all_variables()
        rendered_query = render_template_string(step.query, context_vars)
        self._add_trace_log("TEMPLATE_RENDERED", step_type="RetrieveStep", original_query=step.query, rendered_query=rendered_query)
        print(f"    - Retrieval: from='{step.from_source}', query='{rendered_query}', k={step.k}")

        knowledge_base = self.knowledge_bases.get(step.from_source)
        if knowledge_base is None:
            self._add_trace_log("RETRIEVAL_FAILED", source=step.from_source, query=rendered_query, reason="Knowledge base not loaded or unavailable.")
            print(f"    - WARNING: Knowledge base '{step.from_source}' not loaded. Returning empty list for retrieval.")
            return []

        if not knowledge_base:
            self._add_trace_log("RETRIEVAL_EMPTY_KB", source=step.from_source, query=rendered_query)
            return []

        def tokenize(text: str) -> set[str]:
            if not isinstance(text, str):
                text = str(text)
            text = re.sub(r'[^\w\s]', '', text)
            return set(word for word in text.lower().split() if word)

        query_tokens = tokenize(rendered_query)

        scored_documents = []
        for doc in knowledge_base:
            doc_content = doc.get("content", "")
            doc_tokens = tokenize(doc_content)
            common_tokens = query_tokens.intersection(doc_tokens)
            score = len(common_tokens)

            if score > 0:
                retrieved_doc_item = doc.copy()
                retrieved_doc_item["score"] = float(score)
                scored_documents.append(retrieved_doc_item)

        scored_documents.sort(key=lambda x: x["score"], reverse=True)
        results = scored_documents[:step.k]
        self._add_trace_log("RETRIEVAL_EXECUTED", source=step.from_source, query=rendered_query, k=step.k, result_count=len(results), total_matches_before_k=len(scored_documents))
        return results

    def _execute_tool_step(self, step: ToolStep) -> Any:
        context_vars = self.context.get_all_variables()
        rendered_args = {}
        for arg_name, val_template in step.args.items():
            if isinstance(val_template, str):
                rendered_args[arg_name] = render_template_string(val_template, context_vars)
            else:
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
        rendered_script = render_template_string(step.script, context_vars)
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
        condition_result = safe_eval_code_string(step.condition, context_vars)
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
        self._add_trace_log("WORKFLOW_BRANCH_START", branch=branch_name, num_steps=len(steps))
        last_output = None
        for i, step_obj in enumerate(steps):
            if not isinstance(step_obj, BaseStep):
                raise TypeError(f"Step {i} in branch '{branch_name}' is not a valid BaseStep instance: {step_obj}")
            last_output = self._execute_step(step_obj, i, len(steps))
        self._add_trace_log("WORKFLOW_BRANCH_END", branch=branch_name, last_output=str(last_output))
        return last_output

    def _execute_loop_step(self, step: LoopStep) -> Optional[List[Any]]:
        self._add_trace_log("LOOP_STEP_START", loop_type=str(step.loop_type), expression=step.expression)
        iteration_results = []
        original_context = self.context
        if step.loop_type == LoopType.FOR_EACH:
            if not step.iterable_var_name or not step.loop_var_name:
                raise ValueError("LoopStep FOR_EACH is missing iterable_var_name or loop_var_name.")
            iterable_collection = original_context.get_variable(step.iterable_var_name, None)
            if iterable_collection is None:
                raise ValueError(f"Iterable '{step.iterable_var_name}' not found in context for FOR_EACH loop.")
            if not hasattr(iterable_collection, '__iter__') or isinstance(iterable_collection, str):
                raise TypeError(f"Variable '{step.iterable_var_name}' is not an iterable collection for FOR_EACH loop.")
            for item_index, item_value in enumerate(iterable_collection):
                iteration_context = Context(initial_vars=original_context.get_all_variables())
                iteration_context.set_variable(step.loop_var_name, item_value)
                self.context = iteration_context
                self._add_trace_log("LOOP_ITERATION_START", loop_type="FOR_EACH", iteration=item_index, loop_var=step.loop_var_name, value=item_value)
                last_iteration_output = self._execute_workflow_steps(step.steps, branch_name=f"loop_for_each_iter_{item_index}")
                iteration_results.append(last_iteration_output)
                self._add_trace_log("LOOP_ITERATION_END", loop_type="FOR_EACH", iteration=item_index, output=last_iteration_output)
            self.context = original_context
        elif step.loop_type == LoopType.FOR_RANGE:
            if not step.loop_var_name or not step.range_args_str:
                raise ValueError("LoopStep FOR_RANGE is missing loop_var_name or range_args_str.")
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
                self.context = iteration_context
                self._add_trace_log("LOOP_ITERATION_START", loop_type="FOR_RANGE", iteration_value=i_val, loop_var=step.loop_var_name)
                last_iteration_output = self._execute_workflow_steps(step.steps, branch_name=f"loop_for_range_iter_{i_val}")
                iteration_results.append(last_iteration_output)
                self._add_trace_log("LOOP_ITERATION_END", loop_type="FOR_RANGE", iteration_value=i_val, output=last_iteration_output)
            self.context = original_context
        elif step.loop_type == LoopType.WHILE:
            if not step.condition_expr:
                raise ValueError("LoopStep WHILE is missing condition_expr.")
            iteration_count = 0
            while True:
                condition_result = safe_eval_code_string(step.condition_expr, self.context.get_all_variables())
                if not isinstance(condition_result, bool):
                    raise TypeError(f"While loop condition '{step.condition_expr}' must evaluate to a boolean. Got: {condition_result}")
                self._add_trace_log("LOOP_CONDITION_EVAL", loop_type="WHILE", condition=step.condition_expr, result=condition_result)
                if not condition_result:
                    break
                self._add_trace_log("LOOP_ITERATION_START", loop_type="WHILE", iteration=iteration_count)
                last_iteration_output = self._execute_workflow_steps(step.steps, branch_name=f"loop_while_iter_{iteration_count}")
                iteration_results.append(last_iteration_output)
                self._add_trace_log("LOOP_ITERATION_END", loop_type="WHILE", iteration=iteration_count, output=last_iteration_output)
                iteration_count += 1
                if iteration_count > 1000:
                    self._add_trace_log("LOOP_SAFETY_BREAK", loop_type="WHILE", iterations=iteration_count)
                    print("WARNING: While loop exceeded 1000 iterations, breaking for safety.")
                    break
        else:
            self.context = original_context
            raise NotImplementedError(f"Loop type '{step.loop_type}' is not implemented or LoopStep was not parsed correctly.")
        self._add_trace_log("LOOP_STEP_END", loop_type=str(step.loop_type), num_iterations=len(iteration_results), aggregated_results_count=len(iteration_results))
        if step.def_var:
            return iteration_results
        return None

    def run(self, inputs: Optional[Dict[str, Any]] = None) -> Any:
        self._add_trace_log("INTERPRETER_RUN_START", pil_program_config_model=self.pil_program.config.model if self.pil_program.config else "N/A")
        print(f"Interpreter: Running PIL program...")
        if inputs:
            self._validate_inputs(inputs)
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
        self._add_trace_log("INTERPRETER_RUN_END", final_output_from_workflow=str(final_output))
        if self.pil_program.output_schema and self.pil_program.output_schema.schema:
            self._add_trace_log("OUTPUT_SCHEMA_VALIDATION_START", schema=self.pil_program.output_schema.schema, output_to_validate=str(final_output))
            print(f"Interpreter: Validating final output against outputSchema...")
            try:
                jsonschema.validate(instance=final_output, schema=self.pil_program.output_schema.schema)
                self._add_trace_log("OUTPUT_SCHEMA_VALIDATION_SUCCESS")
                print("Interpreter: Output schema validation successful.")
            except jsonschema.ValidationError as e:
                error_msg = f"Output validation failed: {e.message} (Path: {'/'.join(map(str, e.path)) if e.path else 'N/A'})"
                self._add_trace_log("OUTPUT_SCHEMA_VALIDATION_FAILED", error=e.message, details=str(e))
                raise OutputValidationError(error_msg, validation_error=e) from e
            except jsonschema.SchemaError as e:
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
  api_key: DUMMY_KEY_FOR_MAIN_TEST # Add a dummy key to prevent ConfigurationError if model is present
  parameters: {temperature: 0.2}
persona: {role: Advanced Test Assistant}
input: {vars: {user_command: string, user_data: object, max_items: int}}
outputSchema:
  schema: {type: object, properties: {final_result: {type: string}, items_processed: {type: array}}}
workflow:
  steps:
    - retrieve: {from: examples/knowledge_base.json, query: "{{ user_command }}", k: 2, def: retrieved_docs}
    - prompt:
        text: |
          User command: {{ user_command }}
          User data: {{ user_data }}
          Retrieved docs: {{ retrieved_docs | map(attribute='content') | join('\\n- ') }}
        def: initial_analysis
        max_retries: 1 # Test self-correction
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

        # Mock OpenAI for the main test execution if it uses PromptSteps
        with unittest.mock.patch('openai.OpenAI') as MockOpenAI_main:
            mock_main_client = MockOpenAI_main.return_value
            mock_main_client.chat.completions.create.return_value = unittest.mock.MagicMock(
                choices=[unittest.mock.MagicMock(message=unittest.mock.MagicMock(content="Main test simulated LLM response"))]
            )

            interpreter_debug = Interpreter(pil_program_instance, debug_mode=True)

            # Register dummy tool for the example to run
            def dummy_custom_tool(data, command_type):
                return f"Dummy tool output for {command_type} with data summary: {data.get('summary', 'N/A')}"
            interpreter_debug.register_tool("custom_processing_tool", dummy_custom_tool)


            print("\n--- Running Interpreter (Summarize command, DEBUG MODE) ---")
            inputs_summarize = {"user_command": "summarize", "user_data": {"items": ["apple", "banana", "cherry"], "source": "web"}, "max_items": 2}
            try:
                output_summarize = interpreter_debug.run(inputs=inputs_summarize)
                print(f"\nInterpreter output (summarize): {output_summarize}")
            except ConfigurationError as e:
                print(f"Caught ConfigurationError for summarize: {e}")
            except Exception as e:
                print(f"Unexpected error during summarize run: {e}")
                traceback.print_exc()


            print("\n\n--- Running Interpreter (Process command, new instance, DEBUG MODE) ---")
            # Re-create program instance for a clean context if needed, or reset interpreter context
            pil_program_instance_2 = parser.parse_dict(pil_program_data) # Fresh program object
            interpreter_process_debug = Interpreter(pil_program_instance_2, debug_mode=True)
            interpreter_process_debug.register_tool("custom_processing_tool", dummy_custom_tool)

            inputs_process = {"user_command": "process_detailed", "user_data": {"items": ["orange", "grape"], "source": "db"}, "max_items": 5}
            try:
                output_process = interpreter_process_debug.run(inputs=inputs_process)
                print(f"\nInterpreter output (process): {output_process}")
            except ConfigurationError as e:
                 print(f"Caught ConfigurationError for process: {e}")
            except Exception as e:
                print(f"Unexpected error during process run: {e}")
                traceback.print_exc()

    except Exception as e:
        print(f"\n!!!!!! An error occurred during the test setup or parsing: {e} !!!!!!!")
        import traceback
        traceback.print_exc()

    print("\n--- End of Interpreter Step Execution Logic Test (with Debug Tracing Concepts) ---")
