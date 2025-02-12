# SPDX-License-Identifier: MIT

from unittest import mock

import pytest

from argon2 import PasswordHasher, Type, extract_parameters, profiles
from argon2._password_hasher import _ensure_bytes
from argon2._utils import Parameters
from argon2.exceptions import (
    InvalidHash,
    InvalidHashError,
    UnsupportedParamsError,
)


class TestEnsureBytes:
    def test_is_bytes(self):
        """
        Bytes are just returned.
        """
        s = "föö".encode()

        rv = _ensure_bytes(s, "doesntmatter")

        assert isinstance(rv, bytes)
        assert s == rv

    def test_is_str(self):
        """
        Unicode str is encoded using the specified encoding.
        """
        s = "föö"

        rv = _ensure_bytes(s, "latin1")

        assert isinstance(rv, bytes)
        assert s.encode("latin1") == rv


bytes_and_str_password = pytest.mark.parametrize(
    "password", ["pässword".encode("latin1"), "pässword"]
)


class TestPasswordHasher:
    @bytes_and_str_password
    def test_hash(self, password):
        """
        Hashing works with str and bytes.  Uses correct parameters.
        """
        ph = PasswordHasher(1, 8, 1, 16, 16, "latin1")

        h = ph.hash(password)

        prefix = "$argon2id$v=19$m=8,t=1,p=1$"

        assert isinstance(h, str)
        assert h[: len(prefix)] == prefix

    def test_custom_salt(self, password=b"password"):
        """
        A custom salt can be specified.
        """
        ph = PasswordHasher.from_parameters(profiles.CHEAPEST)

        h = ph.hash(password, salt=b"1234567890123456")

        assert h == (
            "$argon2id$v=19$m=8,t=1,p=1$MTIzNDU2Nzg5MDEyMzQ1Ng$maTa5w"
        )

    @bytes_and_str_password
    def test_verify_agility(self, password):
        """
        Verification works with str and bytes and variant is correctly
        detected.
        """
        ph = PasswordHasher(1, 8, 1, 16, 16, "latin1")
        hash = (  # handrolled artisanal test vector
            "$argon2i$m=8,t=1,p=1$"
            "bL/lLsegFKTuR+5vVyA8tA$VKz5CHavCtFOL1N5TIXWSA"
        )

        assert ph.verify(hash, password)

    @bytes_and_str_password
    def test_hash_verify(self, password):
        """
        Hashes are valid and can be verified.
        """
        ph = PasswordHasher()

        assert ph.verify(ph.hash(password), password) is True

    def test_check(self):
        """
        Raises a helpful TypeError on wrong arguments.
        """
        with pytest.raises(TypeError) as e:
            PasswordHasher("1")

        assert "'time_cost' must be a int (got str)." == e.value.args[0]

    def test_verify_invalid_hash_error(self):
        """
        If the hash can't be parsed, InvalidHashError is raised.
        """
        with pytest.raises(InvalidHashError):
            PasswordHasher().verify("tiger", "does not matter")

    def test_verify_invalid_hash(self):
        """
        InvalidHashError and the deprecrated InvalidHash are the same.
        """
        with pytest.raises(InvalidHash):
            PasswordHasher().verify("tiger", "does not matter")

    @pytest.mark.parametrize("use_bytes", [True, False])
    def test_check_needs_rehash_no(self, use_bytes):
        """
        Return False if the hash has the correct parameters.
        """
        ph = PasswordHasher(1, 8, 1, 16, 16)

        hash = ph.hash("foo")
        if use_bytes:
            hash = hash.encode()

        assert not ph.check_needs_rehash(hash)

    @pytest.mark.parametrize("use_bytes", [True, False])
    def test_check_needs_rehash_yes(self, use_bytes):
        """
        Return True if any of the parameters changes.
        """
        ph = PasswordHasher(1, 8, 1, 16, 16)
        ph_old = PasswordHasher(1, 8, 1, 8, 8)

        hash = ph_old.hash("foo")
        if use_bytes:
            hash = hash.encode()

        assert ph.check_needs_rehash(hash)

    def test_type_is_configurable(self):
        """
        Argon2id is default but can be changed.
        """
        ph = PasswordHasher(time_cost=1, memory_cost=64)
        default_hash = ph.hash("foo")

        assert Type.ID is ph.type is ph._parameters.type
        assert Type.ID is extract_parameters(default_hash).type

        ph = PasswordHasher(time_cost=1, memory_cost=64, type=Type.I)

        assert Type.I is ph.type is ph._parameters.type
        assert Type.I is extract_parameters(ph.hash("foo")).type
        assert ph.check_needs_rehash(default_hash)

    @mock.patch("sys.platform", "emscripten")
    def test_params_on_wasm(self):
        """
        Should fail if on wasm and parallelism > 1
        """
        for machine in ["wasm32", "wasm64"]:
            with mock.patch("platform.machine", return_value=machine):
                with pytest.raises(UnsupportedParamsError) as exinfo:
                    PasswordHasher(parallelism=2)

                assert (
                    str(exinfo.value)
                    == "within wasm/wasi environments `parallelism` must be set to 1"
                )

                # last param is parallelism so it should fail
                params = Parameters(Type.I, 2, 8, 8, 3, 256, 8)
                with pytest.raises(UnsupportedParamsError) as exinfo:
                    ph = PasswordHasher.from_parameters(params)

                assert (
                    str(exinfo.value)
                    == "within wasm/wasi environments `parallelism` must be set to 1"
                )

                # test normal execution
                ph = PasswordHasher(parallelism=1)
                hash = ph.hash("hello")
                assert ph.verify(hash, "hello") is True

                # test default params
                default_params = profiles.get_default_params()
                ph = PasswordHasher.from_parameters(default_params)
                hash = ph.hash("hello")
                assert ph.verify(hash, "hello") is True
