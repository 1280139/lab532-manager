# -*- coding: utf-8 -*-
"""最小 pytest 兼容层 —— 无外网环境下也能跑测试。

只实现本项目的测试用到的 pytest 子集：
  pytest.fixture / pytest.raises / pytest.mark.skip
以及一个收集器，能跑 class Test* / def test_* 并处理 fixture 注入。

有 pytest 的环境请直接用 pytest，这个文件不会被用到。
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import os
import shutil
import sys
import tempfile
import traceback


# ---------------------------------------------------------------- API 桩
def fixture(func=None, *, scope="function", params=None, autouse=False):
    def deco(f):
        f._is_fixture = True
        f._scope = scope
        return f

    return deco(func) if func else deco


class _Raises:
    def __init__(self, exc, match=None):
        self.exc = exc
        self.match = match
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(f"期望抛出 {self.exc.__name__}，但没有抛出")
        if not issubclass(exc_type, self.exc):
            return False
        self.value = exc
        if self.match and self.match not in str(exc):
            raise AssertionError(f"异常信息不含 {self.match!r}：{exc}")
        return True


def raises(exc, match=None):
    return _Raises(exc, match)


class _Mark:
    def skip(self, reason=""):
        def deco(f):
            f._skip = reason or "skipped"
            return f

        return deco

    def parametrize(self, *a, **kw):
        def deco(f):
            return f

        return deco


mark = _Mark()


class _Skipped(Exception):
    pass


def skip(reason=""):
    raise _Skipped(reason or "skipped")


def fail(reason=""):
    raise AssertionError(reason)


# ---------------------------------------------------------------- 运行器
class Runner:
    def __init__(self):
        self.passed = 0
        self.failed = []
        self.skipped = 0
        self.fixture_cache: dict[str, object] = {}
        self.fixtures: dict[str, object] = {}

    def load_fixtures(self, module):
        for name, obj in vars(module).items():
            if callable(obj) and getattr(obj, "_is_fixture", False):
                self.fixtures[name] = obj
        # conftest 里的 fixture 也注册进来
        for name, obj in vars(sys.modules.get("conftest")).items() \
                if "conftest" in sys.modules else []:
            if callable(obj) and getattr(obj, "_is_fixture", False):
                self.fixtures[name] = obj

    def resolve(self, name, module):
        """解析一个 fixture，支持 fixture 依赖 fixture。"""
        if name in self.fixture_cache:
            return self.fixture_cache[name]

        func = self.fixtures.get(name)
        if func is None:
            raise LookupError(f"找不到 fixture: {name}")

        kwargs = {}
        for dep in inspect.signature(func).parameters:
            kwargs[dep] = self.resolve(dep, module)

        gen = func(**kwargs)
        if inspect.isgenerator(gen):
            value = next(gen)
            self.fixture_cache[name] = value
            self.fixture_cache[name + "__gen"] = gen
            return value
        self.fixture_cache[name] = gen
        return gen

    def teardown(self):
        for key in list(self.fixture_cache):
            if key.endswith("__gen"):
                gen = self.fixture_cache.pop(key)
                with contextlib.suppress(StopIteration):
                    next(gen)
        self.fixture_cache.clear()

    def call(self, func, module, extra_kwargs=None):
        kwargs = dict(extra_kwargs or {})
        for pname in inspect.signature(func).parameters:
            if pname in kwargs:
                continue
            kwargs[pname] = self.resolve(pname, module)
        return func(**kwargs)

    def run_module(self, module, label=""):
        self.load_fixtures(module)
        items = []

        for name, obj in vars(module).items():
            if name.startswith("Test") and inspect.isclass(obj):
                for mname, meth in vars(obj).items():
                    if mname.startswith("test_") and callable(meth):
                        items.append((f"{name}.{mname}", obj, meth))
            elif name.startswith("test_") and callable(obj):
                items.append((name, None, obj))

        if not items:
            return

        print(f"\n=== {label or module.__name__} ===")
        for full, cls, meth in items:
            if getattr(meth, "_skip", None):
                print(f"  SKIP  {full}")
                self.skipped += 1
                continue
            try:
                if cls is not None:
                    inst = cls()
                    bound = functools.partial(getattr(inst, meth.__name__))
                    self.call(bound, module)
                else:
                    self.call(meth, module)
                print(f"  PASS  {full}")
                self.passed += 1
            except _Skipped as e:
                print(f"  SKIP  {full}  （{e}）")
                self.skipped += 1
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL  {full}")
                tb = traceback.format_exc()
                print("        " + "\n        ".join(tb.strip().splitlines()[-6:]))
                self.failed.append((full, e))
            finally:
                self.teardown()

    def report(self) -> bool:
        print("\n" + "=" * 56)
        total = self.passed + len(self.failed) + self.skipped
        print(f"通过 {self.passed} / 共 {total}" +
              (f"，跳过 {self.skipped}" if self.skipped else ""))
        if self.failed:
            print(f"失败 {len(self.failed)} 项：")
            for name, e in self.failed:
                print(f"  - {name}: {e}")
            return False
        print("全部通过")
        return True


def run_all(test_modules: list[str]) -> bool:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    # 让测试文件里的 import pytest 指向本模块
    sys.modules["pytest"] = sys.modules[__name__]

    import importlib

    # 先加载 conftest
    if os.path.exists(os.path.join(root, "tests", "conftest.py")):
        sys.path.insert(0, os.path.join(root, "tests"))
        importlib.import_module("conftest")

    runner = Runner()
    for mod_name in test_modules:
        module = importlib.import_module(mod_name)
        runner.run_module(module, mod_name)
    return runner.report()


if __name__ == "__main__":
    mods = ["tests.test_rules", "tests.test_security", "tests.test_flows"]
    ok = run_all(mods)
    sys.exit(0 if ok else 1)
