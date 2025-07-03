import unittest
import jsonschema # For creating SchemaError in tests

from pil_engine.interpreter import Interpreter, PilParser
from pil_engine.core.components import PilProgram
from pil_engine.exceptions import OutputValidationError, InvalidSchemaError, ConstraintViolationError


# Helper to create a PilProgram for testing program-level validations
def create_program_level_validation_test_program(
    output_schema_dict: dict = None,
    program_constraints_dict: dict = None,
    workflow_steps: list = None,
    initial_vars: dict = None,
    config_dict: dict = None # Allow passing full config
) -> PilProgram:

    program_dict = {
        "config": config_dict if config_dict else {} # Use provided config or default
    }
    if output_schema_dict:
        program_dict["outputSchema"] = {"schema": output_schema_dict}

    if program_constraints_dict:
        program_dict["constraints"] = program_constraints_dict

    if workflow_steps:
        program_dict["workflow"] = {"steps": workflow_steps}
    else:
        # Default workflow step that produces a string, and defines 'final_res'
        # which is the default var interpreter.run() returns if no program.output.from is set.
        program_dict["workflow"] = {"steps": [{"code": {"lang":"python", "script": "result = 'default_output'", "def": "final_res"}}]}

    # Ensure 'final_res' is defined if not other steps are present, as interpreter.run() expects it.
    if not workflow_steps and "output" not in program_dict:
        program_dict["output"] = {"from": "final_res"}


    if initial_vars:
         program_dict["input"] = {"vars": {k: {"type": type(v).__name__, "value": v} for k,v in initial_vars.items()}}


    parser = PilParser()
    return parser.parse_dict(program_dict)


