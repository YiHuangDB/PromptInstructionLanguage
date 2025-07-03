import unittest
from unittest.mock import patch, MagicMock
import os # For custom validator module path if needed

from pil_engine.validator import apply_constraints
from pil_engine.core.components import Constraints
from pil_engine.core.context import Context
from pil_engine.exceptions import ConstraintViolationError, PilEngineError

# --- Sample Custom Validator Functions (would typically be in a separate file) ---
# For testing purposes, we can define them here or mock their import.
# Let's assume we'll mock the import and the function's behavior.

class TestConstraintsValidator(unittest.TestCase):
    def setUp(self):
        self.context = Context() # Dummy context for most tests

    # --- Type Constraints ---
    def test_type_string_valid(self):
        constraints = Constraints(type="string")
        self.assertEqual(apply_constraints("hello", constraints, self.context), "hello")

    def test_type_string_invalid(self):
        constraints = Constraints(type="string")
        with self.assertRaisesRegex(ConstraintViolationError, "Expected type 'string', got int"):
            apply_constraints(123, constraints, self.context)

    def test_type_integer_valid(self):
        constraints = Constraints(type="integer")
        self.assertEqual(apply_constraints("123", constraints, self.context), 123)
        self.assertEqual(apply_constraints("-10", constraints, self.context), -10)

    def test_type_integer_already_int(self):
        constraints = Constraints(type="integer")
        self.assertEqual(apply_constraints(456, constraints, self.context), 456)

    def test_type_integer_invalid_string(self):
        constraints = Constraints(type="integer")
        with self.assertRaisesRegex(ConstraintViolationError, "Cannot convert value to 'integer'"):
            apply_constraints("abc", constraints, self.context)

    def test_type_integer_invalid_float_string(self):
        constraints = Constraints(type="integer")
        with self.assertRaisesRegex(ConstraintViolationError, "Cannot convert value to 'integer'"):
            apply_constraints("1.23", constraints, self.context)

    def test_type_number_valid(self): # number means float
        constraints = Constraints(type="number")
        self.assertAlmostEqual(apply_constraints("1.23", constraints, self.context), 1.23)
        self.assertAlmostEqual(apply_constraints("123", constraints, self.context), 123.0) # int string to float
        self.assertAlmostEqual(apply_constraints("-0.5", constraints, self.context), -0.5)

    def test_type_number_already_float_or_int(self):
        constraints = Constraints(type="number")
        self.assertAlmostEqual(apply_constraints(1.23, constraints, self.context), 1.23)
        self.assertAlmostEqual(apply_constraints(123, constraints, self.context), 123.0)


    def test_type_number_invalid_string(self):
        constraints = Constraints(type="number")
        with self.assertRaisesRegex(ConstraintViolationError, "Cannot convert value to 'number'"):
            apply_constraints("abc", constraints, self.context)

    def test_type_boolean_valid_strings(self):
        constraints = Constraints(type="boolean")
        self.assertTrue(apply_constraints("true", constraints, self.context))
        self.assertTrue(apply_constraints("True", constraints, self.context))
        self.assertFalse(apply_constraints("false", constraints, self.context))
        self.assertFalse(apply_constraints("False", constraints, self.context))

    def test_type_boolean_already_bool(self):
        constraints = Constraints(type="boolean")
        self.assertTrue(apply_constraints(True, constraints, self.context))
        self.assertFalse(apply_constraints(False, constraints, self.context))

    def test_type_boolean_invalid_string(self):
        constraints = Constraints(type="boolean")
        with self.assertRaisesRegex(ConstraintViolationError, "Cannot convert string value to 'boolean'"):
            apply_constraints("yes", constraints, self.context)
        with self.assertRaisesRegex(ConstraintViolationError, "Cannot convert string value to 'boolean'"):
            apply_constraints("1", constraints, self.context)

    def test_type_boolean_invalid_type(self):
        constraints = Constraints(type="boolean")
        with self.assertRaisesRegex(ConstraintViolationError, "Expected type 'boolean', got int"):
            apply_constraints(1, constraints, self.context)


    def test_type_list_valid_json_string(self):
        constraints = Constraints(type="list")
        self.assertEqual(apply_constraints("[1, \"a\"]", constraints, self.context), [1, "a"])
        self.assertEqual(apply_constraints("[]", constraints, self.context), [])

    def test_type_list_already_list(self):
        constraints = Constraints(type="list")
        self.assertEqual(apply_constraints([1, "a"], constraints, self.context), [1, "a"])

    def test_type_list_invalid_json_string(self):
        constraints = Constraints(type="list")
        with self.assertRaisesRegex(ConstraintViolationError, "Value is not a valid JSON string for type 'list/array'"):
            apply_constraints("[1, 'a'", constraints, self.context) # Malformed JSON

    def test_type_list_json_parses_to_non_list(self):
        constraints = Constraints(type="list")
        with self.assertRaisesRegex(ConstraintViolationError, "Value parsed from JSON string is not a list"):
            apply_constraints("{\"a\": 1}", constraints, self.context) # Valid JSON, but object not list

    def test_type_list_invalid_type(self):
        constraints = Constraints(type="list")
        with self.assertRaisesRegex(ConstraintViolationError, "Expected type 'list/array' or JSON string"):
            apply_constraints(123, constraints, self.context)


    def test_type_object_valid_json_string(self):
        constraints = Constraints(type="object")
        self.assertEqual(apply_constraints("{\"a\": 1, \"b\": \"x\"}", constraints, self.context), {"a": 1, "b": "x"})

    def test_type_object_already_dict(self):
        constraints = Constraints(type="object")
        self.assertEqual(apply_constraints({"a":1}, constraints, self.context), {"a":1})

    def test_type_object_invalid_json_string(self):
        constraints = Constraints(type="object")
        with self.assertRaisesRegex(ConstraintViolationError, "Value is not a valid JSON string for type 'object'"):
            apply_constraints("{\"a\": 1", constraints, self.context) # Malformed

    def test_type_object_json_parses_to_non_object(self):
        constraints = Constraints(type="object")
        with self.assertRaisesRegex(ConstraintViolationError, "Value parsed from JSON string is not an object/dict"):
            apply_constraints("[1,2,3]", constraints, self.context) # Valid JSON, but list not object

    def test_type_object_invalid_type(self):
        constraints = Constraints(type="object")
        with self.assertRaisesRegex(ConstraintViolationError, "Expected type 'object' or JSON string"):
            apply_constraints(123, constraints, self.context)


    def test_unknown_type_constraint(self):
        constraints = Constraints(type="fancytype")
        with self.assertRaisesRegex(PilEngineError, "Unknown constraint type 'fancytype'"):
            apply_constraints("some value", constraints, self.context)

    # --- Regex Constraint ---
    def test_regex_valid(self):
        constraints = Constraints(regex=r"^\d{3}-\d{2}-\d{4}$") # SSN-like
        self.assertEqual(apply_constraints("123-45-6789", constraints, self.context), "123-45-6789")

    def test_regex_invalid(self):
        constraints = Constraints(regex=r"^\d{3}$")
        with self.assertRaisesRegex(ConstraintViolationError, "Regex constraint violated"):
            apply_constraints("1234", constraints, self.context)

    def test_regex_on_non_string_after_conversion(self):
        # If type conversion makes it non-string, regex should ideally not apply or be defined carefully.
        # Current logic applies regex to str(value) if original was not string.
        constraints = Constraints(type="integer", regex=r"^\d{3}$")
        # Value "123" becomes int 123. Then str(123) = "123", which matches.
        self.assertEqual(apply_constraints("123", constraints, self.context), 123)

        constraints_fail = Constraints(type="integer", regex=r"^[a-z]+$")
        # Value "123" becomes int 123. str(123) = "123". Does not match r"^[a-z]+$".
        with self.assertRaisesRegex(ConstraintViolationError, "Regex constraint violated"):
            apply_constraints("123", constraints_fail, self.context)


    # --- Choices Constraint ---
    def test_choices_valid_string(self):
        constraints = Constraints(choices=["red", "green", "blue"])
        self.assertEqual(apply_constraints("green", constraints, self.context), "green")

    def test_choices_invalid_string(self):
        constraints = Constraints(choices=["red", "green", "blue"])
        with self.assertRaisesRegex(ConstraintViolationError, "not one of the allowed choices"):
            apply_constraints("yellow", constraints, self.context)

    def test_choices_valid_typed_value(self):
        constraints = Constraints(type="integer", choices=[1, 2, 3])
        self.assertEqual(apply_constraints("2", constraints, self.context), 2) # "2" -> 2, then 2 in [1,2,3]

    def test_choices_invalid_typed_value(self):
        constraints = Constraints(type="integer", choices=[1, 2, 3])
        with self.assertRaisesRegex(ConstraintViolationError, "not one of the allowed choices"):
            apply_constraints("4", constraints, self.context) # "4" -> 4, then 4 not in [1,2,3]

    # --- Custom Validator ---
    @patch('pil_engine.validator._dynamic_import')
    def test_custom_validator_valid(self, mock_dynamic_import):
        mock_validator = MagicMock(return_value=True)
        mock_dynamic_import.return_value = mock_validator

        constraints = Constraints(custom_validator="my_module:my_validator_func")
        value = "test_value"
        returned_value = apply_constraints(value, constraints, self.context, step_name="TestStep")

        self.assertEqual(returned_value, value) # Custom validator doesn't change value by default
        mock_dynamic_import.assert_called_once_with("my_module", "my_validator_func")
        mock_validator.assert_called_once_with(value, self.context)

    @patch('pil_engine.validator._dynamic_import')
    def test_custom_validator_returns_false(self, mock_dynamic_import):
        mock_validator = MagicMock(return_value=False)
        mock_dynamic_import.return_value = mock_validator

        constraints = Constraints(custom_validator="my_module:my_validator_func")
        with self.assertRaisesRegex(ConstraintViolationError, "Custom validator 'my_module:my_validator_func' failed"):
            apply_constraints("test_value", constraints, self.context)

    @patch('pil_engine.validator._dynamic_import')
    def test_custom_validator_raises_exception(self, mock_dynamic_import):
        mock_validator = MagicMock(side_effect=ValueError("Validator specific error"))
        mock_dynamic_import.return_value = mock_validator

        constraints = Constraints(custom_validator="my_module:my_validator_func")
        with self.assertRaisesRegex(ConstraintViolationError, "raised an exception: Validator specific error"):
            apply_constraints("test_value", constraints, self.context)

    def test_custom_validator_invalid_format(self):
        constraints = Constraints(custom_validator="my_module_no_colon_func")
        with self.assertRaisesRegex(PilEngineError, "Invalid custom_validator format"):
            apply_constraints("test_value", constraints, self.context)

    @patch('pil_engine.validator._dynamic_import')
    def test_custom_validator_module_not_found(self, mock_dynamic_import):
        mock_dynamic_import.side_effect = PilEngineError("Custom validator module 'nonexistent_module' not found.") # Simulate _dynamic_import's behavior
        constraints = Constraints(custom_validator="nonexistent_module:func")
        with self.assertRaisesRegex(PilEngineError, "Custom validator module 'nonexistent_module' not found"):
            apply_constraints("test_value", constraints, self.context)

    @patch('pil_engine.validator._dynamic_import')
    def test_custom_validator_function_not_found(self, mock_dynamic_import):
        mock_dynamic_import.side_effect = PilEngineError("Custom validator function 'non_existent_func' not found in module 'existing_module'.") # Simulate _dynamic_import's behavior
        constraints = Constraints(custom_validator="existing_module:non_existent_func")
        with self.assertRaisesRegex(PilEngineError, "Custom validator function 'non_existent_func' not found"):
            apply_constraints("test_value", constraints, self.context)

    # --- Combined Constraints ---
    def test_combined_type_and_regex_valid(self):
        constraints = Constraints(type="string", regex=r"^\d{3}$")
        self.assertEqual(apply_constraints("123", constraints, self.context), "123")

    def test_combined_type_and_regex_invalid_type(self):
        constraints = Constraints(type="string", regex=r"^\d{3}$")
        with self.assertRaisesRegex(ConstraintViolationError, "Expected type 'string', got int"):
            apply_constraints(123, constraints, self.context) # Fails type check first

    def test_combined_type_and_regex_invalid_regex(self):
        constraints = Constraints(type="string", regex=r"^\d{3}$")
        with self.assertRaisesRegex(ConstraintViolationError, "Regex constraint violated"):
            apply_constraints("1234", constraints, self.context) # Passes type, fails regex


if __name__ == '__main__':
    unittest.main()
