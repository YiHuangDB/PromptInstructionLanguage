import yaml
import asteval # For CodeStep execution sandbox
from typing import Dict, Any, Optional, List

from .core.components import (
    PilProgram, parse_step, BaseStep, PromptStep, RetrieveStep, ToolStep, CodeStep, IfStep, LoopStep, ActualStepType
)
from .core.context import Context
from .utils import render_template_string, safe_eval_code_string

# --- Conceptual Debugging Strategy Notes for Interpreter ---
# (Already detailed in previous step, summarized here for context)
# 1. Trace-Based Debugging: Implemented with `debug_mode` and `trace_log`.
# 2. Domain-Specific Breakpoints: Conceptual, would require syntax and interpreter changes.
# 3. Unit Testing: Best practice, to be implemented with pytest and test PIL files.
# --- End Conceptual Debugging Notes ---


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
        self.llm_client: Any = None # Placeholder for actual LLM client instance
        self.debug_mode: bool = debug_mode
        self.trace_log: List[Dict[str, Any]] = [] if self.debug_mode else None # Stores trace logs if debug_mode is True

        self._initialize_llm_client()

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
        (Placeholder) Initializes the LLM client based on PIL program's config.
        Currently simulates client creation.
        """
        if self.pil_program.config and self.pil_program.config.model:
            # In a real implementation, this would instantiate an actual LLM client, e.g.:
            # from some_llm_library import LLMClient
            # self.llm_client = LLMClient(model=self.pil_program.config.model, api_key=self.pil_program.config.api_key, **self.pil_program.config.parameters)
            self.llm_client = f"SimulatedLLMClient(model={self.pil_program.config.model}, params={self.pil_program.config.parameters})"
            self._add_trace_log("LLM_CLIENT_INIT", client_info=self.llm_client)
            print(f"Interpreter: LLM Client Initialized: {self.llm_client}")
        else:
            self._add_trace_log("LLM_CLIENT_INIT", status="No config or model specified in PIL, LLM client not initialized.")
            print("Interpreter: No LLM configuration provided, or model not specified. LLM client not initialized.")

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
            print(f"    WARNING: LoopStep execution not fully implemented.")
            output = "simulated_loop_output"
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

        if not self.llm_client:
            self._add_trace_log("LLM_CALL_SKIPPED", reason="LLM client not initialized.")
            print("    WARNING: LLM client not initialized. Skipping actual LLM call.")
            return f"SIMULATED_LLM_RESPONSE_FOR_PROMPT: {rendered_text[:50]}..."

        simulated_response = f"Simulated LLM Output for: '{rendered_text[:30]}...'"
        self._add_trace_log("LLM_CALL_SIMULATED", client=str(self.llm_client), prompt_sent=final_prompt_for_llm, simulated_response=simulated_response)
        print(f"    - (Simulated) LLM Call with client: {self.llm_client}")

        if step.constraints:
            self._add_trace_log("CONSTRAINT_TODO", step_type="PromptStep", constraints=step.constraints)
            print(f"    - TODO: Apply constraints to LLM output: {step.constraints}")
        return simulated_response

    def _execute_retrieve_step(self, step: RetrieveStep) -> List[Dict[str, Any]]:
        context_vars = self.context.get_all_variables()
        rendered_query = render_template_string(step.query, context_vars)
        self._add_trace_log("TEMPLATE_RENDERED", step_type="RetrieveStep", original_query=step.query, rendered_query=rendered_query)
        print(f"    - Retrieval: from='{step.from_source}', query='{rendered_query}', k={step.k}")

        simulated_retrieval = [{"id": f"doc_{i+1}", "content": f"Simulated content for query '{rendered_query}' - doc {i+1}", "score": 1.0 - (i*0.1)} for i in range(step.k)]
        self._add_trace_log("RETRIEVAL_SIMULATED", source=step.from_source, query=rendered_query, k=step.k, result_count=len(simulated_retrieval))
        return simulated_retrieval

    def _execute_tool_step(self, step: ToolStep) -> Any:
        context_vars = self.context.get_all_variables()
        rendered_args = {arg_name: render_template_string(val_tpl, context_vars) for arg_name, val_tpl in step.args.items()}
        self._add_trace_log("TEMPLATE_RENDERED", step_type="ToolStep", original_args=step.args, rendered_args=rendered_args)
        print(f"    - Tool Call: name='{step.name}', args={rendered_args}")

        if step.name == "weather_api":
            sim_tool_output = f"Simulated weather for {rendered_args.get('city', 'unknown')}: Sunny, 25 C"
        else:
            sim_tool_output = f"Simulated output from tool '{step.name}' with args {rendered_args}"
        self._add_trace_log("TOOL_CALL_SIMULATED", tool_name=step.name, args=rendered_args, simulated_output=sim_tool_output)
        return sim_tool_output

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

    def _execute_workflow_steps(self, steps: List[ActualStepType], branch_name: str = "main_workflow") -> Any:
        """Executes a list of steps, typically a workflow or a branch of an IfStep."""
        self._add_trace_log("WORKFLOW_BRANCH_START", branch=branch_name, num_steps=len(steps))
        last_output = None
        for i, step_obj in enumerate(steps):
            if not isinstance(step_obj, BaseStep):
                raise TypeError(f"Step {i} in branch '{branch_name}' is not a valid BaseStep instance: {step_obj}")
            last_output = self._execute_step(step_obj, i, len(steps))
        self._add_trace_log("WORKFLOW_BRANCH_END", branch=branch_name, last_output=str(last_output))
        return last_output


    def run(self, inputs: Optional[Dict[str, Any]] = None) -> Any:
        self._add_trace_log("INTERPRETER_RUN_START", pil_program_config_model=self.pil_program.config.model if self.pil_program.config else "N/A")
        print(f"Interpreter: Running PIL program...")

        if inputs:
            self._validate_inputs(inputs)
        else:
            if self.pil_program.input and self.pil_program.input.vars:
                required_vars = [var.name for var in self.pil_program.input.vars]
                if required_vars:
                    err_msg = f"PIL program expects input variables ({', '.join(required_vars)}), but none were provided."
                    self._add_trace_log("INPUT_VALIDATION_ERROR", error=err_msg)
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
