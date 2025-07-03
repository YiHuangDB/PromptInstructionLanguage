import unittest
from unittest.mock import MagicMock, patch, ANY
from io import StringIO # Added
import openai # For APIError and mocking client
from openai.types.chat import ChatCompletionMessage, ChatCompletion
from openai.types.chat.chat_completion import Choice


from pil_interpreter.evaluator import Evaluator, DEFAULT_MODEL
from pil_interpreter.context import ExecutionContext
from pil_interpreter.exceptions import PILSyntaxError, PILSemanticError

class TestEvaluator(unittest.TestCase):

    def setUp(self):
        self.mock_openai_client = MagicMock(spec=openai.OpenAI)

        # Mock the response structure for chat.completions.create
        self.mock_chat_completion = MagicMock(spec=ChatCompletion)
        self.mock_chat_completion_message = MagicMock(spec=ChatCompletionMessage)
        self.mock_chat_completion_message.content = "Mocked AI Response"
        self.mock_choice = MagicMock(spec=Choice)
        self.mock_choice.message = self.mock_chat_completion_message
        self.mock_chat_completion.choices = [self.mock_choice]
        self.mock_openai_client.chat.completions.create.return_value = self.mock_chat_completion

        self.minimal_program_data = {
            "workflow": { "steps": [] }
        }

    def _create_real_context(self):
        ctx = ExecutionContext()
        # Below side effects are needed if we don't use a fully MagicMock'd context
        # but for these tests, a real context is better for _handle_prompt_step
        return ctx

    def test_evaluator_init_success_with_client(self):
        program_data = {
            "config": {"parameters": {"temp": 0.5}, "model": "gpt-test"},
            "persona": {"role": "test persona"},
            "workflow": {"steps": []}
        }
        context = self._create_real_context()
        evaluator = Evaluator(program_data, context, openai_client=self.mock_openai_client)
        self.assertEqual(evaluator.program_data, program_data)
        self.assertEqual(evaluator.context, context)
        self.assertEqual(evaluator.openai_client, self.mock_openai_client)
        self.assertEqual(context.get_global_parameters()["temp"], 0.5)
        self.assertEqual(context.get_global_parameters()["model"], "gpt-test")
        self.assertEqual(context.get_persona()["role"], "test persona")

    def test_evaluator_init_success_no_client(self):
        context = self._create_real_context()
        evaluator = Evaluator(self.minimal_program_data, context, openai_client=None)
        self.assertIsNone(evaluator.openai_client)

    def test_evaluator_init_invalid_client_type(self):
        context = self._create_real_context()
        with self.assertRaisesRegex(TypeError, "openai_client must be an instance of openai.OpenAI or None"):
            Evaluator(self.minimal_program_data, context, openai_client="not a client") # type: ignore

    # ... (keep other init tests like invalid_program_data, invalid_context) ...
    def test_evaluator_init_invalid_program_data(self):
        with self.assertRaisesRegex(PILSyntaxError, "PIL program data must be a dictionary"):
            Evaluator("not a dict", self._create_real_context())

    def test_evaluator_init_invalid_context(self):
        with self.assertRaisesRegex(TypeError, "Context must be an instance of ExecutionContext"):
            Evaluator({}, "not a context") # type: ignore


    # ... (keep workflow structure tests: no_workflow_block, workflow_not_dict, etc.) ...
    def test_run_workflow_no_workflow_block(self):
        evaluator = Evaluator({}, self._create_real_context(), openai_client=self.mock_openai_client)
        with self.assertRaisesRegex(PILSyntaxError, "No 'workflow' block found"):
            evaluator.run_workflow()

    @patch('builtins.print')
    def test_handle_prompt_step_with_actual_client_mock(self, mock_print):
        context = self._create_real_context()
        context.set_variable("name", "TestUser")
        context.set_persona({"role": "Test Assistant Persona"})
        context.add_history_entry("user", "Previous question")
        context.add_history_entry("assistant", "Previous answer")

        program_data = {
            "config": {"model": "gpt-configured-model", "parameters": {"temperature": 0.2}},
            "workflow": {
                "steps": [{
                    "prompt": {
                        "text": "Hello {{ name }}, how are you?",
                        "def": "ai_response"
                    }
                }]
            }
        }
        evaluator = Evaluator(program_data, context, openai_client=self.mock_openai_client)
        evaluator.run_workflow()

        self.mock_openai_client.chat.completions.create.assert_called_once()
        call_args = self.mock_openai_client.chat.completions.create.call_args

        self.assertEqual(call_args.kwargs['model'], "gpt-configured-model")
        self.assertEqual(call_args.kwargs['temperature'], 0.2)

        expected_messages = [
            {"role": "system", "content": "Test Assistant Persona"},
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
            {"role": "user", "content": "Hello TestUser, how are you?"}
        ]
        self.assertEqual(call_args.kwargs['messages'], expected_messages)

        self.assertEqual(context.get_variable("ai_response"), "Mocked AI Response")
        self.assertEqual(context.get_history()[-1]["content"], "Mocked AI Response")
        self.assertEqual(context.get_history()[-2]["content"], "Hello TestUser, how are you?")


    @patch('builtins.print')
    def test_handle_prompt_step_no_client_fallback_to_mock(self, mock_print):
        context = self._create_real_context()
        context.set_variable("item", "widget")
        program_data = {
            "workflow": {
                "steps": [{"prompt": {"text": "Info on {{ item }}", "def": "info_out"}}]
            }
        }
        evaluator = Evaluator(program_data, context, openai_client=None) # NO client
        evaluator.run_workflow()

        mock_print.assert_any_call("    Warning: OpenAI client not available. Using mocked LLM response.", file=ANY)
        self.assertTrue(context.get_variable("info_out").startswith("Mocked LLM Response to:"))
        self.assertEqual(context.get_history()[-2]["content"], "Info on widget")


    @patch('builtins.print')
    def test_handle_prompt_step_openai_api_error(self, mock_print):
        self.mock_openai_client.chat.completions.create.side_effect = openai.APIError("Test API Error", request=MagicMock(), body=None) # type: ignore

        context = self._create_real_context()
        context.set_variable("query", "failing query")
        program_data = {
             "config": {"model": "gpt-error-model"},
            "workflow": {
                "steps": [{"prompt": {"text": "Process {{ query }}", "def": "error_output"}}]
            }
        }
        evaluator = Evaluator(program_data, context, openai_client=self.mock_openai_client)
        evaluator.run_workflow()

        self.mock_openai_client.chat.completions.create.assert_called_once()
        self.assertTrue(context.get_variable("error_output").startswith("ERROR: OpenAI API Error:"))
        self.assertEqual(context.get_history()[-2]["content"], "Process failing query")
        self.assertTrue(context.get_history()[-1]["content"].startswith("ERROR: OpenAI API Error:"))

        # Make the assertion more robust to exact APIError string representation
        found_matching_call = False
        for call in mock_print.call_args_list:
            args, kwargs = call
            if args and isinstance(args[0], str):
                if "OpenAI API Error" in args[0] and "Test API Error" in args[0]:
                    if kwargs.get('file') is ANY or kwargs.get('file') == __import__('sys').stderr:
                        found_matching_call = True
                        break
        self.assertTrue(found_matching_call, "Expected print call with API error message not found.")


    @patch('builtins.print')
    def test_handle_prompt_step_default_model_used(self, mock_print):
        # No model in config
        program_data = {"workflow": {"steps": [{"prompt": {"text": "Test prompt"}}]}}
        context = self._create_real_context()
        evaluator = Evaluator(program_data, context, openai_client=self.mock_openai_client)
        evaluator.run_workflow()

        self.mock_openai_client.chat.completions.create.assert_called_once()
        call_args = self.mock_openai_client.chat.completions.create.call_args
        self.assertEqual(call_args.kwargs['model'], DEFAULT_MODEL) # Check if default model is used


    # Keep tests for missing text, invalid def type, substitute_variables, unknown_step_type
    # They should be mostly unaffected or require minor tweaks to use real_context and pass client
    def test_handle_prompt_step_missing_text(self):
        prompt_config = {"def": "output"}
        program_data = {"workflow": {"steps": [{"prompt": prompt_config}]}}
        evaluator = Evaluator(program_data, self._create_real_context(), openai_client=self.mock_openai_client)
        with self.assertRaisesRegex(PILSemanticError, "Prompt step must have a 'text' field"):
            evaluator.run_workflow()

    def test_handle_prompt_step_invalid_def_type(self):
        prompt_config = {"text": "Hello", "def": 123}
        program_data = {"workflow": {"steps": [{"prompt": prompt_config}]}}
        evaluator = Evaluator(program_data, self._create_real_context(), openai_client=self.mock_openai_client)
        with self.assertRaisesRegex(PILSemanticError, "Prompt step 'def' field must be a string"):
            evaluator.run_workflow()

    def test_substitute_variables_various_cases(self):
        context = self._create_real_context()
        evaluator = Evaluator(self.minimal_program_data, context, openai_client=self.mock_openai_client)

        context.set_variable("name", "Alice")
        context.set_variable("action", "runs")
        context.set_variable("obj_count", 5)

        text = "My name is {{ name }}." # Corrected this line
        self.assertEqual(evaluator._substitute_variables(text), "My name is Alice.")

        text = "{{ name }} {{ action }} fast."
        self.assertEqual(evaluator._substitute_variables(text), "Alice runs fast.")

        text = "There are {{ obj_count }} items."
        self.assertEqual(evaluator._substitute_variables(text), "There are 5 items.")

        # Jinja2 renders undefined variables as empty strings by default
        text = "Undefined var: {{ undefined_var }} or {{ another_undefined }}."
        self.assertEqual(evaluator._substitute_variables(text), "Undefined var:  or .")

        text = "No variables here."
        self.assertEqual(evaluator._substitute_variables(text), "No variables here.")

        text = "{{ name }} has {{ obj_count }} {{ item_type_undefined }}."
        self.assertEqual(evaluator._substitute_variables(text), "Alice has 5 .")

        # Test dictionary access
        context.set_variable("my_dict", {"key": "value", "count": 10})
        text = "Dict value: {{ my_dict.key }}, count: {{ my_dict.count }}."
        self.assertEqual(evaluator._substitute_variables(text), "Dict value: value, count: 10.")
        text = "Non-existent key: {{ my_dict.non_existent_key }}." # Renders empty
        self.assertEqual(evaluator._substitute_variables(text), "Non-existent key: .")

        # Test with default filter (though not explicitly enabling many filters yet)
        # Jinja2's default env doesn't have many filters, but `default` is usually available via `jinja2.defaults.DEFAULT_FILTERS`
        # For this test, we'll rely on the basic undefined behavior.
        # A more explicit test for filters would require adding them to the environment.
        # text = "Value or default: {{ undefined_var | default('fallback') }}."
        # self.assertEqual(evaluator._substitute_variables(text), "Value or default: fallback.")

        # Test syntax error in template string
        text = "This has an {% invalid jinja syntax %}"
        with patch('sys.stderr', new_callable=StringIO) as mock_stderr: # Corrected here
            self.assertEqual(evaluator._substitute_variables(text), text) # Should return original on syntax error
            self.assertIn("Jinja2 syntax error", mock_stderr.getvalue())


    @patch('builtins.print')
    def test_run_workflow_unknown_step_type(self, mock_print):
        program_data = {"workflow": {"steps": [{"unknown_step": {"param": "value"}}]}}
        evaluator = Evaluator(program_data, self._create_real_context(), openai_client=self.mock_openai_client)
        evaluator.run_workflow()
        mock_print.assert_any_call("  Warning: Unknown step type 'unknown_step' at step 1. Content: {'param': 'value'}", file=ANY)


if __name__ == "__main__":
    unittest.main()
