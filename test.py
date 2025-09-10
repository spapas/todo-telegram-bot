import unittest
from tbot import parse_add_command

class TestParseAddCommand(unittest.TestCase):
    def test_only_task(self):
        text = "Finish the report"
        task, params = parse_add_command(text)
        self.assertEqual(task, "Finish the report")
        self.assertEqual(params, {})

    def test_task_with_params(self):
        text = "Finish report who=Bob category=Work tags=urgent,important"
        task, params = parse_add_command(text)
        self.assertEqual(task, "Finish report")
        self.assertEqual(params, {"who": "Bob", "category": "Work", "tags": "urgent,important"})

    def test_task_with_comma_in_description(self):
        text = "Buy milk, eggs, bread who=Alice tags=grocery,food"
        task, params = parse_add_command(text)
        self.assertEqual(task, "Buy milk, eggs, bread")
        self.assertEqual(params, {"who": "Alice", "tags": "grocery,food"})

    def test_task_with_spaces_around_equals(self):
        text = "Do homework who = Alice category = School tags = urgent,homework"
        task, params = parse_add_command(text)
        self.assertEqual(task, "Do homework")
        self.assertEqual(params, {"who": "Alice", "category": "School", "tags": "urgent,homework"})

if __name__ == "__main__":
    unittest.main()
