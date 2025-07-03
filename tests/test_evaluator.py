import unittest
from unittest.mock import MagicMock, patch

from pil_interpreter.evaluator import Evaluator
from pil_interpreter.context import ExecutionContext
from pil_interpreter.exceptions import PILSyntaxError, PILSemanticError

class TestEvaluator(unittest.TestCase):

    def setUp(self):
        self.mock_context = MagicMock(spec=ExecutionContext)
        self.mock_context.variables = {} # Mock the dictionary directly for side_effect usage
        self.mock_context.conversation_history = []
        self.mock_context.persona_details = {}
        self.mock_context.global_parameters = {}

        # Helper to allow mock_context.set_variable to actually store variables for get_variable
        def mock_set_variable(name, value):
            self.mock_context.variables[name] = value

        def mock_get_variable(name, default=None):
            return self.mock_context.variables.get(name, default)

        def mock_add_history(role, content):
            self.mock_context.conversation_history.append({"role": role, "content": content})

        self.mock_context.set_variable.side_effect = mock_set_variable
        self.mock_context.get_variable.side_effect = mock_get_variable
        self.mock_context.add_history_entry.side_effect = mock_add_history

        self.minimal_program_data = {
            "workflow": {
                "steps": []
            }
        }

    def test_evaluator_init_success(self):
        program_data = {
            "config": {"parameters": {"temp": 0.5}},
            "persona": {"role": "tester"},
            "workflow": {"steps": []}
        }
        evaluator = Evaluator(program_data, self.mock_context)
        self.assertEqual(evaluator.program_data, program_data)
        self.assertEqual(evaluator.context, self.mock_context)
        self.mock_context.set_global_parameters.assert_called_once_with({"temp": 0.5})
        self.mock_context.set_persona.assert_called_once_with({"role": "tester"})

    def test_evaluator_init_invalid_program_data(self):
        with self.assertRaisesRegex(PILSyntaxError, "PIL program data must be a dictionary"):
            Evaluator("not a dict", self.mock_context)

    def test_evaluator_init_invalid_context(self):
        with self.assertRaisesRegex(TypeError, "Context must be an instance of ExecutionContext"):
            Evaluator({}, "not a context") # type: ignore

    def test_run_workflow_no_workflow_block(self):
        evaluator = Evaluator({}, self.mock_context)
        with self.assertRaisesRegex(PILSyntaxError, "No 'workflow' block found"):
            evaluator.run_workflow()

    def test_run_workflow_workflow_not_dict(self):
        evaluator = Evaluator({"workflow": "not a dict"}, self.mock_context)
        with self.assertRaisesRegex(PILSyntaxError, "'workflow' block must be a dictionary"):
            evaluator.run_workflow()

    def test_run_workflow_no_steps(self):
        # Should run without error, print warning (captured via stdout or check logs if implemented)
        evaluator = Evaluator({"workflow": {}}, self.mock_context)
        with patch('builtins.print') as mocked_print:
            evaluator.run_workflow()
            mocked_print.assert_any_call("Warning: Workflow has no steps.")

    def test_run_workflow_steps_not_list(self):
        program_data = {"workflow": {"steps": "not a list"}}
        evaluator = Evaluator(program_data, self.mock_context)
        with self.assertRaisesRegex(PILSyntaxError, "'steps' in workflow must be a list"):
            evaluator.run_workflow()

    def test_run_workflow_invalid_step_format_not_dict(self):
        program_data = {"workflow": {"steps": ["not a dict step"]}}
        evaluator = Evaluator(program_data, self.mock_context)
        with self.assertRaisesRegex(PILSemanticError, "not a valid dictionary with a single type key"):
            evaluator.run_workflow()

    def test_run_workflow_invalid_step_format_multiple_keys(self):
        program_data = {"workflow": {"steps": [{"prompt": {}, "tool": {}}]}} # two keys
        evaluator = Evaluator(program_data, self.mock_context)
        with self.assertRaisesRegex(PILSemanticError, "not a valid dictionary with a single type key"):
            evaluator.run_workflow()

    @patch('builtins.print') # To suppress print statements during test
    def test_handle_prompt_step_basic(self, mock_print):
        self.mock_context.variables = {"name": "World"}
        prompt_config = {
            "text": "Hello ${name}!",
            "def": "greeting_output"
        }
        program_data = {"workflow": {"steps": [{"prompt": prompt_config}]}}

        # Use a real context for this more integrated test of _handle_prompt_step
        real_context = ExecutionContext()
        real_context.set_variable("name", "World")
        evaluator = Evaluator(program_data, real_context)

        evaluator.run_workflow()

        self.assertEqual(real_context.get_variable("greeting_output"), "Mocked LLM Response to: \"Hello World!...\"")
        expected_history = [
            {"role": "user", "content": "Hello World!"},
            {"role": "assistant", "content": "Mocked LLM Response to: \"Hello World!...\""}
        ]
        # Allow for slight variations in mocked response if it's too brittle
        self.assertEqual(len(real_context.get_history()), 2)
        self.assertEqual(real_context.get_history()[0]["content"], "Hello World!")
        self.assertTrue(real_context.get_history()[1]["content"].startswith("Mocked LLM Response"))


    @patch('builtins.print')
    def test_handle_prompt_step_no_def(self, mock_print):
        self.mock_context.variables = {"item": "book"}
        prompt_config = {"text": "Describe the $item."}
        program_data = {"workflow": {"steps": [{"prompt": prompt_config}]}}

        real_context = ExecutionContext()
        real_context.set_variable("item", "book")
        evaluator = Evaluator(program_data, real_context)
        evaluator.run_workflow()

        # No variable should be defined in context from this step
        self.assertEqual(len(real_context.variables), 1) # Only 'item' should be there
        self.assertTrue(real_context.get_variable("item"), "book")

        expected_history = [
            {"role": "user", "content": "Describe the book."},
            {"role": "assistant", "content": "Mocked LLM Response to: \"Describe the book....\""}
        ]
        self.assertEqual(len(real_context.get_history()), 2)
        self.assertEqual(real_context.get_history()[0]["content"], "Describe the book.")

    def test_handle_prompt_step_missing_text(self):
        prompt_config = {"def": "output"} # Missing text
        program_data = {"workflow": {"steps": [{"prompt": prompt_config}]}}
        evaluator = Evaluator(program_data, ExecutionContext())
        with self.assertRaisesRegex(PILSemanticError, "Prompt step must have a 'text' field"):
            evaluator.run_workflow()

    def test_handle_prompt_step_invalid_def_type(self):
        prompt_config = {"text": "Hello", "def": 123} # def is not a string
        program_data = {"workflow": {"steps": [{"prompt": prompt_config}]}}
        evaluator = Evaluator(program_data, ExecutionContext())
        with self.assertRaisesRegex(PILSemanticError, "Prompt step 'def' field must be a string"):
            evaluator.run_workflow()

    def test_substitute_variables_various_cases(self):
        # Test this private method more directly
        evaluator = Evaluator(self.minimal_program_data, self.mock_context)

        self.mock_context.variables = {"name": "Alice", "action": "runs", "obj_count": 5}

        text = "My name is ${name}."
        self.assertEqual(evaluator._substitute_variables(text), "My name is Alice.")

        text = "$name $action fast."
        self.assertEqual(evaluator._substitute_variables(text), "Alice runs fast.")

        text = "There are ${obj_count} items."
        self.assertEqual(evaluator._substitute_variables(text), "There are 5 items.")

        text = "Undefined var: ${undefined_var} or $another_undefined."
        self.assertEqual(evaluator._substitute_variables(text), "Undefined var: ${undefined_var} or $another_undefined.")

        text = "No variables here."
        self.assertEqual(evaluator._substitute_variables(text), "No variables here.")

        text = "${name} has ${obj_count} ${item_type_undefined}."
        self.assertEqual(evaluator._substitute_variables(text), "Alice has 5 ${item_type_undefined}.")

        text = "This is $name's test. Not ${name}s." # 's should not be part of var name
        self.assertEqual(evaluator._substitute_variables(text), "This is Alice's test. Not Alices.")


    @patch('builtins.print')
    def test_run_workflow_unknown_step_type(self, mock_print):
        program_data = {"workflow": {"steps": [{"unknown_step": {"param": "value"}}]}}
        evaluator = Evaluator(program_data, self.mock_context)
        evaluator.run_workflow()
        mock_print.assert_any_call("  Warning: Unknown step type 'unknown_step' at step 1. Content: {'param': 'value'}")


if __name__ == "__main__":
    unittest.main()
