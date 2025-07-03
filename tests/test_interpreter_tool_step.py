import unittest
from typing import Dict, Any, Callable, List # Added List
import io # For capturing stdout/stderr
import sys # For capturing stdout/stderr


from pil_engine.interpreter import Interpreter, PilParser
from pil_engine.core.components import PilProgram, ToolStep
from pil_engine.core.context import Context
from pil_engine.exceptions import ToolExecutionError, ToolNotFoundException # Import the exceptions

# --- Sample Tools for Testing ---
def add_tool(a: Any, b: Any) -> float:
    """Adds two numbers after converting them to float."""
    try:
        return float(a) + float(b)
    except ValueError:
        raise TypeError("Both 'a' and 'b' must be convertible to numbers for add_tool.")

def greet_tool(name: str, greeting: str = "Hello") -> str:
    """Greets a person with an optional custom greeting."""
    if not isinstance(name, str):
        raise TypeError("'name' must be a string for greet_tool.")
    if not isinstance(greeting, str):
        raise TypeError("'greeting' must be a string for greet_tool.")
    return f"{greeting}, {name}!"

def tool_that_raises_exception():
    """A tool that always raises a custom exception."""
    raise ValueError("This tool intentionally failed.")

# --- Test Program Helper ---
def create_tool_test_program(
    tool_name: str,
    tool_args: Dict[str, Any],
    initial_vars: dict = None,
    def_var: str = "tool_output"
) -> PilProgram:

    program_dict = {
        "config": {"model": "test-model"}, # Base config
        "workflow": {
            "steps": [
                {
                    "tool": {
                        "name": tool_name,
                        "args": tool_args,
                        "def": def_var
                    }
                }
            ]
        }
    }
    if initial_vars:
         program_dict["input"] = {"vars": {k: type(v).__name__ for k,v in initial_vars.items()}}

    parser = PilParser()
    return parser.parse_dict(program_dict)


class TestInterpreterToolStep(unittest.TestCase):

    def setUp(self):
        self.interpreter = Interpreter(PilParser().parse_dict({"workflow": {"steps": []}})) # Basic interpreter
        # Register sample tools
        self.interpreter.register_tool("add_numbers", add_tool)
        self.interpreter.register_tool("greet_user", greet_tool)
        self.interpreter.register_tool("failing_tool", tool_that_raises_exception)

    def test_simple_tool_call_add(self):
        program = create_tool_test_program("add_numbers", {"a": 5, "b": "3.0"})
        # Re-initialize interpreter with this specific program for context, or set program
        self.interpreter.pil_program = program
        self.interpreter.context = Context() # Reset context for this run

        self.interpreter.run()

        output = self.interpreter.context.get_variable("tool_output")
        self.assertEqual(output, 8.0)

    def test_tool_call_with_templating(self):
        program = create_tool_test_program(
            "greet_user",
            {"name": "{{user_name}}", "greeting": "Hi"},
            initial_vars={"user_name": "Alice"}
        )
        self.interpreter.pil_program = program
        self.interpreter.context = Context(initial_vars={"user_name": "Alice"})

        self.interpreter.run()
        output = self.interpreter.context.get_variable("tool_output")
        self.assertEqual(output, "Hi, Alice!")

    def test_tool_with_default_argument(self):
        program = create_tool_test_program("greet_user", {"name": "Bob"}) # Uses default greeting
        self.interpreter.pil_program = program
        self.interpreter.context = Context()

        self.interpreter.run()
        output = self.interpreter.context.get_variable("tool_output")
        self.assertEqual(output, "Hello, Bob!")

    def test_unregistered_tool_call(self):
        program = create_tool_test_program("non_existent_tool", {"arg": "val"})
        self.interpreter.pil_program = program
        self.interpreter.context = Context()

        with self.assertRaisesRegex(ToolNotFoundException, "Tool 'non_existent_tool' not found in registry"):
            self.interpreter.run()

    def test_tool_raises_type_error_for_bad_args(self):
        # add_tool expects args convertible to float
        program = create_tool_test_program("add_numbers", {"a": "five", "b": 3})
        self.interpreter.pil_program = program
        self.interpreter.context = Context()

        # The interpreter's _execute_tool_step catches and wraps exceptions in ToolExecutionError
        with self.assertRaisesRegex(ToolExecutionError, "Type error while calling tool 'add_numbers' with args {'a': 'five', 'b': 3}: Both 'a' and 'b' must be convertible to numbers for add_tool."):
            self.interpreter.run()

    def test_tool_raises_custom_exception(self):
        program = create_tool_test_program("failing_tool", {})
        self.interpreter.pil_program = program
        self.interpreter.context = Context()

        # The interpreter's _execute_tool_step wraps other exceptions in ToolExecutionError
        with self.assertRaisesRegex(ToolExecutionError, "Tool 'failing_tool' raised an exception: This tool intentionally failed."):
            self.interpreter.run()

    def test_tool_output_is_correctly_defined(self):
        program = create_tool_test_program("add_numbers", {"a": 10, "b": 20}, def_var="sum_result")
        self.interpreter.pil_program = program
        self.interpreter.context = Context()
        self.interpreter.run()
        self.assertTrue(self.interpreter.context.has_variable("sum_result"))
        self.assertEqual(self.interpreter.context.get_variable("sum_result"), 30.0)

