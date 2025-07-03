import unittest
from pil_interpreter.context import ExecutionContext

class TestExecutionContext(unittest.TestCase):

    def setUp(self):
        self.ctx = ExecutionContext()

    def test_variable_set_get(self):
        self.ctx.set_variable("name", "Jules")
        self.assertEqual(self.ctx.get_variable("name"), "Jules")
        self.assertIsNone(self.ctx.get_variable("undefined_var"))
        self.assertEqual(self.ctx.get_variable("undefined_var", "default_val"), "default_val")

    def test_history_management(self):
        self.assertEqual(self.ctx.get_history(), [])
        self.ctx.add_history_entry(role="user", content="Hello PIL")
        expected_history = [{"role": "user", "content": "Hello PIL"}]
        self.assertEqual(self.ctx.get_history(), expected_history)

        self.ctx.add_history_entry(role="assistant", content="Hi there!")
        expected_history.append({"role": "assistant", "content": "Hi there!"})
        self.assertEqual(self.ctx.get_history(), expected_history)

        # Test that get_history returns a copy
        history_copy = self.ctx.get_history()
        history_copy.append({"role": "system", "content": "System message"})
        self.assertNotEqual(self.ctx.get_history(), history_copy)
        self.assertEqual(len(self.ctx.get_history()), 2)

    def test_history_entry_type_validation(self):
        with self.assertRaises(TypeError):
            self.ctx.add_history_entry(role=123, content="Invalid role type")
        with self.assertRaises(TypeError):
            self.ctx.add_history_entry(role="user", content=None) # Invalid content type

    def test_persona_management(self):
        self.assertEqual(self.ctx.get_persona(), {})
        persona_data = {"role": "AI Assistant", "tone": "helpful"}
        self.ctx.set_persona(persona_data)
        self.assertEqual(self.ctx.get_persona(), persona_data)

        # Test that get_persona returns a copy
        retrieved_persona = self.ctx.get_persona()
        retrieved_persona["style"] = "friendly"
        self.assertNotEqual(self.ctx.get_persona(), retrieved_persona)
        self.assertNotIn("style", self.ctx.get_persona())

    def test_persona_type_validation(self):
        with self.assertRaises(TypeError):
            self.ctx.set_persona("not a dict")

    def test_global_parameters_management(self):
        self.assertEqual(self.ctx.get_global_parameters(), {})
        params_data = {"temperature": 0.7, "model": "gpt-4"}
        self.ctx.set_global_parameters(params_data)
        self.assertEqual(self.ctx.get_global_parameters(), params_data)

        # Test that get_global_parameters returns a copy
        retrieved_params = self.ctx.get_global_parameters()
        retrieved_params["max_tokens"] = 100
        self.assertNotEqual(self.ctx.get_global_parameters(), retrieved_params)
        self.assertNotIn("max_tokens", self.ctx.get_global_parameters())

    def test_global_parameters_type_validation(self):
        with self.assertRaises(TypeError):
            self.ctx.set_global_parameters(["not", "a", "dict"])

    def test_str_representation(self):
        self.ctx.set_variable("test_var", 123)
        self.ctx.add_history_entry("user", "test query")
        self.ctx.set_persona({"role": "tester"})
        self.ctx.set_global_parameters({"temp": 0.5})

        representation = str(self.ctx)
        self.assertIn("test_var", representation)
        self.assertIn("123", representation)
        self.assertIn("test query", representation)
        self.assertIn("tester", representation)
        self.assertIn("temp", representation)
        self.assertIn("0.5", representation)
        self.assertIn("ExecutionContext", representation)

if __name__ == "__main__":
    unittest.main()
