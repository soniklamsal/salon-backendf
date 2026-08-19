"""Model fields shared by the content apps."""

from django.db import models

from common.crypto import decrypt, encrypt


class EncryptedCharField(models.CharField):
    """A CharField whose value is encrypted in the database column.

    Transparent in Python: assign and read a plain string. The value is
    encrypted on the way to the database and decrypted on the way back, so
    templates, forms and the admin need to know nothing about it.

    Ciphertext is longer than what went in, so `max_length` has to leave room.
    It is not a constraint on the plaintext here -- validate that on the form
    if it ever matters.

    Not usable in a query. `Model.objects.filter(password="hunter2")` matches
    nothing, because Fernet includes a timestamp and random IV and so the same
    plaintext encrypts differently every time. That is correct for a secret --
    the only thing anyone should do with this value is send it to a server.
    """

    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def get_prep_value(self, value):
        return encrypt(super().get_prep_value(value) or "")

    def to_python(self, value):
        # Reached when a form re-cleans an already-decrypted value; `decrypt`
        # passes anything without the marker through untouched.
        return decrypt(super().to_python(value) or "")
