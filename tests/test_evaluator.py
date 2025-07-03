import unittest
from unittest.mock import MagicMock, patch, ANY
from io import StringIO
import openai # For APIError and mocking client
import os     # Added
import json   # Added
from openai.types.chat import ChatCompletionMessage, ChatCompletion
from openai.types.chat.chat_completion import Choice


from pil_interpreter.evaluator import Evaluator, DEFAULT_MODEL
from pil_interpreter.context import ExecutionContext
from pil_interpreter.exceptions import PILSyntaxError, PILSemanticError, PILError # Added PILError

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

    @patch('builtins.print') # Ensuring this line is correctly indented
    def test_run_workflow_unknown_step_type(self, mock_print):
        program_data = {"workflow": {"steps": [{"unknown_step": {"param": "value"}}]}}
        evaluator = Evaluator(program_data, self._create_real_context(), openai_client=self.mock_openai_client)
        evaluator.run_workflow()
        mock_print.assert_any_call("  Warning: Unknown step type 'unknown_step' at step 1. Content: {'param': 'value'}", file=ANY)

# --- Tests for _handle_retrieve_step ---
class TestRetrieveStep(unittest.TestCase): # Ensure this class is at column 0
    def setUp(self):
        self.test_dir = "test_kb_files"
        os.makedirs(self.test_dir, exist_ok=True)
        self.kb_path = os.path.join(self.test_dir, "test_kb.json")
        self.sample_kb_data = [
            {"id": "r1", "content": "Info about apples and bananas", "keywords": ["fruit", "apple"]},
            {"id": "r2", "content": "The best apples are green", "keywords": ["apple", "green"]},
            {"id": "r3", "content": "Oranges and citrus fruits", "keywords": ["fruit", "orange"]},
            {"id": "r4", "content": "Another document about nothing specific", "keywords": ["generic"]},
        ]
        with open(self.kb_path, 'w') as f:
            json.dump(self.sample_kb_data, f)

        self.context = ExecutionContext()
        # Mock OpenAI client, though not used directly by retrieve, Evaluator expects it
        self.mock_openai_client = MagicMock(spec=openai.OpenAI)
        self.program_data_template = {"workflow": {"steps": [{"retrieve": {}}]}}


    def tearDown(self):
        # Robustly remove all files in test_dir before removing the directory
        if os.path.exists(self.test_dir):
            for item in os.listdir(self.test_dir):
                item_path = os.path.join(self.test_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    # Could add elif os.path.isdir(item_path): shutil.rmtree(item_path) for subdirs
                except Exception as e:
                    print(f"Warning: Failed to delete {item_path} during teardown: {e}")
            try:
                os.rmdir(self.test_dir)
            except Exception as e:
                print(f"Warning: Failed to delete directory {self.test_dir} during teardown: {e}")


    def _run_retrieve_step(self, retrieve_config):
        self.program_data_template["workflow"]["steps"][0]["retrieve"] = retrieve_config
        evaluator = Evaluator(self.program_data_template, self.context, self.mock_openai_client)
        # Removed patch('builtins.print') from here to see if it resolves assertRaises issue
        evaluator.run_workflow()


    def test_retrieve_successful_match_content(self):
        config = {"from": self.kb_path, "query": "apples", "k": 2, "def": "docs"}
        self._run_retrieve_step(config)
        retrieved = self.context.get_variable("docs")
        self.assertEqual(len(retrieved), 2)
        self.assertTrue(any(d["id"] == "r1" for d in retrieved))
        self.assertTrue(any(d["id"] == "r2" for d in retrieved))

    def test_retrieve_successful_match_keywords(self):
        config = {"from": self.kb_path, "query": "orange", "k": 1, "def": "citrus_docs"}
        self._run_retrieve_step(config)
        retrieved = self.context.get_variable("citrus_docs")
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0]["id"], "r3")

    def test_retrieve_k_parameter_respected(self):
        config = {"from": self.kb_path, "query": "fruit", "k": 1, "def": "one_fruit_doc"}
        self._run_retrieve_step(config)
        retrieved = self.context.get_variable("one_fruit_doc")
        self.assertEqual(len(retrieved), 1)
        # The order might depend on scoring, so check if it's one of the expected
        self.assertIn(retrieved[0]["id"], ["r1", "r3"])


    def test_retrieve_variable_substitution(self):
        self.context.set_variable("kb_file", self.kb_path)
        self.context.set_variable("search_term", "green apples")
        config = {"from": "{{ kb_file }}", "query": "{{ search_term }}", "k": 1, "def": "green_docs"}
        self._run_retrieve_step(config)
        retrieved = self.context.get_variable("green_docs")
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0]["id"], "r2")


    def test_retrieve_file_not_found(self):
        config = {"from": "non_existent.json", "query": "test", "k": 1, "def": "error_docs"}
        with self.assertRaisesRegex(PILError, "Knowledge base file not found"):
            self._run_retrieve_step(config)

    def test_retrieve_malformed_json(self):
        malformed_json_path = os.path.join(self.test_dir, "malformed.json")
        with open(malformed_json_path, 'w') as f:
            f.write("[{'id': 'bad'}]") # Single quotes are invalid JSON

        config = {"from": malformed_json_path, "query": "test", "k": 1, "def": "error_docs"}
        with self.assertRaisesRegex(PILSyntaxError, "Invalid JSON"):
            self._run_retrieve_step(config)
        os.remove(malformed_json_path)

    def test_retrieve_kb_not_a_list(self):
        not_list_kb_path = os.path.join(self.test_dir, "not_list_kb.json")
        with open(not_list_kb_path, 'w') as f:
            json.dump({"error": "not a list"}, f)

        config = {"from": not_list_kb_path, "query": "test", "k": 1, "def": "error_docs"}
        with self.assertRaisesRegex(PILSemanticError, "must contain a JSON list of documents"):
            self._run_retrieve_step(config)
        os.remove(not_list_kb_path)

    def test_retrieve_invalid_k_value(self):
        config = {"from": self.kb_path, "query": "test", "k": -1, "def": "error_docs"}
        with self.assertRaisesRegex(PILSemanticError, "'k' must be a non-negative integer"):
            self._run_retrieve_step(config)

        config_str_k = {"from": self.kb_path, "query": "test", "k": "one", "def": "error_docs"}
        with self.assertRaisesRegex(PILSemanticError, "'k' must be a non-negative integer"):
            self._run_retrieve_step(config_str_k)


    def test_retrieve_missing_parameters(self):
        mandatory_keys = {"from": self.kb_path, "query": "q", "def": "d"}
        # 'k' is optional as it has a default in the implementation

        for key_to_remove in mandatory_keys.keys():
            config = mandatory_keys.copy()
            # Add 'k' back temporarily as it's not what we are testing for removal here,
            # but its absence would be fine. We are testing removal of mandatory ones.
            config_to_test = mandatory_keys.copy()
            if 'k' not in config_to_test : config_to_test['k'] = 1 # ensure k is present for this test setup

            del config_to_test[key_to_remove]

            # If 'k' was the one removed for this iteration, and it's optional, skip asserting error
            # This test is for *mandatory* keys.
            # Actually, the loop is over mandatory_keys, so 'k' is not included.

            with self.assertRaises(PILSemanticError, msg=f"Failed for missing mandatory key: {key_to_remove}"):
                self._run_retrieve_step(config_to_test)

    @patch('builtins.print') # Apply patch here
    def test_retrieve_empty_query(self, mock_print_for_test): # Add mock argument
        config = {"from": self.kb_path, "query": "", "k": 3, "def": "empty_query_docs"}
        expected_msg = "Retrieve step must have a 'query' field as a string template."

        # Inlined logic from _run_retrieve_step for this specific test
        # self.context and self.mock_openai_client are from setUp of TestRetrieveStep
        program_data_template = {"workflow": {"steps": [{"retrieve": config}]}}
        evaluator = Evaluator(program_data_template, self.context, self.mock_openai_client)

        with self.assertRaises(PILSemanticError) as cm:
            evaluator.run_workflow() # Direct call that should raise
        self.assertEqual(str(cm.exception), expected_msg)


    def test_retrieve_no_matching_documents(self):
        config = {"from": self.kb_path, "query": "qwertyuiopasdfghjkl", "k": 3, "def": "no_match_docs"}
        self._run_retrieve_step(config)
        retrieved = self.context.get_variable("no_match_docs")
        self.assertEqual(len(retrieved), 0)


