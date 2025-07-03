import unittest
import asyncio # For async sleep if needed in more complex tests
from unittest.mock import patch, MagicMock

from pil_engine.interpreter import Interpreter, PilParser
from pil_engine.core.components import PilProgram, Config
from pil_engine.core.context import Context
from pil_engine.exceptions import OutputValidationError, ConstraintViolationError

# Helper to create a PilProgram for testing program-level self-correction
def create_program_correction_test_program(
    workflow_steps: list,
    output_schema_dict: dict = None,
    program_constraints_dict: dict = None,
    initial_vars_spec: dict = None, # e.g. {"input_val": "string", "pil_last_error_info": "string"}
    max_program_retries: int = 0
) -> PilProgram:

    program_dict = {
        "config": {
            "max_program_retries": max_program_retries
            # No model needed if not using actual LLM calls in these tests
        },
        "workflow": {"steps": workflow_steps}
    }
    if output_schema_dict:
        program_dict["outputSchema"] = {"schema": output_schema_dict}
    if program_constraints_dict:
        program_dict["constraints"] = program_constraints_dict
    if initial_vars_spec:
        # Define input vars for clarity, actual values passed to run()
        # However, pil_last_error_info is special and injected by the interpreter, not a declared program input.
        declared_inputs = {k: v for k, v in initial_vars_spec.items() if k != "pil_last_error_info"}
        if declared_inputs:
            program_dict["input"] = {"vars": declared_inputs}
    # Ensure there's at least one step that produces output if schema/constraints are used
    # and no explicit workflow_steps are provided.
    if not workflow_steps and (output_schema_dict or program_constraints_dict):
        if not any("def" in step.get(list(step.keys())[0], {}) for step in workflow_steps if step): # this check is on empty list
             # This default might not always align with schema/constraints, adjust per test
            if not workflow_steps: # Add a default step if workflow_steps is empty
                 workflow_steps.append({"code": {"lang": "python", "script": "result = 'default_output'", "def": "final_output_var"}})
                 program_dict["workflow"]["steps"] = workflow_steps


    parser = PilParser()
    return parser.parse_dict(program_dict)


