from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from nacl.utils import random
import nacl.secret
import nacl.utils


class SignalProtocol:
    def __init__(self):
        """
        Initialize with a new X25519 key pair and empty keys.
        """
        self.dh_pair = x25519.X25519PrivateKey.generate()
        self.dh_pub = self.dh_pair.public_key()
        self.root_key = None
        self.chain_key = None
        self.next_header_key = None

    def initial_key_exchange(self, other_public_key):
        """
        Perform initial key exchange to derive root and chain keys.
        """
        shared_key = self.dh_pair.exchange(other_public_key)
        kdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=None,
            info=b"signal_initial_exchange",
        )
        key_material = kdf.derive(shared_key)
        self.root_key = key_material[:32]
        self.chain_key = key_material[32:]

    def ratchet(self, other_public_key):
        """
        Update keys using a ratchet mechanism and generate a new key pair.
        """
        shared_key = self.dh_pair.exchange(other_public_key)
        kdf = HKDF(
            algorithm=hashes.SHA256(),
            length=96,
            salt=self.root_key,
            info=b"signal_ratchet",
        )
        key_material = kdf.derive(shared_key)
        self.root_key = key_material[:32]
        self.chain_key = key_material[32:64]
        self.next_header_key = key_material[64:]
        self.dh_pair = x25519.X25519PrivateKey.generate()
        self.dh_pub = self.dh_pair.public_key()

    def encrypt_message(self, plaintext):
        """
        Encrypt plaintext using a message key derived from the chain key.
        """
        message_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"signal_message_key",
        ).derive(self.chain_key)
        # Advance chain key
        self.chain_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"signal_next_chain_key",
        ).derive(self.chain_key)
        nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
        box = nacl.secret.SecretBox(message_key)
        encrypted = box.encrypt(plaintext.encode(), nonce)
        return encrypted

    def decrypt_message(self, ciphertext):
        """
        Decrypt ciphertext using a message key derived from the chain key.
        """
        message_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"signal_message_key",
        ).derive(self.chain_key)
        # Advance chain key
        self.chain_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"signal_next_chain_key",
        ).derive(self.chain_key)
        box = nacl.secret.SecretBox(message_key)
        decrypted = box.decrypt(ciphertext)
        return decrypted.decode()


def generate_key_pair():
    """
    Generate a new X25519 key pair.
    """
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def serialize_public_key(public_key):
    """
    Serialize a public key to bytes.
    """
    return public_key.public_bytes_raw()


def serialize_private_key(private_key):
    """
    Serialize a private key to bytes.
    """
    return private_key.private_bytes_raw()


def deserialize_public_key(serialized_key):
    """
    Deserialize bytes into a X25519 public key.
    """
    return x25519.X25519PublicKey.from_public_bytes(serialized_key)


def deserialize_private_key(serialized_key):
    """
    Deserialize bytes into a X25519 private key.
    """
    return x25519.X25519PrivateKey.from_private_bytes(serialized_key)