if __name__ == "__main__":
    unittest.main()

# Need to re-add main test execution for all tests if this file is run directly
# For example, by creating a suite or running individual test classes
# if __name__ == '__main__':
#     suite = unittest.TestSuite()
#     suite.addTest(unittest.makeSuite(TestEvaluator)) # Assuming TestEvaluator is the original class
#     suite.addTest(unittest.makeSuite(TestRetrieveStep))
#     runner = unittest.TextTestRunner()
#     runner.run(suite)


# --- Tests for _handle_code_step ---
class TestCodeStep(unittest.TestCase):
    def setUp(self):
        self.context = ExecutionContext()
        self.mock_openai_client = MagicMock(spec=openai.OpenAI) # Evaluator expects it
        self.program_data_template = {"workflow": {"steps": [{"code": {}}]}}

    def _run_code_step(self, code_config):
        self.program_data_template["workflow"]["steps"][0]["code"] = code_config
        evaluator = Evaluator(self.program_data_template, self.context, self.mock_openai_client)
        # Using @patch on the method or a context manager for print if needed for assertions
        # For now, let prints go to stdout for these tests unless asserting specific prints
        evaluator.run_workflow()

    def test_code_step_successful_execution_with_def(self):
        self.context.set_variable("x", 10)
        self.context.set_variable("y", 5)
        script = "result = x * y + 2"
        config = {"lang": "python", "script": script, "def": "result"}

        self._run_code_step(config)

        self.assertEqual(self.context.get_variable("result"), 52)

    def test_code_step_successful_execution_no_def(self):
        self.context.set_variable("my_list", [])
        # This script modifies 'my_list' in the execution_scope.
        # The current implementation of _handle_code_step uses execution_scope = self.context.variables.copy()
        # so direct modification of mutable objects in context won't happen unless we change that.
        # For this test to pass as expected (my_list in context NOT changed), this is correct.
        # If we wanted in-place modification of context vars, exec_scope would need to be self.context.variables.
        script = "my_list.append(123)" # This operates on a copy if my_list is passed as part of execution_scope
                                      # If my_list was a global or a more complex setup, it might differ.
                                      # With current copy(), this won't modify original context.my_list
                                      # This test is to confirm that.

        # Let's test a script that defines a var but it's not captured by 'def'
        script_defines_var = "internal_var = 42"
        config_no_def = {"lang": "python", "script": script_defines_var}
        initial_vars_count = len(self.context.variables)

        self._run_code_step(config_no_def)

        self.assertIsNone(self.context.get_variable("internal_var")) # Not captured
        self.assertEqual(len(self.context.variables), initial_vars_count)


    def test_code_step_def_variable_not_in_script_scope(self):
        script = "a = 10"
        # 'def' refers to 'b', but script only defines 'a'
        config = {"lang": "python", "script": script, "def": "b"}

        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            self._run_code_step(config)
            self.assertIn("Warning: Variable 'b' specified in 'def' was not found", mock_stderr.getvalue())
        self.assertIsNone(self.context.get_variable("b")) # 'b' should not be in context or be None

    def test_code_step_syntax_error_in_script(self):
        script = "a = 10 + " # Syntax error
        config = {"lang": "python", "script": script, "def": "a"}
        with self.assertRaisesRegex(PILSyntaxError, "Syntax error in Python code step"):
            self._run_code_step(config)

    def test_code_step_name_error_in_script_from_pil_context(self):
        # 'z' is not defined in PIL context nor in script before use
        script = "a = z + 10"
        config = {"lang": "python", "script": script, "def": "a"}
        with self.assertRaisesRegex(PILSemanticError, "NameError in Python code step"):
            self._run_code_step(config)

    def test_code_step_unsupported_language(self):
        config = {"lang": "javascript", "script": "var a = 10;", "def": "a"}
        with self.assertRaisesRegex(PILSemanticError, "Unsupported language 'javascript'"):
            self._run_code_step(config)

    def test_code_step_missing_script(self):
        config = {"lang": "python", "def": "a"} # Missing 'script'
        with self.assertRaisesRegex(PILSemanticError, "must have a 'script' field"):
            self._run_code_step(config)

    def test_code_step_script_not_string(self):
        config = {"lang": "python", "script": 123, "def": "a"}
        with self.assertRaisesRegex(PILSemanticError, "must have a 'script' field as a non-empty string"):
            self._run_code_step(config)

    def test_code_step_invalid_def_type(self):
        config = {"lang": "python", "script": "a=1", "def": 123} # def is not a string
        with self.assertRaisesRegex(PILSemanticError, "Code step 'def' field, if provided, must be a string"):
            self._run_code_step(config)

    def test_code_step_script_modifies_copied_scope_not_original_context_directly(self):
        # This test confirms that the script operates on a copy of the context variables,
        # and direct modifications to that scope (for mutable types) don't automatically
        # reflect in the original context, unless explicitly captured by 'def'.
        original_list = [1, 2]
        self.context.set_variable("test_list", original_list)

        # This script will modify 'test_list' within its own execution_scope
        script = "test_list.append(3); new_var = test_list"
        config = {"lang": "python", "script": script, "def": "new_var"}

        self._run_code_step(config)

        # The original list in the context should be unchanged
        self.assertEqual(self.context.get_variable("test_list"), [1, 2])
        # new_var in context should be the modified list from script's scope
        self.assertEqual(self.context.get_variable("new_var"), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