class TestInterpreterProgramLevelValidations(unittest.TestCase):

    # --- OutputSchema Tests ---
    def test_schema_valid_string_output(self):
        schema = {"type": "string"}
        steps = [{"code": {"lang": "python", "script": "result = 'hello world'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(output_schema_dict=schema, workflow_steps=steps)
        interpreter = Interpreter(program)
        interpreter.run()

    def test_schema_invalid_string_output_wrong_type(self):
        schema = {"type": "string"}
        steps = [{"code": {"lang": "python", "script": "result = 123", "def": "final_res"}}]
        program = create_program_level_validation_test_program(output_schema_dict=schema, workflow_steps=steps)
        interpreter = Interpreter(program)
        with self.assertRaisesRegex(OutputValidationError, "123 is not of type 'string'"):
            interpreter.run()

    def test_schema_valid_object_output(self):
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
        # Corrected helper function name
        program = create_program_level_validation_test_program(output_schema_dict=schema, workflow_steps=steps)
        interpreter = Interpreter(program)
        interpreter.run()

    def test_invalid_object_output_missing_required(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"]
        }
        script = "result = {'name': 'Bob'}"
        steps = [{"code": {"lang": "python", "script": script, "def": "final_res"}}]
        # Corrected helper function name
        program = create_program_level_validation_test_program(output_schema_dict=schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        with self.assertRaisesRegex(OutputValidationError, "'age' is a required property"):
            interpreter.run()

    def test_invalid_object_output_wrong_property_type(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"]
        }
        script = "result = {'name': 'Charlie', 'age': 'thirty'}"
        steps = [{"code": {"lang": "python", "script": script, "def": "final_res"}}]
        # Corrected helper function name
        program = create_program_level_validation_test_program(output_schema_dict=schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        with self.assertRaisesRegex(OutputValidationError, "'thirty' is not of type 'integer'"):
            interpreter.run()

    def test_output_none_schema_allows_null(self):
        schema = {"type": ["string", "null"]}
        steps = [{"code": {"lang": "python", "script": "result = None", "def": "final_res"}}]
        # Corrected helper function name
        program = create_program_level_validation_test_program(output_schema_dict=schema, workflow_steps=steps)
        interpreter = Interpreter(program)
        interpreter.run()

    def test_output_none_schema_does_not_allow_null(self):
        schema = {"type": "string"}
        steps = [{"code": {"lang": "python", "script": "result = None", "def": "final_res"}}]
        # Corrected helper function name
        program = create_program_level_validation_test_program(output_schema_dict=schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        with self.assertRaisesRegex(OutputValidationError, "None is not of type 'string'"):
            interpreter.run()

    def test_no_output_schema_defined(self):
        steps = [{"code": {"lang": "python", "script": "result = 123", "def": "final_res"}}]
        # Corrected helper function name
        program = create_program_level_validation_test_program(output_schema_dict=None, workflow_steps=steps)
        interpreter = Interpreter(program)
        try:
            interpreter.run()
        except OutputValidationError:
            self.fail("OutputValidationError raised unexpectedly when no schema was defined.")

    def test_malformed_schema_itself(self):
        malformed_schema = {"type": "invalid_json_type"}
        steps = [{"code": {"lang": "python", "script": "result = 'some output'", "def": "final_res"}}]
        # Corrected helper function name
        program = create_program_level_validation_test_program(output_schema_dict=malformed_schema, workflow_steps=steps)
        interpreter = Interpreter(program)

        with self.assertRaises(InvalidSchemaError) as cm:
            interpreter.run()
        self.assertIn("Invalid OutputSchema provided", str(cm.exception))
        self.assertIsNotNone(cm.exception.schema_error)
        self.assertIsInstance(cm.exception.schema_error, jsonschema.SchemaError)

    # --- Top-level PilProgram.constraints Tests ---
    def test_program_constraints_valid_type(self):
        constraints = {"type": "string"}
        steps = [{"code": {"lang": "python", "script": "result = 'hello'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(program_constraints_dict=constraints, workflow_steps=steps)
        interpreter = Interpreter(program)
        final_val = interpreter.run()
        self.assertEqual(final_val, "hello")

    def test_program_constraints_invalid_type(self):
        constraints = {"type": "integer"}
        steps = [{"code": {"lang": "python", "script": "result = 'not an integer'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(program_constraints_dict=constraints, workflow_steps=steps)
        interpreter = Interpreter(program)
        # Imported ConstraintViolationError
        with self.assertRaisesRegex(ConstraintViolationError, "Type constraint violated.*Cannot convert value to 'integer'"):
            interpreter.run()

    def test_program_constraints_regex_pass(self):
        constraints = {"regex": r"^[a-z]+$"}
        steps = [{"code": {"lang": "python", "script": "result = 'abc'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(program_constraints_dict=constraints, workflow_steps=steps)
        interpreter = Interpreter(program)
        self.assertEqual(interpreter.run(), "abc")

    def test_program_constraints_regex_fail(self):
        constraints = {"regex": r"^\d+$"}
        steps = [{"code": {"lang": "python", "script": "result = 'abc'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(program_constraints_dict=constraints, workflow_steps=steps)
        interpreter = Interpreter(program)
        # Imported ConstraintViolationError
        with self.assertRaisesRegex(ConstraintViolationError, "Regex constraint violated"):
            interpreter.run()

    def test_program_constraints_choices_pass(self):
        constraints = {"choices": ["apple", "banana", "cherry"]}
        steps = [{"code": {"lang": "python", "script": "result = 'banana'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(program_constraints_dict=constraints, workflow_steps=steps)
        interpreter = Interpreter(program)
        self.assertEqual(interpreter.run(), "banana")

    def test_program_constraints_choices_fail(self):
        constraints = {"choices": ["apple", "banana", "cherry"]}
        steps = [{"code": {"lang": "python", "script": "result = 'grape'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(program_constraints_dict=constraints, workflow_steps=steps)
        interpreter = Interpreter(program)
        # Imported ConstraintViolationError
        with self.assertRaisesRegex(ConstraintViolationError, "not one of the allowed choices"):
            interpreter.run()

    # --- Interaction: OutputSchema AND Program.constraints ---
    def test_both_schema_and_program_constraints_pass(self):
        output_schema = {"type": "string", "minLength": 3}
        program_constraints = {"regex": r"^[a-z]+$"}
        steps = [{"code": {"lang": "python", "script": "result = 'hello'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(
            output_schema_dict=output_schema,
            program_constraints_dict=program_constraints,
            workflow_steps=steps
        )
        interpreter = Interpreter(program)
        self.assertEqual(interpreter.run(), "hello")

    def test_schema_pass_program_constraints_fail(self):
        output_schema = {"type": "string"}
        program_constraints = {"regex": r"^[a-z]+$"}
        steps = [{"code": {"lang": "python", "script": "result = '123'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(
            output_schema_dict=output_schema,
            program_constraints_dict=program_constraints,
            workflow_steps=steps
        )
        interpreter = Interpreter(program)
        # Imported ConstraintViolationError
        with self.assertRaisesRegex(ConstraintViolationError, "Regex constraint violated"):
            interpreter.run()

    def test_schema_fail_program_constraints_not_reached(self):
        output_schema = {"type": "integer"}
        program_constraints = {"regex": r"^[a-z]+$"}
        steps = [{"code": {"lang": "python", "script": "result = 'abc'", "def": "final_res"}}]
        program = create_program_level_validation_test_program(
            output_schema_dict=output_schema,
            program_constraints_dict=program_constraints,
            workflow_steps=steps
        )
        interpreter = Interpreter(program)
        with self.assertRaisesRegex(OutputValidationError, "'abc' is not of type 'integer'"):
            interpreter.run()

    def test_interaction_schema_pass_program_constraint_type_conversion(self):
        json_list_string = "[1, 2, 3]"
        steps = [{"code": {"lang": "python", "script": f"result = '{json_list_string}'", "def": "final_res"}}]

        output_schema = {"type": "string"}
        program_constraints = {"type": "list"}

        program = create_program_level_validation_test_program(
            output_schema_dict=output_schema,
            program_constraints_dict=program_constraints,
            workflow_steps=steps
        )
        interpreter = Interpreter(program)
        final_output = interpreter.run()

        # The string '[1, 2, 3]' passes string schema.
        # Then apply_constraints converts it to actual list [1, 2, 3]
        self.assertEqual(final_output, [1, 2, 3])
        self.assertIsInstance(final_output, list)


if __name__ == '__main__':
    unittest.main()
