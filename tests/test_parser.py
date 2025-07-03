import unittest
import os
import yaml # For creating invalid YAML for testing
from pil_interpreter.parser import load_pil_file
from pil_interpreter.exceptions import PILSyntaxError

# Helper to create temporary test files
def create_temp_file(directory, filename, content):
    filepath = os.path.join(directory, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return filepath

class TestPILParser(unittest.TestCase):

    def setUp(self):
        self.test_dir = "test_pil_files"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        for item in os.listdir(self.test_dir):
            os.remove(os.path.join(self.test_dir, item))
        os.rmdir(self.test_dir)

    def test_load_valid_pil_file(self):
        content = """
workflow:
  steps:
    - prompt: { text: "Hello" }
config:
  model: "test_model"
"""
        filepath = create_temp_file(self.test_dir, "valid.pil", content)
        data = load_pil_file(filepath)
        self.assertIn("workflow", data)
        self.assertIn("steps", data["workflow"])
        self.assertIsInstance(data["workflow"]["steps"], list)
        self.assertEqual(data["workflow"]["steps"][0]["prompt"]["text"], "Hello")
        self.assertEqual(data["config"]["model"], "test_model")

    def test_load_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_pil_file("non_existent_file.pil")

    def test_load_invalid_yaml_syntax(self):
        content = "workflow: [unclosed bracket" # Invalid YAML
        filepath = create_temp_file(self.test_dir, "invalid_yaml.pil", content)
        with self.assertRaisesRegex(PILSyntaxError, "Invalid YAML syntax"):
            load_pil_file(filepath)

    def test_load_pil_not_a_dictionary(self):
        content = "- item1\n- item2" # Valid YAML, but not a dictionary
        filepath = create_temp_file(self.test_dir, "list.pil", content)
        with self.assertRaisesRegex(PILSyntaxError, "must be a YAML mapping"):
            load_pil_file(filepath)

    def test_missing_workflow_key(self):
        content = "config: { model: 'test' }"
        filepath = create_temp_file(self.test_dir, "missing_workflow.pil", content)
        with self.assertRaisesRegex(PILSyntaxError, "missing required top-level keys: workflow"):
            load_pil_file(filepath)

    def test_workflow_not_a_dictionary(self):
        content = "workflow: \"just a string\""
        filepath = create_temp_file(self.test_dir, "workflow_string.pil", content)
        with self.assertRaisesRegex(PILSyntaxError, "The 'workflow' block must be a YAML mapping"):
            load_pil_file(filepath)

    def test_workflow_missing_steps_key(self):
        content = "workflow: { description: 'my workflow' }"
        filepath = create_temp_file(self.test_dir, "workflow_no_steps.pil", content)
        with self.assertRaisesRegex(PILSyntaxError, "must contain a 'steps' list"):
            load_pil_file(filepath)

    def test_workflow_steps_not_a_list(self):
        content = "workflow: { steps: 'not a list' }"
        filepath = create_temp_file(self.test_dir, "steps_not_list.pil", content)
        with self.assertRaisesRegex(PILSyntaxError, "The 'steps' in a 'workflow' block must be a list"):
            load_pil_file(filepath)

if __name__ == "__main__":
    unittest.main()