class TestInterpreterProgramSelfCorrection(unittest.IsolatedAsyncioTestCase):

    async def test_successful_run_no_retries_needed(self):
        """Program succeeds on the first try, no program-level retries invoked."""
        steps = [{"code": {"lang": "python", "script": "result = {'status': 'ok'}", "def": "final_res"}}]
        schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}

        program = create_program_correction_test_program(
            workflow_steps=steps,
            output_schema_dict=schema,
            max_program_retries=1 # Allow retries, but shouldn't be used
        )
        interpreter = Interpreter(program)
        final_output = await interpreter.run()

        self.assertEqual(final_output, {"status": "ok"})
        # We can check logs or a (future) counter on interpreter to see if retries happened.
        # For now, success implies no retry was needed for validation.

    async def test_output_schema_error_triggers_retry_and_succeeds(self):
        """Program fails outputSchema, retries with error info, then succeeds."""

        # Script will check for 'pil_last_error_info' and change behavior
        script_def = """
if 'pil_last_error_info' in dir() and pil_last_error_info:
    result = {"data": "corrected_valid_data"} # Correct output on retry
else:
    result = {"data": 123} # Invalid output first time (string expected)
"""
        steps = [{"code": {"lang": "python", "script": script_def, "def": "final_res"}}]
        schema = {"type": "object", "properties": {"data": {"type": "string"}}, "required": ["data"]}
        # Define pil_last_error_info as an optional input
        input_spec = {"pil_last_error_info": "string"}


        program = create_program_correction_test_program(
            workflow_steps=steps,
            output_schema_dict=schema,
            max_program_retries=1,
            initial_vars_spec=input_spec
        )
        interpreter = Interpreter(program, debug_mode=True) # Enable debug for trace

        # Initial call with no pil_last_error_info
        final_output = await interpreter.run(inputs={})

        self.assertEqual(final_output, {"data": "corrected_valid_data"})

        # Verify retry occurred by checking trace logs (a bit indirect)
        # A better way would be to mock/spy parts of the interpreter or have counters.
        retry_log_found = any("PROGRAM_RETRYING" in entry.get("event", "") for entry in interpreter.trace_log)
        self.assertTrue(retry_log_found, "Program should have logged a retry attempt.")

        error_info_passed_on_retry = False
        for entry in interpreter.trace_log:
            if entry.get("event") == "PROGRAM_ATTEMPT_START" and entry.get("attempt") == 2:
                if "pil_last_error_info" in entry.get("current_run_inputs", {}):
                    self.assertIn("Previous execution attempt failed", entry["current_run_inputs"]["pil_last_error_info"])
                    self.assertIn("OutputValidationError", entry["current_run_inputs"]["pil_last_error_info"])
                    error_info_passed_on_retry = True
                break
        self.assertTrue(error_info_passed_on_retry, "pil_last_error_info should be in inputs for the retry attempt.")


    async def test_top_level_constraint_error_triggers_retry_and_succeeds(self):
        """Program passes schema but fails top-level constraints, retries, then succeeds."""
        script_def = """
if 'pil_last_error_info' in dir() and pil_last_error_info:
    result = "valid_final_string" # Correct output on retry
else:
    result = "short" # Fails length constraint on first try
"""
        steps = [{"code": {"lang": "python", "script": script_def, "def": "final_res"}}]
        # output_schema is simple, will pass "short"
        schema = {"type": "string"}
        # program_constraints will fail "short"
        prog_constraints = {"type": "string", "regex": "^valid_.*", "choices": ["valid_final_string", "another_valid"]}
        input_spec = {"pil_last_error_info": "string"}

        program = create_program_correction_test_program(
            workflow_steps=steps,
            output_schema_dict=schema,
            program_constraints_dict=prog_constraints,
            max_program_retries=1,
            initial_vars_spec=input_spec
        )
        interpreter = Interpreter(program, debug_mode=True)
        final_output = await interpreter.run(inputs={})

        self.assertEqual(final_output, "valid_final_string")
        retry_log_found = any("PROGRAM_RETRYING" in entry.get("event", "") for entry in interpreter.trace_log)
        self.assertTrue(retry_log_found, "Program should have logged a retry attempt for constraint violation.")

        error_info_passed_on_retry = False
        for entry in interpreter.trace_log:
            if entry.get("event") == "PROGRAM_ATTEMPT_START" and entry.get("attempt") == 2:
                if "pil_last_error_info" in entry.get("current_run_inputs", {}):
                    self.assertIn("ConstraintViolationError", entry["current_run_inputs"]["pil_last_error_info"])
                    error_info_passed_on_retry = True
                break
        self.assertTrue(error_info_passed_on_retry, "pil_last_error_info should be in inputs for the retry due to constraint.")


    async def test_all_retries_fail_output_schema(self):
        """Program fails outputSchema validation and exhausts all retries."""
        steps = [{"code": {"lang": "python", "script": "result = {'data': 123}", "def": "final_res"}}] # Always invalid
        schema = {"type": "object", "properties": {"data": {"type": "string"}}}

        program = create_program_correction_test_program(
            workflow_steps=steps,
            output_schema_dict=schema,
            max_program_retries=1
        )
        interpreter = Interpreter(program, debug_mode=True)

        with self.assertRaises(OutputValidationError) as cm:
            await interpreter.run()

        self.assertIn("123 is not of type 'string'", str(cm.exception))

        # Check that it attempted retries
        attempt_logs = [entry for entry in interpreter.trace_log if entry.get("event") == "PROGRAM_ATTEMPT_START"]
        self.assertEqual(len(attempt_logs), 2, "Should be 1 initial attempt + 1 retry attempt.")

        all_retries_failed_log = any("PROGRAM_ALL_RETRIES_FAILED" in entry.get("event", "") for entry in interpreter.trace_log)
        self.assertTrue(all_retries_failed_log, "Program should have logged that all retries failed.")


    async def test_no_retries_configured_fails_immediately(self):
        """Program fails validation, and with max_program_retries=0, fails immediately."""
        steps = [{"code": {"lang": "python", "script": "result = {'data': 123}", "def": "final_res"}}]
        schema = {"type": "object", "properties": {"data": {"type": "string"}}}

        program = create_program_correction_test_program(
            workflow_steps=steps,
            output_schema_dict=schema,
            max_program_retries=0 # NO retries
        )
        interpreter = Interpreter(program, debug_mode=True)

        with self.assertRaises(OutputValidationError):
            await interpreter.run()

        attempt_logs = [entry for entry in interpreter.trace_log if entry.get("event") == "PROGRAM_ATTEMPT_START"]
        self.assertEqual(len(attempt_logs), 1, "Should be only 1 initial attempt, no retries.")

        retry_log_found = any("PROGRAM_RETRYING" in entry.get("event", "") for entry in interpreter.trace_log)
        self.assertFalse(retry_log_found, "Program should not have logged a retry attempt.")


if __name__ == "__main__":
    unittest.main()
