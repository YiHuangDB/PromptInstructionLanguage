import unittest
from unittest.mock import patch, MagicMock
import os

# Assuming openai is a dependency. In a real scenario, ensure it's installed.
import openai

from pil_engine.interpreter import Interpreter, PilParser
from pil_engine.core.components import PilProgram, PromptStep, Config, Persona, Input
from pil_engine.core.context import Context


# Helper to create a PilProgram with a single PromptStep
def create_prompt_test_program(
    prompt_text: str,
    model_name: str = "gpt-test-model",
    api_key: str = None,
    parameters: dict = None,
    persona_data: dict = None,
    examples_data: list = None,
    initial_vars: dict = None
) -> PilProgram:

    program_dict = {
        "config": {
            "model": model_name,
        },
        "workflow": {
            "steps": [
                {
                    "prompt": {
                        "text": prompt_text,
                    }
                }
            ]
        }
    }
    if api_key:
        program_dict["config"]["api_key"] = api_key
    if parameters:
        program_dict["config"]["parameters"] = parameters
    if persona_data:
        program_dict["persona"] = persona_data
    if examples_data:
        program_dict["workflow"]["steps"][0]["prompt"]["examples"] = examples_data
    if initial_vars:
         program_dict["input"] = {"vars": {k: type(v).__name__ for k,v in initial_vars.items()}}


    parser = PilParser()
    return parser.parse_dict(program_dict)


