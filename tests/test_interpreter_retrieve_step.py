import unittest
import os
import json
from pathlib import Path

from pil_engine.interpreter import Interpreter, PilParser
from pil_engine.core.components import PilProgram, RetrieveStep
from pil_engine.core.context import Context

# Helper to create a PilProgram for testing retrieve steps
def create_retrieve_test_program(
    from_source: str,
    query: str,
    k: int = 3,
    initial_vars: dict = None,
    def_var: str = "retrieved_docs"
) -> PilProgram:

    program_dict = {
        "config": {}, # No model specified, so LLM client init will be skipped
        "workflow": {
            "steps": [
                {
                    "retrieve": {
                        "from": from_source,
                        "query": query,
                        "k": k,
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

class TestInterpreterRetrieveStep(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create a dummy KB file for testing
        cls.test_data_dir = Path(__file__).parent / "test_data"
        cls.test_kb_path = cls.test_data_dir / "test_kb_for_retrieval.json" # Use a distinct name
        cls.sample_kb_data = [
            {"id": "doc1", "content": "Paris is the capital of France. Eiffel Tower is a landmark."},
            {"id": "doc2", "content": "The weather in Paris is mild. Spring in Paris is lovely."},
            {"id": "doc3", "content": "London is the capital of the United Kingdom."},
            {"id": "doc4", "content": "France has great food and wine. Paris is a culinary center."},
            {"id": "doc5", "content": "This document has no relevant keywords for typical queries."},
            {"id": "doc6", "content": "Another document about the Eiffel Tower in Paris."}
        ]
        cls.test_data_dir.mkdir(exist_ok=True)
        with open(cls.test_kb_path, "w") as f:
            json.dump(cls.sample_kb_data, f)

    @classmethod
    def tearDownClass(cls):
        if cls.test_kb_path.exists():
            os.remove(cls.test_kb_path)

    def test_simple_retrieval_found(self):
        program = create_retrieve_test_program(str(self.test_kb_path), "Paris Eiffel Tower", k=2)
        interpreter = Interpreter(program)
        interpreter.run()

        retrieved_docs = interpreter.context.get_variable("retrieved_docs")
        self.assertEqual(len(retrieved_docs), 2)
        self.assertEqual(retrieved_docs[0]["id"], "doc1") # "Paris", "Eiffel", "Tower" - 3 matches
        self.assertEqual(retrieved_docs[1]["id"], "doc6") # "Eiffel", "Tower", "Paris" - 3 matches (order might vary if scores are same)
        # Check scores (simple count of common unique keywords)
        self.assertAlmostEqual(retrieved_docs[0]["score"], 3.0)
        self.assertAlmostEqual(retrieved_docs[1]["score"], 3.0)


    def test_retrieval_with_templating_in_query(self):
        program = create_retrieve_test_program(str(self.test_kb_path), "Information about {{city_name}}", k=1, initial_vars={"city_name": "London"})
        interpreter = Interpreter(program, initial_vars={"city_name": "London"})
        interpreter.run()

        retrieved_docs = interpreter.context.get_variable("retrieved_docs")
        self.assertEqual(len(retrieved_docs), 1)
        self.assertEqual(retrieved_docs[0]["id"], "doc3") # "London", "capital" (if "information about" is ignored by splitting) -> query "information about london"
        # Query: "information about london" -> tokens: {information, about, london}
        # Doc3: "london is the capital of the united kingdom" -> tokens: {london, is, the, capital, of, united, kingdom}
        # Common: {london} -> score 1.0 (This is very basic, "information" and "about" likely won't match)
        # Let's refine query for better testing: "capital {{city_name}}"

        program_refined = create_retrieve_test_program(str(self.test_kb_path), "capital {{city_name}}", k=1, initial_vars={"city_name": "London"})
        interpreter_refined = Interpreter(program_refined, initial_vars={"city_name": "London"})
        interpreter_refined.run()
        retrieved_docs_refined = interpreter_refined.context.get_variable("retrieved_docs")
        self.assertEqual(len(retrieved_docs_refined), 1)
        self.assertEqual(retrieved_docs_refined[0]["id"], "doc3") # Query: "capital london", Doc3: "london capital" -> score 2
        self.assertAlmostEqual(retrieved_docs_refined[0]["score"], 2.0)


    def test_retrieval_k_value_respected(self):
        program = create_retrieve_test_program(str(self.test_kb_path), "Paris", k=1)
        interpreter = Interpreter(program)
        interpreter.run()
        retrieved_docs = interpreter.context.get_variable("retrieved_docs")
        self.assertEqual(len(retrieved_docs), 1)
        # Multiple docs contain "Paris", check that the one with highest score (or one of them) is returned
        self.assertIn(retrieved_docs[0]["id"], ["doc1", "doc2", "doc4", "doc6"])

    def test_retrieval_no_matches(self):
        program = create_retrieve_test_program(str(self.test_kb_path), "non_existent_keyword_xyz", k=3)
        interpreter = Interpreter(program)
        interpreter.run()
        retrieved_docs = interpreter.context.get_variable("retrieved_docs")
        self.assertEqual(len(retrieved_docs), 0)

    def test_retrieval_from_empty_kb_file(self):
        empty_kb_path = self.test_data_dir / "empty_kb.json"
        with open(empty_kb_path, "w") as f:
            json.dump([], f)

        program = create_retrieve_test_program(str(empty_kb_path), "any query", k=3)
        interpreter = Interpreter(program) # KB loading happens here
        interpreter.run() # Execute the workflow

        retrieved_docs = interpreter.context.get_variable("retrieved_docs")
        self.assertEqual(len(retrieved_docs), 0)
        os.remove(empty_kb_path)

    def test_retrieval_from_non_existent_kb_file(self):
        non_existent_kb_path = str(self.test_data_dir / "i_do_not_exist.json")
        program = create_retrieve_test_program(non_existent_kb_path, "any query", k=3)

        # KB loading failure occurs at Interpreter initialization and prints a warning.
        # The retrieval step itself should then gracefully return empty.
        interpreter = Interpreter(program)
        interpreter.run()

        retrieved_docs = interpreter.context.get_variable("retrieved_docs")
        self.assertEqual(len(retrieved_docs), 0)
        # Also check if the kb was marked as None (failed to load)
        self.assertIsNone(interpreter.knowledge_bases.get(non_existent_kb_path))

    def test_retrieval_case_insensitivity(self):
        program = create_retrieve_test_program(str(self.test_kb_path), "pArIs eiFFel", k=1)
        interpreter = Interpreter(program)
        interpreter.run()
        retrieved_docs = interpreter.context.get_variable("retrieved_docs")
        self.assertEqual(len(retrieved_docs), 1)
        self.assertEqual(retrieved_docs[0]["id"], "doc1") # or doc6, both have 2 matches for "paris", "eiffel"
        self.assertAlmostEqual(retrieved_docs[0]["score"], 2.0)

    def test_retrieval_document_structure_and_score(self):
        program = create_retrieve_test_program(str(self.test_kb_path), "London capital", k=1)
        interpreter = Interpreter(program)
        interpreter.run()
        retrieved_docs = interpreter.context.get_variable("retrieved_docs")
        self.assertEqual(len(retrieved_docs), 1)
        doc = retrieved_docs[0]
        self.assertEqual(doc["id"], "doc3")
        self.assertEqual(doc["content"], "London is the capital of the United Kingdom.")
        self.assertAlmostEqual(doc["score"], 2.0) # "london", "capital"
        # Ensure other fields from original doc are preserved
        original_doc3 = next(d for d in self.sample_kb_data if d["id"] == "doc3")
        # self.assertEqual(doc.get("title"), original_doc3.get("title")) # If title was in sample_kb_data for doc3

if __name__ == '__main__':
    unittest.main()
