"""Validate operator inputs without reading secrets or connecting to a database."""
import ast
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
import unittest
from fastapi import HTTPException

source = ast.parse((Path(__file__).resolve().parents[1] / "admin_server.py").read_text(encoding="utf-8-sig"))
functions = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in {"validate_enemy_base", "validate_endgame_stage"}]
scope = dict(Decimal=Decimal, InvalidOperation=InvalidOperation, HTTPException=HTTPException, Any=Any, re=re)
exec(compile(ast.Module(body=functions, type_ignores=[]), "enemy-validation", "exec"), scope)
validate = scope["validate_enemy_base"]

class EnemyBaseValidationTest(unittest.TestCase):
    def test_invalid_numbers(self):
        for value in (True, None, "NaN", "Infinity", -1, 0, 10**12+1):
            with self.subTest(value=value), self.assertRaises(HTTPException):
                validate({"hp": value})

    def test_bounds_and_optional_fields(self):
        validate({"hp": 10**12, "martial_power": 0, "speed": 1, "enabled": False})
        validate({"family": "TOWER", "enemy_code": "12:1", "hp": 1040}, creating=True)

    def test_required_hp_and_stage_identity(self):
        for payload in ({}, {"hp": 100, "family": "TOWER", "enemy_code": "0:1"}, {"hp": 100, "enabled": "false"}):
            with self.subTest(payload=payload), self.assertRaises(HTTPException):
                validate(payload, creating=True)

    def test_rejects_unreachable_rooms_and_fractional_floors(self):
        for payload in ({"mode":"TOWER","stage_no":1,"chamber_no":2}, {"mode":"ABYSS","stage_no":1,"chamber_no":4}, {"mode":"TOWER","stage_no":1.5}, {"mode":"TOWER","stage_no":True}):
            with self.subTest(payload=payload), self.assertRaises(HTTPException):
                scope["validate_endgame_stage"](payload)
        scope["validate_endgame_stage"]({"mode":"ABYSS","stage_no":12,"chamber_no":3})

if __name__ == "__main__":
    unittest.main()