class TestInterpreterPromptStep(unittest.TestCase):

    def setUp(self):
        # Ensure a clean environment for API key tests if needed, though mocks are preferred
        self.original_openai_api_key = os.environ.get("OPENAI_API_KEY")
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

    def tearDown(self):
        if self.original_openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.original_openai_api_key
        elif "OPENAI_API_KEY" in os.environ: # If test set it and it wasn't there before
            del os.environ["OPENAI_API_KEY"]

    @patch('openai.OpenAI')
    def test_successful_llm_call(self, MockOpenAI):
        # Mock the OpenAI client and its methods
        mock_client_instance = MockOpenAI.return_value
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Test LLM response"))]
        mock_completion.id = "cmpl-test123"
        mock_completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        mock_client_instance.chat.completions.create.return_value = mock_completion

        pil_program = create_prompt_test_program(
            prompt_text="Hello {{name}}",
            api_key="test_key_from_config", # Test config key usage
            parameters={"temperature": 0.5}
        )
        interpreter = Interpreter(pil_program, initial_vars={"name": "World"}, debug_mode=True)

        # The first step in the workflow is the PromptStep
        prompt_step_obj = pil_program.workflow.steps[0]

        response = interpreter._execute_prompt_step(prompt_step_obj)

        self.assertEqual(response, "Test LLM response")
        mock_client_instance.chat.completions.create.assert_called_once()
        call_args = mock_client_instance.chat.completions.create.call_args

        self.assertEqual(call_args.kwargs['model'], "gpt-test-model")
        self.assertIn({"role": "user", "content": "Hello World"}, call_args.kwargs['messages'])
        self.assertEqual(call_args.kwargs['temperature'], 0.5)

        # Check if client was initialized with the config key
        MockOpenAI.assert_called_with(api_key="test_key_from_config")


    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_key_from_env"})
    @patch('openai.OpenAI')
    def test_llm_call_with_env_api_key(self, MockOpenAI):
        mock_client_instance = MockOpenAI.return_value
        mock_client_instance.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="Env key response"))])

        # Program does NOT provide api_key in config, so it should use env var
        pil_program = create_prompt_test_program(prompt_text="Test prompt")

        # Interpreter initialization will trigger _initialize_llm_client
        interpreter = Interpreter(pil_program)
        MockOpenAI.assert_called_with(api_key="test_key_from_env") # Check client init

        prompt_step_obj = pil_program.workflow.steps[0]
        response = interpreter._execute_prompt_step(prompt_step_obj)
        self.assertEqual(response, "Env key response")


    def test_llm_call_no_api_key_raises_error(self):
        # No API key in config, and we ensure no OPENAI_API_KEY in env (setUp does this)
        pil_program = create_prompt_test_program(prompt_text="Test prompt", api_key=None)

        # Initialization should set llm_client to None
        interpreter = Interpreter(pil_program)
        self.assertIsNone(interpreter.llm_client)

        prompt_step_obj = pil_program.workflow.steps[0]
        with self.assertRaisesRegex(ConnectionRefusedError, "LLM client is not initialized"):
            interpreter._execute_prompt_step(prompt_step_obj)

    @patch('openai.OpenAI')
    def test_llm_call_with_persona_and_examples(self, MockOpenAI):
        mock_client_instance = MockOpenAI.return_value
        mock_client_instance.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="Response"))])

        pil_program = create_prompt_test_program(
            prompt_text="User question: {{query}}",
            api_key="fake_key",
            persona_data={"role": "Helpful Assistant", "style": "concise"},
            examples_data=[
                {"input": "What is 1+1?", "output": "2"},
                {"input": "What is the capital of France?", "output": "Paris"}
            ]
        )
        interpreter = Interpreter(pil_program, initial_vars={"query": "What is PIL?"})

        # Manually set __persona__ in context as run() is not called directly in this test
        if pil_program.persona:
            interpreter.context.set_variable("__persona__", pil_program.persona)

        prompt_step_obj = pil_program.workflow.steps[0]
        interpreter._execute_prompt_step(prompt_step_obj)

        mock_client_instance.chat.completions.create.assert_called_once()
        call_args = mock_client_instance.chat.completions.create.call_args
        messages = call_args.kwargs['messages']

        self.assertEqual(messages[0], {"role": "system", "content": "Role: Helpful Assistant, Style: concise"}) # Corrected expected system message
        self.assertEqual(messages[1], {"role": "user", "content": "What is 1+1?"})
        self.assertEqual(messages[2], {"role": "assistant", "content": "2"})
        self.assertEqual(messages[3], {"role": "user", "content": "What is the capital of France?"})
        self.assertEqual(messages[4], {"role": "assistant", "content": "Paris"})
        self.assertEqual(messages[5], {"role": "user", "content": "User question: What is PIL?"})

    # Test various OpenAI API errors
    @patch('openai.OpenAI')
    def test_llm_api_connection_error(self, MockOpenAI):
        mock_client_instance = MockOpenAI.return_value
        mock_client_instance.chat.completions.create.side_effect = openai.APIConnectionError(request=MagicMock())

        pil_program = create_prompt_test_program(prompt_text="test", api_key="fake")
        interpreter = Interpreter(pil_program)
        prompt_step_obj = pil_program.workflow.steps[0]

        with self.assertRaisesRegex(ConnectionError, "OpenAI API request failed to connect"):
            interpreter._execute_prompt_step(prompt_step_obj)

    @patch('openai.OpenAI')
    def test_llm_authentication_error(self, MockOpenAI):
        mock_client_instance = MockOpenAI.return_value
        # Simulate AuthenticationError (ensure you have a response object for the error if needed by the lib)
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Incorrect API key provided"}} # Example error structure

        mock_client_instance.chat.completions.create.side_effect = openai.AuthenticationError(
            message="Incorrect API key.", response=mock_response, body=None
        )

        pil_program = create_prompt_test_program(prompt_text="test", api_key="fake")
        interpreter = Interpreter(pil_program)
        prompt_step_obj = pil_program.workflow.steps[0]

        with self.assertRaisesRegex(PermissionError, "OpenAI API authentication failed"):
            interpreter._execute_prompt_step(prompt_step_obj)

    @patch('openai.OpenAI')
    def test_llm_rate_limit_error(self, MockOpenAI):
        mock_client_instance = MockOpenAI.return_value
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client_instance.chat.completions.create.side_effect = openai.RateLimitError(
            message="Rate limit exceeded.", response=mock_response, body=None
        )

        pil_program = create_prompt_test_program(prompt_text="test", api_key="fake")
        interpreter = Interpreter(pil_program)
        prompt_step_obj = pil_program.workflow.steps[0]

        with self.assertRaisesRegex(PermissionError, "OpenAI API request exceeded rate limit"): # Changed from ConnectionAbortedError
            interpreter._execute_prompt_step(prompt_step_obj)

    @patch('openai.OpenAI')
    def test_llm_generic_api_status_error(self, MockOpenAI):
        mock_client_instance = MockOpenAI.return_value
        mock_response = MagicMock(status_code=500, text="Internal Server Error")
        # To make it look more like a httpx.Response for openai >1.0
        mock_response.json = lambda: {"error": {"message": "Server error"}}
        mock_response.headers = {}

        mock_client_instance.chat.completions.create.side_effect = openai.APIStatusError(
            message="API error.", response=mock_response, body=None
        )

        pil_program = create_prompt_test_program(prompt_text="test", api_key="fake")
        interpreter = Interpreter(pil_program)
        prompt_step_obj = pil_program.workflow.steps[0]

        with self.assertRaisesRegex(RuntimeError, "OpenAI API returned an error status 500"):
            interpreter._execute_prompt_step(prompt_step_obj)


if __name__ == '__main__':
    unittest.main()
