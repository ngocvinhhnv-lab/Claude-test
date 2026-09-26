import unittest

from hello import greet


class TestGreet(unittest.TestCase):
    def test_default(self):
        self.assertEqual(greet(), "Xin chào, thế giới!")

    def test_name(self):
        self.assertEqual(greet("Vinh"), "Xin chào, Vinh!")


if __name__ == "__main__":
    unittest.main()
