import unittest
import jsonschema # For creating SchemaError in tests

from pil_engine.interpreter import Interpreter, PilParser
from pil_engine.core.components import PilProgram
from pil_engine.exceptions import OutputValidationError, InvalidSchemaError


# Helper to create a PilProgram for testing output schema
def create_schema_test_program(
    output_schema: dict = None,
    workflow_steps: list = None, # Steps for the workflow
    initial_vars: dict = None
) -> PilProgram:

    program_dict = {
        "config": {} # Basic config, no model by default
    }
    if output_schema:
        program_dict["outputSchema"] = {"schema": output_schema}

    if workflow_steps:
        program_dict["workflow"] = {"steps": workflow_steps}
    else: # Default workflow that produces a known output if no steps provided
        program_dict["workflow"] = {"steps": [{"code": {"lang":"python", "script": "result = 'default_output_for_schema_test'", "def": "final_output_var"}}]}


    if initial_vars:
         program_dict["input"] = {"vars": {k: type(v).__name__ for k,v in initial_vars.items()}}

    parser = PilParser()
    return parser.parse_dict(program_dict)


class TestInterpreterOutputSchema(unittest.TestCase):

    def test_valid_string_output(self):
        schema = {"type": "string"}
        # Last step produces a string. For PromptStep, this is simulated.
        # We need to ensure the (mocked) LLM produces a string.
        # For simplicity, let's use a CodeStep to produce a known type.
        steps = [{"code": {"lang": "python", "script": "result = 'hello world'", "def": "final_res"}}]
        program = create_schema_test_program(output_schema=schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        # No exception should be raised
        interpreter.run()

    def test_invalid_string_output_wrong_type(self):
        schema = {"type": "string"}
        steps = [{"code": {"lang": "python", "script": "result = 123", "def": "final_res"}}] # Produces number
        program = create_schema_test_program(output_schema=schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        with self.assertRaisesRegex(OutputValidationError, "123 is not of type 'string'"):
            interpreter.run()

    def test_valid_object_output(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"}
            },
            "required": ["name", "age"]
        }
        script = "result = {'name': 'Alice', 'age': 30}"
        steps = [{"code": {"lang": "python", "script": script, "def": "final_res"}}]
        program = create_schema_test_program(output_schema=schema, workflow_steps=steps)
        interpreter = Interpreter(program)
        interpreter.run() # Should pass

    def test_invalid_object_output_missing_required(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"]
        }
        script = "result = {'name': 'Bob'}" # Missing 'age'
        steps = [{"code": {"lang": "python", "script": script, "def": "final_res"}}]
        program = create_schema_test_program(output_schema=schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        with self.assertRaisesRegex(OutputValidationError, "'age' is a required property"):
            interpreter.run()

    def test_invalid_object_output_wrong_property_type(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"]
        }
        script = "result = {'name': 'Charlie', 'age': 'thirty'}" # Age is string, not int
        steps = [{"code": {"lang": "python", "script": script, "def": "final_res"}}]
        program = create_schema_test_program(output_schema=schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        with self.assertRaisesRegex(OutputValidationError, "'thirty' is not of type 'integer'"):
            interpreter.run()

    def test_output_none_schema_allows_null(self):
        schema = {"type": ["string", "null"]}
        steps = [{"code": {"lang": "python", "script": "result = None", "def": "final_res"}}]
        program = create_schema_test_program(output_schema=schema, workflow_steps=steps)
        interpreter = Interpreter(program)
        interpreter.run() # Should pass as None is allowed by "null" type

    def test_output_none_schema_does_not_allow_null(self):
        schema = {"type": "string"}
        steps = [{"code": {"lang": "python", "script": "result = None", "def": "final_res"}}]
        program = create_schema_test_program(output_schema=schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        with self.assertRaisesRegex(OutputValidationError, "None is not of type 'string'"):
            interpreter.run()

    def test_no_output_schema_defined(self):
        # Workflow produces an int, but no schema to validate against
        steps = [{"code": {"lang": "python", "script": "result = 123", "def": "final_res"}}]
        program = create_schema_test_program(output_schema=None, workflow_steps=steps)
        interpreter = Interpreter(program)
        try:
            interpreter.run() # Should run without validation error
        except OutputValidationError:
            self.fail("OutputValidationError raised unexpectedly when no schema was defined.")

    def test_malformed_schema_itself(self):
        # Example of a schema that is structurally invalid (e.g. type is not a valid type name)
        malformed_schema = {"type": "invalid_json_type"}
        steps = [{"code": {"lang": "python", "script": "result = 'some output'", "def": "final_res"}}]
        program = create_schema_test_program(output_schema=malformed_schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        # jsonschema.validate might raise jsonschema.SchemaError if the schema itself is bad
        with self.assertRaises(InvalidSchemaError) as cm:
            interpreter.run()
        self.assertIn("Invalid OutputSchema provided", str(cm.exception))
        # Check if the original SchemaError is available (if needed for more detailed assertions)
        self.assertIsNotNone(cm.exception.schema_error)
        self.assertIsInstance(cm.exception.schema_error, jsonschema.SchemaError)


if __name__ == '__main__':
    unittest.main()
