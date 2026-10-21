"""Exercise request validation without loading environment secrets or touching a database."""
import ast
from decimal import Decimal, InvalidOperation
from pathlib import Path
import unittest
from fastapi import HTTPException

source = ast.parse((Path(__file__).resolve().parents[1] / "admin_server.py").read_text(encoding="utf-8-sig"))
functions = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "_shop_integer"]
scope = {"Decimal": Decimal, "InvalidOperation": InvalidOperation, "HTTPException": HTTPException}
exec(compile(ast.Module(body=functions, type_ignores=[]), "shop-validation", "exec"), scope)


class ShopValidationTest(unittest.TestCase):
    def test_rejects_invalid_numbers(self):
        for value in (True, False, None, "NaN", "Infinity", -1, 0, 1.5, "bad", 1000001):
            with self.subTest(value=value), self.assertRaises(HTTPException):
                scope["_shop_integer"]({"price": value}, "price", 1, 1000000)

    def test_accepts_exact_integer_bounds(self):
        for value in (1, 1000000, "10", "10.0"):
            self.assertEqual(scope["_shop_integer"]({"price": value}, "price", 1, 1000000), int(Decimal(str(value))))


if __name__ == "__main__":
    unittest.main()
