import unittest
from unittest.mock import patch, MagicMock # Added import
from typing import Dict, Any, List

from pil_engine.core.components import PilProgram, LoopStep, PromptStep, CodeStep, LoopType
from pil_engine.interpreter import Interpreter, PilParser
from pil_engine.core.context import Context

# Helper to quickly create a PilProgram for testing loop steps
def create_loop_test_program(loop_yaml_snippet: Dict[str, Any], initial_vars_spec: Dict[str, str] = None, include_llm_config: bool = False) -> PilProgram:
    program_dict = {
        "config": {},
        "workflow": {
            "steps": [
                loop_yaml_snippet # The loop step itself
            ]
        }
    }
    if include_llm_config: # Used for tests that involve PromptSteps
        program_dict["config"]["model"] = "test-model-for-loop"
        program_dict["config"]["api_key"] = "dummy_test_key_for_mocking"

    if initial_vars_spec:
        # Add input definitions based on the spec (name: type_str)
        program_dict["input"] = {"vars": initial_vars_spec}

    parser = PilParser()
    return parser.parse_dict(program_dict)

class TestInterpreterLoopStep(unittest.IsolatedAsyncioTestCase): # Changed base class

    @patch('openai.AsyncOpenAI') # Changed to AsyncOpenAI
    async def test_for_each_loop_simple_list(self, MockAsyncOpenAI): # Made test async
        # Configure the mock async client
        mock_client_instance = MockAsyncOpenAI.return_value

        # Simulate different responses based on input to distinguish iterations
        async def async_side_effect_func(*args, **kwargs): # Made side_effect async
            prompt_content = kwargs['messages'][-1]['content']
            mock_resp = MagicMock() # The response object itself doesn't need to be async for the mock
            mock_resp.choices = [MagicMock(message=MagicMock(content=f"Mocked: {prompt_content}"))]
            return mock_resp

        # Assign an AsyncMock to the create method with the async side_effect
        mock_client_instance.chat.completions.create = unittest.mock.AsyncMock(side_effect=async_side_effect_func)

        loop_yaml_snippet = {
            "for": "item in {{my_items}}", # Should be {{...}} to match updated LoopStep regex
            "steps": [
                {"prompt": {"text": "Processing {{ item }}", "def": "step_output"}}
            ],
            "def": "loop_results"
        }
        # Define the *specification* of inputs for the program
        input_vars_spec = {"my_items": "list"}
        # Define the *actual values* for those inputs for this run
        actual_input_values = {"my_items": ["apple", "banana"]}

        program = create_loop_test_program(loop_yaml_snippet, initial_vars_spec=input_vars_spec, include_llm_config=True)

        # Interpreter no longer needs initial_vars if they are passed to run()
        interpreter = Interpreter(pil_program=program, debug_mode=False)
        MockAsyncOpenAI.assert_called_with(api_key="dummy_test_key_for_mocking")

        final_output = await interpreter.run(inputs=actual_input_values) # Pass actual values to run

        loop_output_in_context = interpreter.context.get_variable("loop_results")
        self.assertIsInstance(loop_output_in_context, list)
        self.assertEqual(len(loop_output_in_context), 2)
        # PromptStep output is simulated, so we check for the template rendered
        self.assertIn("Processing apple", loop_output_in_context[0])
        self.assertIn("Processing banana", loop_output_in_context[1])

        # Check loop variable scope - should not exist outside
        self.assertFalse(interpreter.context.has_variable("item"))

    def test_for_range_loop_single_arg(self):
        loop_yaml_snippet = {
            "for": "i in range(3)",
            "steps": [
                {"code": {"lang": "python", "script": "result = i * 2", "def": "iter_res"}}
            ],
            "def": "range_loop_output"
        }
        program = create_loop_test_program(loop_yaml_snippet)
        interpreter = Interpreter(pil_program=program, debug_mode=False)
        interpreter.run()

        loop_results = interpreter.context.get_variable("range_loop_output")
        self.assertEqual(loop_results, [0, 2, 4]) # 0*2, 1*2, 2*2

    def test_for_range_loop_dynamic_args(self):
        loop_yaml_snippet = {
            "for": "val in range({{start_val}}, {{end_val}})", # Changed to {{...}}
            "steps": [
                {"code": {"lang": "python", "script": "result = val + 1", "def": "current_val"}}
            ],
            "def": "range_results_dynamic"
        }
        initial_vars = {"start_val": 1, "end_val": 4} # range(1,4) -> 1,2,3
        program = create_loop_test_program(loop_yaml_snippet, initial_vars=initial_vars)
        interpreter = Interpreter(pil_program=program, initial_vars=initial_vars, debug_mode=False)
        interpreter.run()

        loop_output = interpreter.context.get_variable("range_results_dynamic")
        self.assertEqual(loop_output, [2, 3, 4]) # 1+1, 2+1, 3+1

    def test_while_loop_simple_condition(self):
        loop_yaml_snippet = {
            "while": "{{counter}} < 3",
            "steps": [
                {"code": {"lang": "python", "script": "result = counter", "def": "captured_value_for_iteration"}},
                {"code": {"lang": "python", "script": "result = counter + 1", "def": "counter"}} # Updates counter in main context
            ],
            "def": "while_loop_res" # Collects results of the last step in 'steps', which is the new counter value. This is not what we want to assert for [0,1,2].
        }
        # To assert [0,1,2], the loop's 'def' should collect the 'captured_value_for_iteration'.
        # This means the step defining 'captured_value_for_iteration' must be the LAST step in the iteration for the loop's 'def' to pick it up.
        # Let's adjust:
        loop_yaml_snippet_corrected = {
            "while": "{{counter}} < 3",
            "steps": [
                {"code": {"lang": "python", "script": "result = counter + 1", "def": "counter"}}, # Update counter first
                {"code": {"lang": "python", "script": "result = counter -1", "def": "value_to_collect"}} # Then calculate the value that was just used in condition (effectively)
            ],
            "def": "while_loop_res"
        }
        loop_yaml_snippet_final = {
             "while": "{{counter}} < 3",
             "steps": [
                 {"code": {"lang": "python", "script": "result = counter + 1", "def": "counter"}}, # Update counter first
                 {"code": {"lang": "python", "script": "result = counter - 1", "def": "value_to_collect_is_old_counter"}} # This is the value collected
             ],
             "def": "while_loop_res"
        }

        initial_vars = {"counter": 0}
        program = create_loop_test_program(loop_yaml_snippet_final, initial_vars=initial_vars)
        interpreter = Interpreter(pil_program=program, initial_vars=initial_vars, debug_mode=False)
        interpreter.run()

        loop_output = interpreter.context.get_variable("while_loop_res")
        self.assertEqual(loop_output, [0, 1, 2])
        self.assertEqual(interpreter.context.get_variable("counter"), 3)
        # Variable defined by a step inside a WHILE loop should persist in the main context
        self.assertTrue(interpreter.context.has_variable("value_to_collect_is_old_counter"))
        # Its final value would be from the last iteration where counter was 3, so result = 3 - 1 = 2
        self.assertEqual(interpreter.context.get_variable("value_to_collect_is_old_counter"), 2)


    def test_loop_variable_scoping_for_each(self):
        # Test that a variable defined inside a for-each loop iteration does not leak to subsequent iterations or outside
        loop_yaml_snippet = {
            "for": "item in ${my_list}", # Note: Will change to {{my_list}} later
            "steps": [
                {"code": {"lang": "python", "script": "result = item * 10", "def": "inner_var_in_context"}},
                {"code": {"lang": "python", "script": "result = {{inner_var_in_context}}", "def": "current_iter_output"}}
            ],
            "def": "collected_outputs"
        }
        initial_vars = {"my_list": [1, 2]} # my_list will be used by {{my_list}}
        program = create_loop_test_program(loop_yaml_snippet, initial_vars=initial_vars)
        interpreter = Interpreter(pil_program=program, initial_vars=initial_vars, debug_mode=True)
        interpreter.run()

        results = interpreter.context.get_variable("collected_outputs")
        # Expected:
        # Iter 1: item=1. inner_var=10. result = 10 + 0 = 10. inner_var_check becomes 10.
        # Iter 2: item=2. inner_var=20 (new scope). result = 20 + 0 (because inner_var_check from previous scope should not be visible) = 20.
        # If inner_var leaked, result for iter 2 would be 20 + 10 = 30.
        # The globals().get part is a bit of a hack for testing, ideally context scoping handles this cleanly.
        # The current implementation of _execute_loop_step re-initializes context for each FOR_EACH iteration, so this should pass.
        self.assertEqual(results, [10, 20])

        self.assertFalse(interpreter.context.has_variable("inner_var_in_context"))
        # current_iter_output is defined by the last step in the loop, and then collected by the loop's def_var.
        # So collected_outputs will have the list of current_iter_output values.
        # The variable 'current_iter_output' itself, from the step's def, should also be scoped to the iteration.
        self.assertFalse(interpreter.context.has_variable("current_iter_output"))

    async def test_for_range_loop_single_arg(self):
        loop_yaml_snippet = {
            "for": "i in range(3)",
            "steps": [
                {"code": {"lang": "python", "script": "result = i * 2", "def": "iter_res"}}
            ],
            "def": "range_loop_output"
        }
        program = create_loop_test_program(loop_yaml_snippet) # No initial_vars_spec needed as range is static
        interpreter = Interpreter(pil_program=program, debug_mode=False)
        await interpreter.run()

        loop_results = interpreter.context.get_variable("range_loop_output")
        self.assertEqual(loop_results, [0, 2, 4])

    async def test_for_range_loop_dynamic_args(self):
        loop_yaml_snippet = {
            "for": "val in range({{start_val}}, {{end_val}})",
            "steps": [
                {"code": {"lang": "python", "script": "result = val + 1", "def": "current_val"}}
            ],
            "def": "range_results_dynamic"
        }
        input_vars_spec = {"start_val": "integer", "end_val": "integer"}
        actual_input_values = {"start_val": 1, "end_val": 4}
        program = create_loop_test_program(loop_yaml_snippet, initial_vars_spec=input_vars_spec)
        interpreter = Interpreter(pil_program=program, debug_mode=False)
        await interpreter.run(inputs=actual_input_values)

        loop_output = interpreter.context.get_variable("range_results_dynamic")
        self.assertEqual(loop_output, [2, 3, 4])

    async def test_while_loop_simple_condition(self):
        loop_yaml_snippet_final = {
             "while": "{{counter}} < 3",
             "steps": [
                 {"code": {"lang": "python", "script": "result = counter + 1", "def": "counter"}},
                 {"code": {"lang": "python", "script": "result = counter - 1", "def": "value_to_collect_is_old_counter"}}
             ],
             "def": "while_loop_res"
        }
        input_vars_spec = {"counter": "integer"}
        actual_input_values = {"counter": 0}
        program = create_loop_test_program(loop_yaml_snippet_final, initial_vars_spec=input_vars_spec)
        interpreter = Interpreter(pil_program=program, debug_mode=False)
        await interpreter.run(inputs=actual_input_values)

        loop_output = interpreter.context.get_variable("while_loop_res")
        self.assertEqual(loop_output, [0, 1, 2])
        self.assertEqual(interpreter.context.get_variable("counter"), 3)
        self.assertTrue(interpreter.context.has_variable("value_to_collect_is_old_counter"))
        self.assertEqual(interpreter.context.get_variable("value_to_collect_is_old_counter"), 2)

    async def test_loop_variable_scoping_for_each(self):
        loop_yaml_snippet = {
            "for": "item in {{my_list}}", # Should be {{...}}
            "steps": [
                {"code": {"lang": "python", "script": "result = item * 10", "def": "inner_var_in_context"}},
                {"code": {"lang": "python", "script": "result = {{inner_var_in_context}}", "def": "current_iter_output"}}
            ],
            "def": "collected_outputs"
        }
        input_vars_spec = {"my_list": "list"}
        actual_input_values = {"my_list": [1, 2]}
        program = create_loop_test_program(loop_yaml_snippet, initial_vars_spec=input_vars_spec)
        interpreter = Interpreter(pil_program=program, debug_mode=True)
        await interpreter.run(inputs=actual_input_values)

        results = interpreter.context.get_variable("collected_outputs")
        self.assertEqual(results, [10, 20])
        self.assertFalse(interpreter.context.has_variable("inner_var_in_context"))
        self.assertFalse(interpreter.context.has_variable("current_iter_output"))

    async def test_for_each_empty_list(self):
        loop_yaml_snippet = {
            "for": "item in {{empty_list}}", # Should be {{...}}
            "steps": [{"prompt": {"text": "This should not run", "def": "dummy"}}],
            "def": "loop_output_empty"
        }
        input_vars_spec = {"empty_list": "list"}
        actual_input_values = {"empty_list": []}
        program = create_loop_test_program(loop_yaml_snippet, initial_vars_spec=input_vars_spec)
        interpreter = Interpreter(pil_program=program)
        await interpreter.run(inputs=actual_input_values)

        results = interpreter.context.get_variable("loop_output_empty")
        self.assertEqual(results, [])

    async def test_while_loop_condition_initially_false(self):
        loop_yaml_snippet = {
            "while": "{{flag}} == True",
            "steps": [{"prompt": {"text": "Not executed", "def": "dummy"}}],
            "def": "while_false_output"
        }
        input_vars_spec = {"flag": "boolean"}
        actual_input_values = {"flag": False}
        program = create_loop_test_program(loop_yaml_snippet, initial_vars_spec=input_vars_spec)
        interpreter = Interpreter(pil_program=program)
        await interpreter.run(inputs=actual_input_values)

        results = interpreter.context.get_variable("while_false_output")
        self.assertEqual(results, [])

    async def test_loop_without_def_var(self):
        loop_yaml_snippet = {
            "for": "i in range(1)",
            "steps": [
                 {"code": {"lang": "python", "script": "side_effect_var = i + 100"}}
            ]
        }
        program = create_loop_test_program(loop_yaml_snippet)
        interpreter = Interpreter(pil_program=program)
        await interpreter.run() # await

        # but Python CodeStep uses asteval, which sandboxes.
        # Here, we primarily test that it runs and doesn't try to def a variable.
        # The 'side_effect_var' would be in the iteration's sandbox context, not the main one.
        self.assertFalse(interpreter.context.has_variable("side_effect_var")) # Correctly not in global context

        # Verify no default variable name was accidentally created by the loop
        self.assertFalse(any(k.startswith("loop_") for k in interpreter.context.get_all_variables().keys()),
                         "No default loop output variable should be created if 'def' is missing.")

    async def test_for_range_loop_with_step(self): # async
        loop_yaml_snippet = {
            "for": "k in range(1, 6, 2)",
            "steps": [{"code": {"lang": "python", "script": "result = k", "def": "v"}}],
            "def": "range_step_results"
        }
        program = create_loop_test_program(loop_yaml_snippet)
        interpreter = Interpreter(pil_program=program)
        await interpreter.run() # await
        self.assertEqual(interpreter.context.get_variable("range_step_results"), [1, 3, 5])

    async def test_nested_loops(self): # async
        outer_loop_yaml_snippet = {
            "for": "i in range(2)",
            "steps": [
                {
                    "for": "j in range(2)",
                    "steps": [
                        {"code": {"lang": "python", "script": "result = (i * 10) + j", "def": "calc_val"}}
                    ],
                    "def": "inner_loop_results_for_i"
                }
            ],
            "def": "outer_loop_total_results"
        }
        program = create_loop_test_program(outer_loop_yaml_snippet)
        interpreter = Interpreter(pil_program=program, debug_mode=False)
        await interpreter.run() # await

        expected_results = [
            [0, 1],
            [10, 11]
        ]
        self.assertEqual(interpreter.context.get_variable("outer_loop_total_results"), expected_results)

        self.assertFalse(interpreter.context.has_variable("i"))
        self.assertFalse(interpreter.context.has_variable("j"))
        self.assertFalse(interpreter.context.has_variable("calc_val"))
        self.assertFalse(interpreter.context.has_variable("inner_loop_results_for_i"))


if __name__ == '__main__':
    unittest.main()

print("Created tests/test_interpreter_loop_step.py with various loop test cases.")