def complex_arg_tool(name: str, numbers: List[int], config: Dict[str, Any], active: Any): # Changed active hint to Any
    """A tool that accepts complex (list, dict, bool) arguments, robust to string booleans."""
    is_active_bool = False
    if isinstance(active, bool):
        is_active_bool = active
    elif isinstance(active, str):
        is_active_bool = active.lower() == 'true' # Handle "true"/"false" strings

    if not is_active_bool:
        return f"{name} is inactive."
    return f"{name}: Processed {len(numbers)} numbers. First config key: {list(config.keys())[0] if config else 'N/A'}"

class TestInterpreterToolRegistration(unittest.TestCase):
    def setUp(self):
        # Create a basic PilProgram for the interpreter, not strictly needed for registration tests but good practice
        self.pil_program = PilParser().parse_dict({"config": {}, "workflow": {"steps": []}})
        self.interpreter = Interpreter(self.pil_program)

    def test_register_valid_tool(self):
        self.interpreter.register_tool("my_valid_tool", lambda x: x * 2)
        self.assertIn("my_valid_tool", self.interpreter.tool_registry)
        self.assertEqual(self.interpreter.tool_registry["my_valid_tool"](5), 10)

    def test_register_non_callable(self):
        with self.assertRaisesRegex(TypeError, "Tool 'bad_tool' must be a callable Python function or method."):
            self.interpreter.register_tool("bad_tool", 123)

    def test_register_empty_name(self):
        with self.assertRaisesRegex(ValueError, "Tool name must be a non-empty string."):
            self.interpreter.register_tool("", lambda: "test")

    def test_register_non_string_name(self):
        with self.assertRaisesRegex(ValueError, "Tool name must be a non-empty string."):
            self.interpreter.register_tool(123, lambda: "test")

    def test_reregister_tool_works_and_warns(self):
        original_tool = lambda: "original"
        new_tool = lambda: "new"

        self.interpreter.register_tool("re_tool", original_tool)
        self.assertEqual(self.interpreter.tool_registry["re_tool"](), "original")

        # Capture stdout to check for warning
        captured_output = io.StringIO()
        sys.stdout = captured_output

        self.interpreter.register_tool("re_tool", new_tool)

        sys.stdout = sys.__stdout__  # Reset redirect.

        self.assertIn("Warning: Tool 're_tool' is being re-registered", captured_output.getvalue())
        self.assertEqual(self.interpreter.tool_registry["re_tool"](), "new", "Tool should be updated to the new callable.")

class TestInterpreterToolStepWithComplexArgs(unittest.TestCase):
    def setUp(self):
        self.interpreter = Interpreter(PilParser().parse_dict({"workflow": {"steps": []}}))
        self.interpreter.register_tool("complex_tool", complex_arg_tool)

    def test_tool_with_literal_dict_list_bool_args(self):
        test_config = {"key1": "val1", "nested": {"n_key": 100}}
        test_numbers = [10, 20, 30]

        program = create_tool_test_program(
            "complex_tool",
            {
                "name": "MyComplexTask",
                "numbers": test_numbers, # Passed as actual list
                "config": test_config,   # Passed as actual dict
                "active": True           # Passed as actual bool
            },
            def_var="complex_output"
        )
        self.interpreter.pil_program = program
        self.interpreter.context = Context()
        self.interpreter.run()

        expected_output = "MyComplexTask: Processed 3 numbers. First config key: key1"
        self.assertEqual(self.interpreter.context.get_variable("complex_output"), expected_output)

    def test_tool_with_literal_args_and_templating(self):
        # Scenario: some args are literal, some are templated
        test_config_literal = {"source": "direct"}

        program = create_tool_test_program(
            "complex_tool",
            {
                "name": "{{task_name}}", # Templated
                "numbers": [1, 2],       # Literal list
                "config": test_config_literal, # Literal dict
                "active": "{{is_active}}" # Templated
            },
            initial_vars={"task_name": "MixedTask", "is_active": False},
            def_var="mixed_output"
        )
        self.interpreter.pil_program = program
        self.interpreter.context = Context(initial_vars={"task_name": "MixedTask", "is_active": False})
        self.interpreter.run()

        expected_output = "MixedTask is inactive."
        self.assertEqual(self.interpreter.context.get_variable("mixed_output"), expected_output)


if __name__ == '__main__':
    unittest.main()
