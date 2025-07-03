import unittest
from typing import Dict, Any, Callable

from pil_engine.interpreter import Interpreter, PilParser
from pil_engine.core.components import PilProgram, ToolStep
from pil_engine.core.context import Context
from pil_engine.exceptions import ToolExecutionError # Import the exception

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

        with self.assertRaisesRegex(KeyError, "Tool 'non_existent_tool' not found in registry"):
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


if __name__ == '__main__':
    unittest.main()
